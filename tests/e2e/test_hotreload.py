import shutil

import pytest

from envo.e2e import ReloadTimeout
from tests.e2e import utils
import os
from time import sleep
from pathlib import Path


from tests.e2e.utils import PromptState


class TestHotReload(utils.TestBase):
    def test_hot_reload(self, shell):
        shell.start()
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING, name=r"(new|sandbox)").eval()

        new_content = Path("env_test.py").read_text().replace("sandbox", "new")
        Path("env_test.py").write_text(new_content)

        shell.envo.assert_reloaded()

        shell.exit()
        e.exit().eval()

    @pytest.mark.timeout(6)
    def test_old_envs_gone(self, shell):
        shell.start()
        e = shell.expecter
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
        shell.start()
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        Path("./test_dir").mkdir()
        shell.envo.assert_reloaded(1, "test_dir")
        shell.sendline("cd ./test_dir")

        shell.trigger_reload(Path("env_test.py"))
        shell.envo.assert_reloaded(2)

        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_new_python_files(self, shell):
        shell.start()
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()
        Path("./test_dir").mkdir()

        shell.envo.assert_reloaded(1, "test_dir")

        utils.replace_in_code(
            "watch_files: List[str] = []", 'watch_files: List[str] = ["test_dir/**/*.py", "test_dir/*.py"]',
        )
        shell.envo.assert_reloaded(2)

        file = Path("./test_dir/some_src_file.py")
        file.touch()
        shell.envo.assert_reloaded(3, "test_dir/some_src_file.py")

        file.write_text("test = 1")
        shell.envo.assert_reloaded(4, "test_dir/some_src_file.py")

        shell.exit()
        e.exit().eval()

    def test_delete_watched_file(self, shell):
        shell.start()
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        utils.replace_in_code(
            "watch_files: List[str] = []", 'watch_files: List[str] = ["*.py"]',
        )
        shell.envo.assert_reloaded(1)

        file = Path("some_src_file.py")
        file.touch()
        shell.envo.assert_reloaded(2, "some_src_file.py")

        file.unlink()
        shell.envo.assert_reloaded(3, "some_src_file.py")

        shell.exit()
        e.exit().eval()

    def test_delete_watched_directory(self, shell):
        shell.start()
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        directory = Path("./test_dir")
        directory.mkdir()

        shell.envo.assert_reloaded(1, "test_dir")

        some_file = Path("./test_dir/some_file.py")
        some_file.touch()

        utils.replace_in_code(
            "watch_files: List[str] = []", 'watch_files: List[str] = ["test_dir/**/*.py", "test_dir/*.py"]',
        )

        shell.envo.assert_reloaded(2)

        some_file.unlink()
        shell.envo.assert_reloaded(3, "test_dir/some_file.py")

        shutil.rmtree(directory, ignore_errors=True)
        shell.envo.assert_reloaded(4, "test_dir")

        shell.exit()
        e.exit().eval()

    def test_ignored_files(self, shell):
        shell.start()
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        Path("./test_dir").mkdir()

        shell.envo.assert_reloaded(1, "test_dir")

        utils.replace_in_code(
            "watch_files: List[str] = []", 'watch_files: List[str] = ["test_dir/**/*.py"]',
        )
        shell.envo.assert_reloaded(2)

        utils.replace_in_code(
            "ignore_files: List[str] = []", 'ignore_files: List[str] = ["test_dir/ignored_file.py"]',
        )
        shell.envo.assert_reloaded(3)

        ignored_file = Path("./test_dir/ignored_file.py")
        watched_file = Path("./test_dir/watched_file.py")
        watched_file.touch()

        shell.envo.assert_reloaded(4, "test_dir/watched_file.py")

        watched_file.write_text("test = 1")
        shell.envo.assert_reloaded(5, "test_dir/watched_file.py")

        ignored_file.touch()

        shell.envo.assert_reloaded(5, "test_dir/watched_file.py")

        shell.exit()
        e.exit().eval()

    def test_error(self, shell):
        shell.start()
        e = shell.expecter
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

    def test_few_times_in_a_row_quick(self, shell):
        shell.start()
        e = shell.expecter
        e.prompt().eval()

        for i in range(5):
            sleep(0.2)
            shell.trigger_reload()

        shell.envo.assert_reloaded(5)

        shell.exit()
        e.exit().eval()

    def test_if_reproductible(self, shell):
        os.environ["PATH"] = "/already_existing_path:" + os.environ["PATH"]

        utils.add_declaration("path: Raw[str]")
        utils.add_definition(
            """
            import os
            self.path = os.environ["PATH"]
            self.path = "/some_path:" + self.path
            """
        )

        shell.start()

        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        shell.trigger_reload()
        shell.trigger_reload()
        shell.trigger_reload()

        shell.sendline("print($PATH)")
        sleep(0.5)

        e.output(r"\['/some_path', '/already_existing_path'.*\]\n")
        e.prompt()

        shell.exit()
        e.exit().eval()

    def test_shouldnt_reload_on_new_shell(self, shell):
        shell.start()
        e = shell.expecter
        e.prompt().eval()

        shell2 = utils.Spawn("envo test", debug=False)
        shell2.start()
        shell2.expecter.prompt().eval()
        shell2.exit()

        shell.envo.assert_reloaded(0)

        shell.exit()
        e.exit().eval()

    def test_not_reloading_during_command(self, shell):
        shell.start()

        e = shell.expecter
        e.prompt().eval()
        sleep(0.5)
        shell.sendline('sleep 3 && print("command_test")')
        sleep(0.5)
        shell.trigger_reload()
        with pytest.raises(ReloadTimeout):
            shell.envo.assert_reloaded(1, timeout=0.2)

        shell.trigger_reload()
        with pytest.raises(ReloadTimeout):
            shell.envo.assert_reloaded(1, timeout=0.2)

        shell.trigger_reload()
        with pytest.raises(ReloadTimeout):
            shell.envo.assert_reloaded(1, timeout=0.2)

        e.output("command_test\n")
        e.prompt(PromptState.MAYBE_LOADING)
        shell.envo.assert_reloaded(1, timeout=4)

        shell.exit()
        e.exit().eval()
