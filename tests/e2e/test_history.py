from time import sleep

from envo import logging
from tests.e2e import utils

UP_KEY = "\033[A"


class TestHistory(utils.TestBase):
    def test_simple_case(self, shell):
        e = shell.start()
        e.prompt().eval()

        shell.sendline("print('Hi')")
        e.output("Hi\n")
        e.prompt().eval()

        shell.send(UP_KEY, expect=False)
        e.output(r"print\(\'Hi\'\)").eval()
        shell.sendline("")

        e.output("Hi\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_separate_histories(self, shell, comm_shell):
        e = shell.start()
        e.prompt().eval()
        shell.sendline("a = 1")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()
        e = shell.start()
        e.prompt().eval()

        shell.send(UP_KEY, expect=False)
        e.output("a = 1").eval()
        shell.sendline("")
        e.prompt()
        shell.exit()
        e.exit().eval()

        # comm env
        e = comm_shell.start()
        e.prompt().eval()
        comm_shell.sendline("b = 123")
        e.prompt().eval()

        comm_shell.exit()
        e.exit().eval()
        e = comm_shell.start()
        e.prompt().eval()

        comm_shell.send(UP_KEY, expect=False)
        e.output("b = 123").eval()
        comm_shell.sendline("")
        e.prompt()
        comm_shell.exit()
        e.exit().eval()

        # back to test shell
        e = shell.start()
        e.prompt().eval()

        shell.send(UP_KEY, expect=False)
        e.output("a = 1").eval()
        shell.sendline("")
        e.prompt()
        shell.exit()
        e.exit().eval()
