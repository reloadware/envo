import pytest

from tests.e2e import utils
import os
from pathlib import Path


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

    @pytest.mark.skip
    def test_child_importable(self, shell, init_child_env):
        Path("__init__.py").touch()
        os.chdir("child")
        Path("__init__.py").touch()

        shell.start()
        e = shell.expecter
        e.prompt(name=r"child").eval()

        test_script = Path("test_script.py")
        content = "import os\n"
        content += "del os.environ['ENVO_E2E_TEST']\n"
        content += "from env_test import Env\n"
        content += "env = Env()\n"
        content += 'print("ok")\n'
        test_script.write_text(content)

        shell.sendline("python3 test_script.py")
        e.output("ok\n")
        e.prompt(name=r"child").eval()

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
