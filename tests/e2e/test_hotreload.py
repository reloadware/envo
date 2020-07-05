import shutil

import pytest

from tests.e2e import utils
import os
from time import sleep
from pathlib import Path


from tests.e2e.utils import PromptState


class TestHotReload(utils.TestBase):
    def test_hot_reload(self, shell):
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING, name=r"(new|sandbox)").eval()

        new_content = Path("env_comm.py").read_text().replace("sandbox", "new")
        Path("env_comm.py").write_text(new_content)

        e.reloaded()

        e.prompt(name="new").eval()

        shell.exit()
        e.exit().eval()

    @pytest.mark.flaky(reruns=10)
    @pytest.mark.timeout(6)
    def test_old_envs_gone(self, shell):
        e = shell.expecter
        e.prompt().eval()
        # wait a bit so envs are loaded

        sleep(0.4)

        shell.sendline("$SANDBOX_STAGE")
        e.output(r"'test'\n")

        e.prompt(PromptState.MAYBE_LOADING, name=r"new")
        new_content = Path("env_comm.py").read_text().replace("sandbox", "new")
        Path("env_comm.py").write_text(new_content)

        e.reloaded()
        e.prompt(name="new").eval()

        shell.sendline("$NEW_STAGE")
        e.output(r"'test'\n")
        e.prompt(name=r"new").eval()

        shell.sendline("$SANDBOX_STAGE")
        e.output(".*Unknown environment variable.*")
        e.prompt(name="new").eval()

        shell.exit()
        e.exit().eval()

    def test_from_child_dir(self, shell):
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        Path("./test_dir").mkdir()
        os.chdir("./test_dir")

        utils.trigger_reload(Path("../env_comm.py"))
        e.reloaded()

        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_new_python_files(self, shell):
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()
        Path("./test_dir").mkdir()

        utils.replace_in_code(
            "watch_files: Tuple[str, ...] = ()", 'watch_files: Tuple[str, ...] = ("test_dir/**/*.py", "test_dir/*.py")',
        )
        e.reloaded()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        file = Path("./test_dir/some_src_file.py")
        file.touch()
        e.reloaded("test_dir/some_src_file.py")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        file.write_text("test = 1")
        e.reloaded("test_dir/some_src_file.py")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        shell.exit()
        e.exit().eval()

    def test_delete_watched_file(self, shell):
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        utils.replace_in_code(
            "watch_files: Tuple[str, ...] = ()", 'watch_files: Tuple[str, ...] = ("*.py")',
        )
        e.reloaded()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        file = Path("some_src_file.py")
        file.touch()
        e.reloaded("some_src_file.py")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        file.unlink()

        shell.exit()
        e.exit().eval()

    def test_delete_watched_directory(self, shell):
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        directory = Path("./test_dir")
        directory.mkdir()

        Path("./test_dir/some_file.py").touch()
        utils.replace_in_code(
            "watch_files: Tuple[str, ...] = ()", 'watch_files: Tuple[str, ...] = ("test_dir/**/*.py", "test_dir/*.py")',
        )
        e.reloaded()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        shutil.rmtree(directory, ignore_errors=True)

        shell.exit()
        e.exit().eval()

    def test_ignored_files(self, shell):
        e = shell.expecter
        e.prompt(PromptState.MAYBE_LOADING).eval()

        Path("./test_dir").mkdir()
        utils.replace_in_code(
            "watch_files: Tuple[str, ...] = ()", 'watch_files: Tuple[str, ...] = ("test_dir/**/*.py",)',
        )
        e.reloaded()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        utils.replace_in_code(
            "ignore_files: Tuple[str, ...] = ()", 'ignore_files: Tuple[str, ...] = ("test_dir/ignored_file.py",)',
        )
        e.reloaded()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        ignored_file = Path("./test_dir/ignored_file.py")
        watched_file = Path("./test_dir/watched_file.py")
        watched_file.touch()
        e.reloaded("test_dir/watched_file.py")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        watched_file.write_text("test = 1")
        e.reloaded("test_dir/watched_file.py")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        ignored_file.touch()

        shell.exit()
        e.exit().eval()

    def test_error(self, shell):
        sleep(1)
        e = shell.expecter

        utils.replace_in_code("# Declare your variables here", "test_var: int")

        e.output(r'Variable "sandbox\.test_var" is unset!\n')
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        e.reloaded()
        e.output(r'Variable "sandbox\.test_var" is unset!\n')
        e.prompt(PromptState.EMERGENCY).eval()

        e.expected.pop()
        e.expected.pop()

        utils.replace_in_code("test_var: int", "# Declare your variables here")
        e.prompt(PromptState.MAYBE_LOADING).eval()
        e.reloaded()

        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_few_times_in_a_row_quick(self, shell):
        e = shell.expecter
        e.prompt().eval()

        for i in range(5):
            sleep(0.2)
            utils.trigger_reload()

        e.reloaded(times=5)

        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_if_reproductible(self):
        os.environ["PATH"] = "/already_existing_path:" + os.environ["PATH"]

        utils.add_declaration("path: Raw[str]")
        utils.add_definition(
            """
            import os
            self.path = os.environ["PATH"]
            self.path = "/some_path:" + self.path
            """
        )

        shell = utils.shell()
        e = shell.expecter
        e.prompt().eval()

        utils.trigger_reload()
        sleep(0.2)
        utils.trigger_reload()
        sleep(0.2)
        utils.trigger_reload()
        sleep(0.2)

        shell.sendline("print($PATH)")
        sleep(0.5)

        e.output(r"\['/some_path', '/already_existing_path'.*\]\n")
        e.prompt()

        shell.exit()
        e.exit().eval()

    def test_shouldnt_reload_on_new_shell(self):
        s1 = utils.shell()
        e = s1.expecter

        e.prompt().eval()
        s2 = utils.shell()

        s1.log()
        e.prompt().eval()

        s2.exit()
        s2.expecter.prompt().exit().eval()
        s1.exit()
        e.exit().eval()

    def test_not_reloading_during_command(self, shell):
        e = shell.expecter
        e.prompt().eval()
        sleep(0.5)
        shell.sendline('sleep 3 && print("command_test")')
        sleep(0.5)
        utils.trigger_reload()
        utils.trigger_reload()
        utils.trigger_reload()

        e.output("command_test\n")
        e.prompt(PromptState.MAYBE_LOADING).eval()
        e.reloaded(times=1)

        e.prompt()

        shell.exit()
        e.exit().eval()
