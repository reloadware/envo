from pathlib import Path
from time import sleep

from pytest import mark

from tests import facade
from tests.e2e import utils


class TestSecret(utils.TestBase):
    @mark.skip(reason="TODO")
    def test_basic(self, shell):
        utils.add_secret_declaration("cake: str = secret()")
        utils.add_command(
            """
        @command
        def print_cake(self) -> None:
            print(self.secrets.cake)
        """
        )
        e = shell.start(wait_until_ready=False)

        e.output(r"Warning: Password input may be echoed\.\nsandbox\.cake:").eval()
        shell.sendline("Caramel", expect=False)
        e.output(r"\n")
        e.prompt().eval()

        shell.sendline("print_cake")
        e.output(r"Caramel\n").prompt().eval()

        shell.exit()
        e.exit().eval()
