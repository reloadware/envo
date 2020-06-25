import pytest
from pexpect import TIMEOUT

from tests.e2e import utils
import os
import time
from pathlib import Path

import pexpect


class TestHotReload(utils.TestBase):
    def test_hot_reload(self, shell, envo_prompt):
        new_content = Path("env_comm.py").read_text().replace("sandbox", "new")
        Path("env_comm.py").write_text(new_content)
        new_prompt = envo_prompt.replace(b"sandbox", b"new")
        shell.expect(new_prompt, timeout=2)

    def test_old_envs_gone(self, shell, envo_prompt):
        shell.sendline("$SANDBOX_STAGE")
        shell.expect("test")

        new_content = Path("env_comm.py").read_text().replace("sandbox", "new")
        Path("env_comm.py").write_text(new_content)
        new_prompt = envo_prompt.replace(b"sandbox", b"new")
        shell.expect(new_prompt)

        shell.sendline("$NEW_STAGE")
        shell.expect("test")

        shell.sendline("$SANDBOX_STAGE")
        shell.expect(new_prompt)

    def test_from_child_dir(self, shell, envo_prompt):
        Path("./test_dir").mkdir()
        os.chdir("./test_dir")
        time.sleep(0.1)

        new_content = Path("../env_comm.py").read_text() + "\n"
        Path("../env_comm.py").write_text(new_content)

        shell.expect(r".*changes.*env_comm\.py.*Reloading")
        shell.expect(envo_prompt)

    def test_new_python_files(self, shell, envo_prompt):
        Path("./test_dir").mkdir()
        time.sleep(0.1)

        utils.replace_in_code(
            "watch_files: Tuple[str] = ()",
            'watch_files: Tuple[str] = ("test_dir/**/*.py", "test_dir/*.py")',
        )
        shell.expect(r".*changes.*env_comm\.py.*Reloading")
        time.sleep(0.2)

        file = Path("./test_dir/some_src_file.py")
        file.touch()

        shell.expect(r".*changes.*some_src_file\.py.*Reloading")
        time.sleep(0.1)
        file.write_text("test = 1")

        shell.expect(r".*changes.*some_src_file\.py.*Reloading")
        shell.expect(envo_prompt)

    def test_ignored_files(self, shell, envo_prompt):
        Path("./test_dir").mkdir()
        time.sleep(0.1)

        utils.replace_in_code(
            "watch_files: Tuple[str] = ()",
            'watch_files: Tuple[str] = ("test_dir/**/*.py",)',
        )
        time.sleep(0.1)
        shell.expect(r".*changes.*env_comm\.py.*Reloading")
        time.sleep(0.1)
        utils.replace_in_code(
            "ignore_files: Tuple[str] = ()",
            'ignore_files: Tuple[str] = ("test_dir/ignored_file.py",)',
        )
        shell.expect(r".*changes.*env_comm\.py.*Reloading")

        ignored_file = Path("./test_dir/ignored_file.py")
        watched_file = Path("./test_dir/watched_file.py")
        time.sleep(0.5)
        watched_file.touch()
        shell.expect(r".*changes.*watched_file\.py.*Reloading")
        time.sleep(0.1)
        watched_file.write_text("test = 1")
        shell.expect(r".*changes.*watched_file\.py.*Reloading")

        time.sleep(0.1)
        ignored_file.touch()
        with pytest.raises(TIMEOUT):
            shell.expect(r".*changes.*ignored_file\.py.*Reloading")

        with pytest.raises(TIMEOUT):
            shell.expect(r".*changes.*ignored_file\.py.*Reloading")

        shell.expect(envo_prompt)

    def test_error(self, shell, envo_prompt):
        comm_file = Path("env_comm.py")
        file_before = comm_file.read_text()

        new_content = comm_file.read_text().replace(
            "# Declare your variables here", "test_var: int"
        )
        Path("env_comm.py").write_text(new_content)

        shell.expect(
            r'Reloading.*Variable "sandbox\.test_var" is unset!', timeout=5,
        )
        shell.expect("❌".encode("utf-8"))

        Path("env_comm.py").write_text(file_before)

        with pytest.raises(TIMEOUT):
            shell.expect("❌".encode("utf-8"))

        shell.expect(envo_prompt)

    def test_few_times_in_a_row_quick(self, shell, envo_prompt):
        env_comm_file = Path("env_comm.py")

        for i in range(5):
            env_comm_file.write_text(env_comm_file.read_text() + "\n")
            time.sleep(0.2)

        shell.expect(envo_prompt)
        shell.expect(envo_prompt)
        shell.expect(envo_prompt)
        shell.expect(envo_prompt)
        shell.expect(envo_prompt)

        shell.sendline("exit")
        shell.expect(pexpect.EOF)

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

    def test_shouldnt_reload_on_new_shell(self, envo_prompt):
        s1 = utils.shell()
        utils.shell()

        with pytest.raises(TIMEOUT):
            s1.expect("Reloading", timeout=0.5)
