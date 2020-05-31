import os
import re
import time
from pathlib import Path

import pexpect
import pytest
from pexpect import run
from tests.utils import change_file


class TestE2e:
    @pytest.fixture(autouse=True)
    def setup(self, mock_exit, sandbox, prompt, init):
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
        from envo.comm.test_utils import spawn

        comm_file = Path("env_comm.py")

        comm_file.write_text(
            comm_file.read_text().replace(
                "# Declare your variables here", "test_var: str"
            )
        )
        comm_file.write_text(
            comm_file.read_text().replace(
                "# Define your variables here", 'self.test_var = "test_value"'
            )
        )

        s = spawn("envo test --save")
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

    def test_hot_reload(self, shell, envo_prompt):
        new_content = Path("env_comm.py").read_text().replace("sandbox", "new")
        change_file(Path("env_comm.py"), 0.5, new_content)
        new_prompt = envo_prompt.replace(b"sandbox", b"new")
        shell.expect(new_prompt, timeout=2)

    def test_hot_reload_old_envs_gone(self, shell, envo_prompt):
        shell.sendline("$SANDBOX_STAGE")
        shell.expect("test")

        new_content = Path("env_comm.py").read_text().replace("sandbox", "new")
        change_file(Path("env_comm.py"), 0.5, new_content)
        new_prompt = envo_prompt.replace(b"sandbox", b"new")
        shell.expect(new_prompt)

        shell.sendline("$NEW_STAGE")
        shell.expect("test")

        shell.sendline("$SANDBOX_STAGE")
        shell.expect(new_prompt)

    def test_hot_reload_child_dir(self, shell, envo_prompt):
        Path("./test_dir").mkdir()
        os.chdir("./test_dir")

        new_content = Path("../env_comm.py").read_text() + "\n"
        change_file(Path("../env_comm.py"), 0.5, new_content)

        shell.expect(envo_prompt)

    def test_hot_reload_error(self, shell, envo_prompt):
        comm_file = Path("env_comm.py")
        file_before = comm_file.read_text()

        new_content = comm_file.read_text().replace(
            "# Declare your variables here", "test_var: int"
        )
        change_file(Path("env_comm.py"), 0.5, new_content)

        shell.expect(
            r'Reloading.*Detected errors!.*Variable "sandbox\.test_var" is unset!',
            timeout=5,
        )
        shell.expect("❌".encode("utf-8") + envo_prompt, timeout=2)

        Path("env_comm.py").write_text(file_before)
        shell.expect(envo_prompt, timeout=2)

    def test_hot_reload_few_times_in_a_row_quick(self, shell, envo_prompt):
        env_comm_file = Path("env_comm.py")

        for i in range(5):
            time.sleep(0.1)
            env_comm_file.write_text(env_comm_file.read_text() + "\n")

        shell.expect(envo_prompt)

        shell.sendcontrol("d")
        shell.expect(pexpect.EOF, timeout=6)

    def test_autodiscovery(self, envo_prompt):
        from envo.comm.test_utils import shell

        Path("./test_dir").mkdir()
        os.chdir("./test_dir")

        s = shell()
        s.sendline("print('test')")
        s.expect(b"test")
        s.expect(envo_prompt)
        s.sendcontrol("d")

        assert list(Path(".").glob(".*")) == []

    def test_multiple_instances(self, envo_prompt):
        from envo.comm.test_utils import shell

        shells = [shell() for i in range(6)]

        new_content = Path("env_comm.py").read_text() + "\n"
        change_file(Path("env_comm.py"), 0.5, new_content)

        [s.expect(envo_prompt, timeout=8) for s in shells]

    def test_env_persists_in_bash_scripts(self, shell):
        file = Path("script.sh")
        file.touch()
        file.write_text("$SANDBOX_ROOT\n")

        shell.sendline("bash script.sh")
        shell.expect(str(Path(".").absolute()))


class TestParentChild:
    @pytest.fixture(autouse=True)
    def setup(self, mock_exit, sandbox, prompt, init):
        pass

    def test_init(self, envo_prompt, init_child_env):
        from envo.comm.test_utils import spawn

        os.chdir("child")

        s = spawn("envo test")
        nested_prompt = envo_prompt.replace(b"sandbox", b"sandbox.child")

        s.expect(nested_prompt)

    def test_child_parent_prompt(self, init_child_env):
        from envo.comm.test_utils import spawn

        os.chdir("child")

        s = spawn("envo test")
        s.expect(r"🛠\(sandbox.child\).*".encode("utf-8"))

    def test_hot_reload(self, envo_prompt, init_child_env):
        from envo.comm.test_utils import spawn

        os.chdir("child")

        s = spawn("envo test")
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
        from envo.comm.test_utils import spawn

        Path("__init__.py").touch()
        os.chdir("child")
        Path("__init__.py").touch()

        s = spawn("envo test")
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
        from envo.comm.test_utils import spawn

        root_dir = Path(".").absolute()

        os.chdir(root_dir / "sandbox/sandbox")

        s = spawn("envo test")
        s.sendline('"sandbox.sandbox.sandbox" in $PROMPT')
        s.expect("True")
