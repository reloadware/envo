from pathlib import Path
from time import sleep

from tests import facade
from tests.e2e import utils
from tests.e2e.utils import PromptState


class TestBootCode(utils.TestBase):
    def test_imports(self, shell):
        boot = ["import math"]
        utils.add_boot(boot)
        e = shell.start()

        e.prompt().eval()

        shell.sendline("math")
        e.output(r"<module 'math'.*\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_bash(self, shell):
        Path("dir").mkdir()
        boot = ["cd dir"]
        utils.add_boot(boot)
        e = shell.start()

        e.prompt().eval()
        if facade.is_windows():
            shell.sendline("echo %CD%")
        else:
            shell.sendline("pwd")
        if facade.is_windows():
            e.output(r".*sandbox_.*\\dir\n")
        else:
            e.output(r".*sandbox_.*/dir\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_error(self, shell):
        env_test = Path("env_test.py")
        file_before = env_test.read_text()

        boot = ["1/0"]
        utils.add_boot(boot)
        e = shell.start()

        e.output(r'.*1/0.*ZeroDivisionError.*')
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        env_test.write_text(file_before)
        sleep(1)

        e.pop()
        e.pop()

        e.prompt().eval()

        shell.exit()
        e.exit().eval()
