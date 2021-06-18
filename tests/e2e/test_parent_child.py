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

        utils.replace_in_code('name: str = "child"', 'name: str = "ch"')

        e.expected.pop()
        e.prompt(name=r"child").eval()

        e.expected.pop()
        e.prompt(name=r"ch").eval()

        shell.exit()
        e.exit().eval()

    def test_hot_reload_parent(self, shell, init_child_env):
        utils.add_definition("self.attr = 'Cake'")
        utils.add_command("""
        @command
        def get_attr(self):
            print(self.attr)
        """)

        os.chdir("child")

        e = shell.start()
        e.prompt(name=r"child").eval()
        shell.sendline("get_attr")
        e.output(r"Cake\n")
        e.prompt(name=r"child").eval()

        utils.replace_in_code("self.attr = 'Cake'", "self.attr = 'Super Cake'", "../env_test.py")
        shell.envo.wait_until_ready()
        shell.sendline("get_attr")
        e.output(r"Super Cake\n")
        e.prompt(name=r"child").eval()

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
