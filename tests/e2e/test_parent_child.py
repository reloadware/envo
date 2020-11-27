import os
from pathlib import Path

import pytest

from tests.e2e import utils


class TestParentChild(utils.TestBase):
    def test_init(self, shell, init_child_env):
        os.chdir("child")
        shell.start()
        e = shell.expecter
        e.prompt(name=r"child").eval()

        shell.exit()
        e.exit().eval()

    def test_hot_reload(self, shell, init_child_env):
        os.chdir("child")

        shell.start()
        e = shell.expecter
        e.prompt(name=r"child").eval()

        utils.replace_in_code("child", "ch")

        e.expected.pop()
        e.prompt(name=r"child").eval()

        e.expected.pop()
        e.prompt(name=r"ch").eval()

        shell.exit()
        e.exit().eval()

    def test_same_child_names(self, shell, init_2_same_childs):
        root_dir = Path(".").absolute()
        os.chdir(root_dir / "sandbox/sandbox")

        shell.start()

        e = shell.expecter
        e.prompt(name="sandbox")

        shell.exit()
        e.exit().eval()
