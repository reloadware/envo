from pathlib import Path
from time import sleep

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
        shell.sendline("pwd")
        e.output(r".*sandbox/dir\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_error(self, shell):
        env_test = Path("env_test.py")
        file_before = env_test.read_text()

        boot = ["1/0"]
        utils.add_boot(boot)
        e = shell.start(wait_until_ready=False)

        e.output(r".*File.*ZeroDivisionError: division by zero\n")
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        env_test.write_text(file_before)
        sleep(1)
        e.expected.pop()
        e.expected.pop()

        e.prompt().eval()

        shell.exit()
        e.exit().eval()
