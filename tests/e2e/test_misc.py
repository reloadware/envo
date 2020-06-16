import os
import re
from pathlib import Path

import pexpect
import pytest
from pexpect import run

from tests.e2e import utils


class TestMisc(utils.TestBase):
    def test_shell(self, shell, envo_prompt):
        shell.sendline("print('test')")
        shell.expect(b"test")
        shell.expect(envo_prompt)

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()

    def test_shell_exit(self, shell, envo_prompt):
        shell.sendcontrol("d")
        shell.expect(pexpect.EOF)

    def test_dry_run(self):
        ret = run("envo test --dry-run")
        assert ret != b""

    def test_save(self):
        utils.add_declaration("test_var: str")
        utils.add_definition('self.test_var = "test_value"')

        s = utils.spawn("envo test --save")
        s.expect(r"Saved envs to \.env_test")
        s.expect(pexpect.EOF)

        dot_env = Path(".env_test")
        assert dot_env.exists()

        # remove PYTHONPATH since it'll be different depending on the machine
        content = dot_env.read_text()
        content = re.sub(r'PYTHONPATH.*"', "", content, 1)
        content = re.sub(r'SANDBOX_ROOT.*"', "", content, 1)
        content = content.replace("\n\n", "\n")
        if content.startswith("\n"):
            content = content[1:]

        if content.endswith("\n"):
            content = content[:-1]

        assert (
            content == 'SANDBOX_STAGE="test"\n'
            'ENVO_STAGE="test"\n'
            'SANDBOX_TESTVAR="test_value"'
        )

    @pytest.mark.parametrize(
        "dir_name", ["my-sand-box", "my sandbox", ".sandbox", ".san.d- b  ox"]
    )
    def test_init_weird_dir_name(self, dir_name, envo_prompt):
        env_dir = Path(dir_name)
        env_dir.mkdir()
        os.chdir(str(env_dir))
        run("envo test --init")

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()
        s = utils.spawn("envo test")
        prompt = envo_prompt.replace(b"sandbox", dir_name.encode("utf-8"))
        prompt = prompt.replace(b".", rb"\.")
        s.expect(prompt)

    def test_autodiscovery(self, envo_prompt):
        Path("./test_dir").mkdir()
        os.chdir("./test_dir")

        s = utils.shell()
        s.sendline("print('test')")
        s.expect(b"test")
        s.expect(envo_prompt)
        s.sendcontrol("d")

        assert list(Path(".").glob(".*")) == []

    def test_multiple_instances(self, envo_prompt):
        shells = [utils.shell() for i in range(6)]

        new_content = Path("env_comm.py").read_text() + "\n"
        utils.change_file(Path("env_comm.py"), 0.5, new_content)

        [s.expect(envo_prompt, timeout=10) for s in shells]

    def test_env_persists_in_bash_scripts(self, shell):
        file = Path("script.sh")
        file.touch()
        file.write_text("$SANDBOX_ROOT\n")

        shell.sendline("bash script.sh")
        shell.expect(str(Path(".").absolute()))

    def test_access_to_env_in_shell(self, shell):
        shell.sendline("script.sh")
