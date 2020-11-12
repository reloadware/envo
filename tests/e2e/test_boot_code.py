from pathlib import Path
from time import sleep

from tests.e2e import utils


class TestBootCode(utils.TestBase):
    def test_imports(self, shell):
        boot = ["import math"]
        utils.add_boot(boot)
        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline("math")
        e.output(r"<module 'math' \(built-in\)>\n").prompt().eval()

        shell.exit()
        e.exit().eval()
