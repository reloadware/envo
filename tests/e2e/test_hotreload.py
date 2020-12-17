import os
import shutil
from pathlib import Path
from time import sleep

import pytest

from envo.e2e import ReloadTimeout
from envo.misc import is_windows, is_linux
from tests.e2e import utils
from tests.e2e.utils import PromptState


class TestHotReload(utils.TestBase):
    def test_hot_reload(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING, name=r"(new|sandbox)").eval()

        new_content = Path("env_test.py").read_text().replace("sandbox", "new")
        Path("env_test.py").write_text(new_content)

        shell.envo.assert_reloaded()

        shell.exit()
        e.exit().eval()

    @pytest.mark.timeout(6)
    def test_old_envs_gone(self, shell):
        e = shell.start()
        e.prompt().eval()

        shell.sendline("$SANDBOX_STAGE")
        e.output(r"'test'\n")

        e.prompt(PromptState.MAYBE_LOADING).eval()
        utils.replace_in_code("sandbox", "new")
        shell.envo.assert_reloaded()

        e.pop()
        e.prompt(PromptState.MAYBE_LOADING, name=r"new").eval()

        shell.sendline("$NEW_STAGE")
        e.output(r"'test'\n")
        e.prompt(name=r"new").eval()

        shell.sendline("$SANDBOX_STAGE")
        e.output(".*Unknown environment variable.*")
        e.prompt(name="new").eval()

        shell.exit()
        e.exit().eval()

    def test_from_child_dir(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        Path("./test_dir").mkdir()
        shell.sendline("cd ./test_dir")

        shell.trigger_reload(Path("env_test.py"))
        shell.envo.assert_reloaded(1)

        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_new_python_files(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()
        Path("./test_dir").mkdir()

        utils.replace_in_code(
            "watch_files: List[str] = []",
            'watch_files: List[str] = ["test_dir/**/*.py", "test_dir/*.py"]',
        )
        shell.envo.assert_reloaded(1)

        file = Path("./test_dir/some_src_file.py")
        file.touch()
        shell.envo.assert_reloaded(2, r".*test_dir/some_src_file\.py")

        file.write_text("test = 1")
        shell.envo.assert_reloaded(3, r".*test_dir/some_src_file\.py")

        shell.exit()
        e.exit().eval()

    def test_delete_watched_file(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        utils.replace_in_code(
            "watch_files: List[str] = []",
            'watch_files: List[str] = ["*.py"]',
        )
        shell.envo.assert_reloaded(1)

        file = Path("some_src_file.py")
        file.touch()
        shell.envo.assert_reloaded(2, r".*some_src_file\.py")

        file.unlink()
        shell.envo.assert_reloaded(3, r".*some_src_file\.py")

        shell.exit()
        e.exit().eval()

    def test_delete_watched_directory(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        directory = Path("./test_dir")
        directory.mkdir()

        some_file = Path("./test_dir/some_file.py")
        some_file.touch()

        utils.replace_in_code(
            "watch_files: List[str] = []",
            'watch_files: List[str] = ["test_dir/**/*.py", "test_dir/*.py"]',
        )

        shell.envo.assert_reloaded(1)

        some_file.unlink()
        shell.envo.assert_reloaded(2, r".*test_dir/some_file\.py")

        shutil.rmtree(directory, ignore_errors=True)

        shell.exit()
        e.exit().eval()

    def test_delete_dir_with_file_inside(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        utils.replace_in_code(
            "watch_files: List[str] = []",
            'watch_files: List[str] = ["*.py", "./test_dir/*.py"]',
        )
        shell.envo.assert_reloaded(1)

        directory = Path("./test_dir")
        directory.mkdir()

        file1 = Path("./test_dir/some_src_file.py")
        file1.touch()
        shell.envo.assert_reloaded(2, r".*test_dir/some_src_file\.py")

        file2 = Path("./test_dir/some_src_file_2.py")
        file2.touch()
        shell.envo.assert_reloaded(3, r".*test_dir/some_src_file_2\.py")

        shutil.rmtree(directory, ignore_errors=True)
        shell.envo.assert_reloaded(4, r".*test_dir/some_src_file_.\.py")

        shell.exit()
        e.exit().eval()

    def test_ignored_files(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        Path("./test_dir").mkdir()

        utils.replace_in_code(
            "watch_files: List[str] = []",
            'watch_files: List[str] = ["test_dir/**/*.py", "test_dir/*.py"]',
        )
        shell.envo.assert_reloaded(1)

        utils.replace_in_code(
            "ignore_files: List[str] = []",
            'ignore_files: List[str] = ["test_dir/ignored_file.py"]',
        )
        shell.envo.assert_reloaded(2)

        ignored_file = Path("./test_dir/ignored_file.py")
        watched_file = Path("./test_dir/watched_file.py")
        watched_file.touch()

        shell.envo.assert_reloaded(3, r".*test_dir/watched_file\.py")

        watched_file.write_text("test = 1")
        shell.envo.assert_reloaded(4, r".*test_dir/watched_file\.py")

        ignored_file.touch()

        with pytest.raises(ReloadTimeout):
            shell.envo.assert_reloaded(5, r".*test_dir/ignored_file\.py")

        shell.exit()
        e.exit().eval()

    def test_syntax_error(self, shell):
        utils.replace_in_code("# Declare your variables here", "1/0")

        e = shell.start()
        e.output(r".*ZeroDivisionError: division by zero\n")
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        e.expected.pop()
        e.expected.pop()

        utils.replace_in_code("1/0", "")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        shell.envo.assert_reloaded(1)

        shell.exit()
        e.exit().eval()

    def test_error(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        utils.replace_in_code("# Declare your variables here", "test_var: int")
        shell.envo.assert_reloaded(1)

        e.expected.pop()

        e.output(r'Variable "test_var" is unset!\n')
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        e.expected.pop()
        e.expected.pop()

        utils.replace_in_code("test_var: int", "# Declare your variables here")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        shell.envo.assert_reloaded(2)

        shell.exit()
        e.exit().eval()

    def test_parents_are_watched_in_emergency_mode(self, shell, init_child_env):
        os.chdir("child")

        utils.replace_in_code(
            "# Declare your variables here",
            "test_var: int",
            file=Path("../env_comm.py"),
        )

        e = shell.start()
        e.output(r'Variable "test_var" is unset!\n')
        e.prompt(name=r"child", state=PromptState.EMERGENCY_MAYBE_LOADING).eval()

        e.expected.pop()
        e.expected.pop()

        utils.replace_in_code(
            "test_var: int",
            "# Declare your variables here",
            file=Path("../env_comm.py"),
        )
        e.prompt(name=r"child", state=PromptState.MAYBE_LOADING).eval()

        shell.envo.assert_reloaded(1, path=r".*sandbox/env_comm\.py")

        shell.exit()
        e.exit().eval()

    def test_few_times_in_a_row_quick(self, shell):
        e = shell.start()
        e.prompt().eval()

        for i in range(5):
            sleep(0.2)
            shell.trigger_reload()

        shell.envo.assert_reloaded(5)

        shell.exit()
        e.exit().eval()

    def test_if_reproductible(self, shell):
        if is_linux():
            os.environ["PATH"] = f"/already_existing_path:" + os.environ["PATH"]
            utils.add_definition(
                f"""
                self.path = "/some_path:" + self.path
                """
            )
        if is_windows():
            os.environ["PATH"] = f"\\already_existing_path;" + os.environ["PATH"]
            utils.add_definition(
                f"""
                self.path = "\\\\some_path;" + self.path
                """
            )

        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        shell.trigger_reload()
        shell.trigger_reload()
        shell.trigger_reload()

        shell.sendline("print($PATH)")
        sleep(0.5)

        if is_linux():
            e.output(rf"\['/some_path', .*'/already_existing_path'.*\]\n")
        if is_windows():
            e.output(rf"\['\\\\some_path', .*'\\\\already_existing_path'.*\]\n")

        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_shouldnt_reload_on_new_shell(self, shell):
        e = shell.start()
        e.prompt().eval()

        shell2 = utils.SpawnEnvo("test", debug=False)
        shell2.start()
        shell2.expecter.prompt().eval()
        shell2.exit()

        shell.envo.assert_reloaded(0)

        shell.exit()
        e.exit().eval()

    def test_not_reloading_during_command(self, shell):
        e = shell.start()
        e.prompt().eval()
        sleep(0.5)
        shell.sendline('from time import sleep; sleep(10)')
        e.prompt()
        shell.sendline('print("command_test")')
        sleep(0.5)
        shell.trigger_reload()
        with pytest.raises(ReloadTimeout):
            shell.envo.assert_reloaded(1, timeout=0.2)

        sleep(0.1)

        shell.trigger_reload()
        with pytest.raises(ReloadTimeout):
            shell.envo.assert_reloaded(1, timeout=0.2)

        e.output("command_test\n")
        e.prompt(PromptState.MAYBE_LOADING)
        shell.envo.assert_reloaded(1, timeout=10)

        shell.exit()
        e.exit().eval()
