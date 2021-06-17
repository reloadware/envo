import os
import re
from pathlib import Path
from time import sleep

import pytest
from flaky import flaky

from tests import facade
from tests.e2e import utils

flaky = flaky(max_runs=3, min_passes=1)


class TestMisc(utils.TestBase):
    def test_shell(self, shell):
        e = shell.start()
        e.prompt().eval()

        shell.sendline("print('test')")
        e.output(r"test\n")
        e.prompt().eval()

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()

        shell.exit()
        e.exit().eval()

    def test_dry_run(self):
        ret = utils.run("envo test dry-run")
        assert re.match(
            (
                r'export ENVO_NAME="sandbox"\n'
                r'export ENVO_STAGE="test"\n'
                r'export PATH=".*"\n'
                r'export PYTHONPATH=".*"\n'
                r'export SANDBOX_ROOT=".*sandbox"\n'
                r'export SANDBOX_STAGE="test"\n'
            ),
            ret,
        )

    def test_dump(self):
        utils.add_declaration("test_var: str = var(default='test_value')")

        ret = utils.run("envo test dump")
        assert "Saved envs to .env_test" in ret

        dot_env = Path(".env_test")
        assert dot_env.exists()

        # remove PYTHONPATH since it'll be different depending on the machine
        content = dot_env.read_text()
        print(f"Comparing:\n{content}")
        assert re.match(
            (
                r'ENVO_NAME="sandbox"\n'
                r'ENVO_STAGE="test"\n'
                r'PATH=".*"\n'
                r'PYTHONPATH=".*"\n'
                r'SANDBOX_ROOT=".*sandbox"\n'
                r'SANDBOX_STAGE="test"\n'
                r'SANDBOX_TESTVAR="test_value"'
            ),
            content,
        )

    @pytest.mark.parametrize(
        "dir_name", ["my-sand-box", "my sandbox", ".sandbox", ".san.d- b  ox"]
    )
    def test_init_weird_dir_name(self, shell, dir_name):
        env_dir = Path(dir_name)
        env_dir.mkdir()
        os.chdir(str(env_dir))

        utils.run("envo test init")

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()

        e = shell.start()

        e.prompt(name=dir_name).eval()

        shell.exit()
        e.exit().eval()

    def test_autodiscovery(self, shell):
        Path("./test_dir").mkdir()
        os.chdir("./test_dir")

        e = shell.start()

        e.prompt().eval()

        shell.sendline("print('test')")
        e.output(r"test\n")
        e.prompt()

        shell.exit()
        e.exit().eval()

        assert list(Path(".").glob(".*")) == []

    @flaky
    def test_multiple_instances(self):
        shells = []
        for i in range(6):
            s = utils.SpawnEnvo("test", debug=False)
            s.start()
            shells.append(s)

        utils.trigger_reload()
        sleep(0.5)

        for s in shells:
            s.expecter.prompt().eval()
            s.exit()
            s.expecter.exit().eval()

    def test_env_persists_in_bash_scripts(self, shell):
        e = shell.start()
        e.prompt().eval()

        if facade.is_linux():
            file = Path("script.sh")
            file.touch()
            file.write_text("echo $SANDBOX_ROOT\n")
            shell.sendline("bash script.sh")
            e.output(str(Path(".").absolute()) + r"\n")

        if facade.is_windows():
            file = Path("script.bat")
            file.touch()
            file.write_text("@ECHO OFF\necho %SANDBOX_ROOT%\n")
            shell.sendline("script.bat")
            e.output(str(Path(".").absolute()).replace("\\", "\\\\") + r"\n")

        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_add_source_roots(self, shell):
        comm_path = Path("comm")
        comm_path.mkdir()

        comm_package = comm_path / "package"
        comm_package.mkdir()

        comm_package_init = comm_package / "__init__.py"
        comm_package_init.touch()

        utils.replace_in_code("envo.add_source_roots([root])", "envo.add_source_roots([root, root/'comm'])")
        utils.replace_in_code("# Declare your command namespaces here", "import package")

        e = shell.start()
        e.prompt().eval()

        shell.exit()
        e.exit().eval()