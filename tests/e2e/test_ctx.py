from pathlib import Path
from time import sleep

from tests import facade
from tests.e2e import utils
from tests.e2e.utils import PromptState


class TestCtx(utils.TestBase):
    def test_default(self, shell):
        utils.add_ctx_declaration("cake: str = ctx_var(default='Crepe')")
        utils.add_command(
            """
        @command
        def print_cake(self) -> None:
            print(self.ctx.cake)
        """
        )
        e = shell.start()

        e.prompt().eval()

        shell.sendline("print_cake")
        e.output(r"Crepe\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_no_default(self, shell):
        utils.add_ctx_declaration("cake: str = ctx_var()")

        utils.add_definition("self.ctx.cake = 'Crepe'")

        utils.add_command(
            """
        @command
        def print_cake(self) -> None:
            print(self.ctx.cake)
        """
        )
        e = shell.start()

        e.prompt().eval()

        shell.sendline("print_cake")
        e.output(r"Crepe\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_no_value_error(self, shell):
        utils.add_ctx_declaration("cake: str = ctx_var()")

        e = shell.start()
        e.output(rf".*{facade.NoValueError.__name__}.*{facade.NoValueError(var_name='sandbox.cake', type_=str)}.*\n")
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        shell.exit()
        e.exit().eval()

    def test_no_type_error(self, shell):
        utils.add_ctx_declaration("cake = ctx_var()")

        e = shell.start()
        e.output(rf".*{facade.NoTypeError.__name__}.*{facade.NoTypeError(var_name='sandbox.cake')}.*\n")
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        shell.exit()
        e.exit().eval()

    def test_wrong_type_error(self, shell):
        utils.add_ctx_declaration("cake_n: int = ctx_var(default='5')")

        e = shell.start()
        e.output(
            rf".*{facade.WrongTypeError.__name__}.*{facade.WrongTypeError(var_name='sandbox.cake_n', type_=int, got_type=str)}.*\n"
        )
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        shell.exit()
        e.exit().eval()

    def test_group(self, shell):
        utils.add_ctx_declaration(
            """
        class Cakeshop(CtxGroup):
            cake: str = ctx_var(default='Crepe')
        cakeshop = Cakeshop()
        """
        )

        utils.add_command(
            """
        @command
        def print_cake(self) -> None:
            print(self.ctx.cakeshop.cake)
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("print_cake")
        e.output(r"Crepe\n").prompt().eval()

        shell.exit()
        e.exit().eval()
