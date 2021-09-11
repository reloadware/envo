import os
import shutil
from pathlib import Path
from time import sleep

import pytest
from flaky import flaky
from pytest import mark

from tests import facade
from tests.e2e import utils
from tests.e2e.utils import PromptState, flaky


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
        utils.replace_in_code("sandbox", "new", file="env_comm.py")
        shell.envo.assert_reloaded(path=".*env_comm\.py")

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

        utils.add_meta(
            'watch_files: List[str] = ["test_dir/*.py"]',
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

        utils.add_meta(
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

        utils.add_meta(
            'watch_files: List[str] = ["test_dir/*.py"]',
        )

        shell.envo.assert_reloaded(1)

        some_file.unlink()
        shell.envo.assert_reloaded(2, r".*test_dir/some_file\.py")

        shutil.rmtree(directory, ignore_errors=True)

        shell.exit()
        e.exit().eval()

    def test_delete_dir_with_file_inside(self, shell):
        directory = Path("./test_dir")
        directory.mkdir()

        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        utils.add_meta('watch_files: List[str] = ["*.py", "./test_dir/*.py"]')
        shell.envo.assert_reloaded(1)

        file1 = Path("./test_dir/some_src_file.py")
        file1.touch()
        shell.envo.assert_reloaded(2, r".*test_dir/some_src_file.py")

        file2 = Path("./test_dir/some_src_file_2.py")
        file2.touch()
        shell.envo.assert_reloaded(3, r".*test_dir/some_src_file_2.py")

        shutil.rmtree(directory, ignore_errors=True)
        shell.envo.assert_reloaded(4, r".*test_dir/some_src_file_?.?.py")

        shell.exit()
        e.exit().eval()

    @flaky
    def test_ignored_files(self, shell):
        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        Path("./test_dir").mkdir()

        utils.add_meta(
            'watch_files: List[str] = ["test_dir/*.py"]',
        )
        shell.envo.assert_reloaded(1)

        utils.add_meta('ignore_files: List[str] = ["test_dir/ignored_file.py"]')
        shell.envo.assert_reloaded(2)

        ignored_file = Path("./test_dir/ignored_file.py")
        watched_file = Path("./test_dir/watched_file.py")
        watched_file.touch()

        shell.envo.assert_reloaded(3, r".*test_dir/watched_file\.py")

        watched_file.write_text("test = 1")
        shell.envo.assert_reloaded(4, r".*test_dir/watched_file\.py")

        ignored_file.touch()

        with pytest.raises(facade.ReloadTimeout):
            shell.envo.assert_reloaded(5, r".*test_dir/ignored_file\.py")

        shell.exit()
        e.exit().eval()

    @mark.skip(reason="TODO")
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

    @mark.skip(reason="TODO")
    def test_parents_are_watched_in_emergency_mode(self, shell, init_child_env):
        os.chdir("child")

        file_before = Path("../env_comm.py").read_text()

        utils.add_env_declaration(
            "test_var: int = var()",
            file=Path("../env_comm.py"),
        )

        e = shell.start()
        e.output(rf'{facade.NoValueError("child.test_var", int)}\n')
        e.prompt(name=r"child", state=PromptState.EMERGENCY_MAYBE_LOADING).eval()

        e.expected.pop()
        e.expected.pop()
        sleep(1)

        Path("../env_comm.py").write_text(file_before)

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
        if facade.is_linux():
            os.environ["PATH"] = "/already_existing_path:" + os.environ["PATH"]
            utils.add_definition(
                """
                self.e.path = "/some_path:" + self.e.path
                """
            )
        if facade.is_windows():
            os.environ["PATH"] = "\\already_existing_path;" + os.environ["PATH"]
            utils.add_definition(
                """
                self.e.path = "\\\\some_path;" + self.e.path
                """
            )

        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        shell.trigger_reload()
        shell.trigger_reload()
        shell.trigger_reload()

        shell.sendline("print($PATH)")
        sleep(0.5)

        if facade.is_linux():
            e.output(r"\['/some_path', .*'/already_existing_path'.*\]\n")
        if facade.is_windows():
            e.output(r"\['\\\\some_path', .*'\\\\already_existing_path'.*\]\n")

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

    @flaky
    def test_not_reloading_during_command(self, shell):
        e = shell.start()
        e.prompt().eval()
        sleep(0.5)
        shell.sendline("from time import sleep; sleep(10)")
        e.prompt()
        shell.sendline('print("command_test")')
        sleep(1.0)
        shell.trigger_reload()
        with pytest.raises(facade.ReloadTimeout):
            shell.envo.assert_reloaded(1, timeout=0.2)

        sleep(0.1)

        shell.trigger_reload()
        with pytest.raises(facade.ReloadTimeout):
            shell.envo.assert_reloaded(1, timeout=0.2)

        e.output("command_test\n")
        e.prompt(PromptState.MAYBE_LOADING)
        shell.envo.assert_reloaded(1, timeout=10)

        shell.exit()
        e.exit().eval()
