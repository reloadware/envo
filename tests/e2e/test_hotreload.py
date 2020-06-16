from tests.e2e import utils
import os
import time
from pathlib import Path

import pexpect


class TestHotReload(utils.TestBase):
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
            time.sleep(0.3)
            env_comm_file.write_text(env_comm_file.read_text() + "\n")

        shell.expect(envo_prompt)

        shell.sendcontrol("d")
        shell.expect(pexpect.EOF, timeout=15)

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

        shell.sendline("print($PATH)")
        time.sleep(0.5)

        shell.expect(r"\['/some_path', '/already_existing_path'.*\]", timeout=2)
