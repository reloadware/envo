import os
import re
import time
from pathlib import Path

import pexpect
import pytest
from pexpect import run

from tests.e2e import utils


class TestE2e:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox, init):
        pass

    def test_shell(self, shell, envo_prompt):
        shell.sendline("print('test')")
        shell.expect(b"test")
        shell.expect(envo_prompt)

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()

    def test_shell_exit(self, shell):
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


class TestHotReload:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox, init):
        pass

    def test_hot_reload(self, shell, envo_prompt):
        new_content = Path("env_comm.py").read_text().replace("sandbox", "new")
        utils.change_file(Path("env_comm.py"), 0.5, new_content)
        new_prompt = envo_prompt.replace(b"sandbox", b"new")
        shell.expect(new_prompt, timeout=2)

    def test_old_envs_gone(self, shell, envo_prompt):
        shell.sendline("$SANDBOX_STAGE")
        shell.expect("test")

        new_content = Path("env_comm.py").read_text().replace("sandbox", "new")
        utils.change_file(Path("env_comm.py"), 0.5, new_content)
        new_prompt = envo_prompt.replace(b"sandbox", b"new")
        shell.expect(new_prompt)

        shell.sendline("$NEW_STAGE")
        shell.expect("test")

        shell.sendline("$SANDBOX_STAGE")
        shell.expect(new_prompt)

    def test_from_child_dir(self, shell, envo_prompt):
        Path("./test_dir").mkdir()
        os.chdir("./test_dir")

        new_content = Path("../env_comm.py").read_text() + "\n"
        utils.change_file(Path("../env_comm.py"), 0.5, new_content)

        shell.expect(envo_prompt)

    def test_error(self, shell, envo_prompt):
        comm_file = Path("env_comm.py")
        file_before = comm_file.read_text()

        new_content = comm_file.read_text().replace(
            "# Declare your variables here", "test_var: int"
        )
        utils.change_file(Path("env_comm.py"), 0.5, new_content)

        shell.expect(
            r'Reloading.*Detected errors!.*Variable "sandbox\.test_var" is unset!',
            timeout=5,
        )
        shell.expect("❌".encode("utf-8"), timeout=2)

        Path("env_comm.py").write_text(file_before)
        shell.expect(envo_prompt, timeout=2)

    def test_few_times_in_a_row_quick(self, shell, envo_prompt):
        env_comm_file = Path("env_comm.py")

        for i in range(5):
            time.sleep(0.1)
            env_comm_file.write_text(env_comm_file.read_text() + "\n")

        shell.expect(envo_prompt)

        shell.sendcontrol("d")
        shell.expect(pexpect.EOF, timeout=10)

    def test_if_reproductible(self, envo_prompt):
        os.environ["PATH"] = "/already_existing_path:" + os.environ["PATH"]

        shell = utils.shell()
        utils.add_declaration("path: Raw[str]")
        utils.add_definition(
            """
                    import os
                    self.path = os.environ["PATH"]
                    self.path = "/some_path:" + self.path
                    """
        )

        Path("env_comm.py").write_text(Path("env_comm.py").read_text() + "\n")
        time.sleep(0.2)
        Path("env_comm.py").write_text(Path("env_comm.py").read_text() + "\n")
        time.sleep(0.2)
        Path("env_comm.py").write_text(Path("env_comm.py").read_text() + "\n")
        time.sleep(0.2)

        shell.sendline("$PATH")
        time.sleep(0.5)

        shell.expect(r"\['/some_path', '/already_existing_path'.*\]", timeout=2)


class TestCommands:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox, init):
        pass

    def test_command_no_prop_no_glob(self, envo_prompt):
        utils.flake_cmd(prop=False, glob=False)
        utils.mypy_cmd(prop=False, glob=False)
        s = utils.shell()

        s.sendline("env.flake")
        s.expect(r"envo\.env\.Command object at")
        s.expect(envo_prompt)

        s.sendline("env.flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.mypy()")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

        s.sendline("flake")
        s.expect("not found")
        s.expect(envo_prompt)

        s.sendline("flake()")
        s.expect("NameError: name 'flake' is not defined")
        s.expect(envo_prompt)

    def test_command_prop_no_glob(self, envo_prompt):
        utils.flake_cmd(prop=True, glob=False)
        utils.mypy_cmd(prop=True, glob=False)
        s = utils.shell()

        s.sendline("env.flake")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.mypy")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

        s.sendline("env.flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.mypy()")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

        s.sendline("flake")
        s.expect("not found")
        s.expect(envo_prompt)

        s.sendline("flake()")
        s.expect("NameError: name 'flake' is not defined")
        s.expect(envo_prompt)

    def test_command_no_prop_glob(self, envo_prompt):
        utils.flake_cmd(prop=False, glob=True)
        utils.mypy_cmd(prop=False, glob=True)
        s = utils.shell()

        s.sendline("env.flake")
        s.expect(r"envo\.env\.Command object at")
        s.expect(envo_prompt)

        s.sendline("env.flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.mypy()")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

        s.sendline("flake")
        s.expect(r"envo\.env\.Command object at")
        s.expect(envo_prompt)

        s.sendline("flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("mypy()")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

    def test_command_prop_glob(self, envo_prompt):
        utils.flake_cmd(prop=True, glob=True)
        utils.mypy_cmd(prop=False, glob=False)
        s = utils.shell()

        s.sendline("env.flake")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("flake")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

    def test_cmd_in_non_root_dir(self, envo_prompt):
        utils.add_command(
            """
            @command(glob=True, prop=True)
            def flake(self) -> None:
                print("flake good")
            """
        )
        s = utils.shell()

        child_dir = Path("child_dir")
        child_dir.mkdir()

        os.chdir(str(child_dir))

        s.sendline("flake")
        s.expect("flake good")
        s.expect(envo_prompt)

    def test_single_command(self):
        from tests.e2e.utils import spawn

        s = spawn("""envo test -c "print('teest')" """)
        s.expect("teest")
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 0

    def test_single_command_fail(self):
        from tests.e2e.utils import spawn

        s = spawn("""envo test -c "import sys;print('some msg');sys.exit(2)" """)
        s.expect("some msg")
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 2

        s = spawn("""envo test -c "cat /home/non_existend_file" """)
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 1


class TestParentChild:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox, init):
        pass

    def test_init(self, envo_prompt, init_child_env):
        from tests.e2e.utils import spawn

        os.chdir("child")

        s = spawn("envo test --shell=simple")
        nested_prompt = envo_prompt.replace(b"sandbox", b"sandbox.child")

        s.expect(nested_prompt)

    def test_child_parent_prompt(self, init_child_env):
        from tests.e2e.utils import spawn

        os.chdir("child")

        s = spawn("envo test --shell=simple")
        s.expect(r"🛠\(sandbox.child\).*".encode("utf-8"))

    def test_hot_reload(self, envo_prompt, init_child_env):
        from tests.e2e.utils import spawn

        os.chdir("child")

        s = spawn("envo test --shell=simple")
        nested_prompt = envo_prompt.replace(b"sandbox", b"sandbox.child")
        s.expect(nested_prompt)

        child_file = Path("env_comm.py")
        content = child_file.read_text()
        content = content.replace("child", "ch")
        child_file.write_text(content)

        new_prompt1 = nested_prompt.replace(b"child", b"ch")
        s.expect(new_prompt1)

        parent_file = Path("../env_comm.py")
        content = parent_file.read_text()
        content = content.replace("sandbox", "sb")
        parent_file.write_text(content)

        new_prompt2 = new_prompt1.replace(b"sandbox", b"sb")
        s.expect(new_prompt2)

    def test_child_importable(self, envo_prompt, init_child_env):
        from tests.e2e.utils import spawn

        Path("__init__.py").touch()
        os.chdir("child")
        Path("__init__.py").touch()

        s = spawn("envo test --shell=simple")
        nested_prompt = envo_prompt.replace(b"sandbox", b"sandbox.child")
        s.expect(nested_prompt)

        test_script = Path("test_script.py")
        content = "from env_test import Env\n"
        content += "env = Env()\n"
        content += 'print("ok")\n'
        test_script.write_text(content)

        s.sendline("python3 test_script.py")
        s.expect("ok")

    def test_same_child_names(self, init_2_same_childs):
        from tests.e2e.utils import spawn

        root_dir = Path(".").absolute()

        os.chdir(root_dir / "sandbox/sandbox")

        s = spawn("envo test --shell=simple")
        s.sendline('"sandbox.sandbox.sandbox" in $PROMPT')
        s.expect("True", timeout=3)
