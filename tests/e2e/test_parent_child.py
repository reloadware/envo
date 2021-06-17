import os
from pathlib import Path

from tests.e2e import utils


class TestParentChild(utils.TestBase):
    def test_init(self, shell, init_child_env):
        os.chdir("child")
        e = shell.start()
        e.prompt(name=r"child").eval()

        shell.exit()
        e.exit().eval()

    def test_hot_reload(self, shell, init_child_env):
        os.chdir("child")

        e = shell.start()
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

        e = shell.start()
        e.prompt(name="sandbox")

        shell.exit()
        e.exit().eval()

    def test_super_uses_self(self, shell):
        utils.add_declaration("var: str", Path("env_comm.py"))
        utils.add_definition("self.var = 'cake'", Path("env_comm.py"))

        utils.add_command(
            """
            @command
            def cmd(self) -> None:
                print(self.var)
            """,
            Path("env_comm.py"),
        )

        utils.add_definition("self.var = 'super cake'", Path("env_test.py"))
        utils.add_command(
            """
            @command
            def cmd(self) -> None:
                super().cmd()
            """,
            Path("env_test.py"),
        )

        e = shell.start()

        e.prompt()

        shell.sendline("cmd")
        e.output(r"super cake\n").prompt().eval()

        shell.exit()
        e.exit().eval()
