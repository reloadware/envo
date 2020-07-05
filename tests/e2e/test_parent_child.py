from tests.e2e import utils
import os
from pathlib import Path


class TestParentChild(utils.TestBase):
    def test_init(self, init_child_env):
        os.chdir("child")

        s = utils.shell()
        e = s.expecter
        e.prompt(name=r"sandbox\.child").eval()

        s.exit()
        e.exit().eval()

    def test_hot_reload(self, init_child_env):
        os.chdir("child")

        s = utils.shell()
        e = s.expecter
        e.prompt(name=r"sandbox\.child").eval()

        utils.replace_in_code("child", "ch")

        e.expected.pop()
        e.prompt(name=r"sandbox\.child").eval()

        e.expected.pop()
        e.prompt(name=r"sandbox\.ch").eval()

        utils.replace_in_code("sandbox", "sb", file=Path("../env_comm.py"))
        e.expected.pop()
        e.prompt(name=r"sb\.ch").eval()

        s.exit()
        e.exit().eval()

    def test_child_importable(self, init_child_env):
        Path("__init__.py").touch()
        os.chdir("child")
        Path("__init__.py").touch()

        s = utils.shell()
        e = s.expecter
        e.prompt(name=r"sandbox\.child").eval()

        test_script = Path("test_script.py")
        content = "from env_test import Env\n"
        content += "env = Env()\n"
        content += 'print("ok")\n'
        test_script.write_text(content)

        s.sendline("python3 test_script.py")
        e.output("ok\n")
        e.prompt(name=r"sandbox\.child")

        s.exit()
        e.exit().eval()

    def test_same_child_names(self, init_2_same_childs):
        root_dir = Path(".").absolute()
        os.chdir(root_dir / "sandbox/sandbox")

        s = utils.shell()
        e = s.expecter
        e.prompt(name="sandbox.sandbox.sandbox")

        s.exit()
        e.exit().eval()
