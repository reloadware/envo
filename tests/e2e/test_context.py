from pathlib import Path
from time import sleep

from tests.e2e import utils


class TestContext(utils.TestBase):
    def test_simple_context(self, shell):
        context = {
            "str_var": "str test value",
            "int_var": 8,
            "dict_var": {"nested_var": "some nested value"},
        }
        utils.add_context(context)
        e = shell.start()

        e.prompt().eval()

        shell.sendline("print(str_var)")
        e.output(r"str test value\n").prompt().eval()

        shell.sendline("print(int_var)")
        e.output(r"8\n").prompt().eval()

        shell.sendline('print(dict_var["nested_var"])')
        e.output(r"some nested value\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_multiple_contexts(self, shell):
        context1 = {
            "str_var1": "str test1 value",
            "int_var1": 8,
        }
        utils.add_context(context1, name="context1")

        context2 = {
            "str_var2": "str test2 value",
            "int_var2": 28,
        }
        utils.add_context(context2, name="context2")

        e = shell.start()

        e.prompt().eval()

        shell.sendline("print(str_var1)")
        e.output(r"str test1 value\n").prompt().eval()

        shell.sendline("print(int_var1)")
        e.output(r"8\n").prompt().eval()

        shell.sendline("print(str_var2)")
        e.output(r"str test2 value\n").prompt().eval()

        shell.sendline("print(int_var2)")
        e.output(r"28\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_contexts_inheritance(self, shell):
        context1 = {
            "str_var1": "str test1 value",
            "int_var1": 8,
            "other_var": "other var value",
        }
        utils.add_context(context1, name="context1")

        context2 = {
            "str_var2": "str test2 value",
            "str_var1": "str test1 new value",
            "int_var2": 28,
        }
        utils.add_context(context2, name="context2", file=Path("env_test.py"))
        e = shell.start()

        e.prompt().eval()

        shell.sendline("print(str_var1)")
        e.output(r"str test1 new value\n").prompt().eval()

        shell.sendline("print(int_var1)")
        e.output(r"8\n").prompt().eval()

        shell.sendline("print(str_var2)")
        e.output(r"str test2 value\n").prompt().eval()

        shell.sendline("print(int_var2)")
        e.output(r"28\n").prompt().eval()

        shell.sendline("print(other_var)")
        e.output(r"other var value\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_slow_context(self, shell):
        utils.add_command(
            """
            @context
            def some_context(self) -> Dict[str, Any]:
                from time import sleep
                sleep(4.0)
                return {"slow_var": "slow var value"}
            """
        )
        shell.start(False)
        e = shell.expecter

        e.prompt(utils.PromptState.LOADING)

        shell.sendline("print(slow_var)")
        e.output(r"NameError: name 'slow_var' is not defined\n")
        e.prompt(utils.PromptState.MAYBE_LOADING).eval()

        e.expected.pop()
        e.prompt().eval()

        shell.sendline("print(slow_var)")
        e.output(r"slow var value\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_error_in_context(self, shell):
        utils.add_command(
            """
            @context
            def some_context(self) -> Dict[str, Any]:
                return {"var": 1/0}
            """
        )
        shell.start(False)
        e = shell.expecter

        e.prompt(utils.PromptState.MAYBE_LOADING)
        e.output(fr".*{ZeroDivisionError.__name__}.*")
        e.prompt().eval()

        shell.sendline("var")
        e.output(r".*not found.*")

        shell.exit()
        e.exit().eval()
