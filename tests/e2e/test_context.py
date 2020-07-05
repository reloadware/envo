from pathlib import Path
from time import sleep

from tests.e2e import utils


class TestContext(utils.TestBase):
    def test_simple_context(self):
        context = {
            "str_var": "str test value",
            "int_var": 8,
            "dict_var": {"nested_var": "some nested value"},
        }
        utils.add_context(context)
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        s.sendline("print(str_var)")
        e.output(r"str test value\n").prompt().eval()

        s.sendline("print(int_var)")
        e.output(r"8\n").prompt().eval()

        s.sendline('print(dict_var["nested_var"])')
        e.output(r"some nested value\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_multiple_contexts(self):
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
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        s.sendline("print(str_var1)")
        e.output(r"str test1 value\n").prompt().eval()

        s.sendline("print(int_var1)")
        e.output(r"8\n").prompt().eval()

        s.sendline("print(str_var2)")
        e.output(r"str test2 value\n").prompt().eval()

        s.sendline("print(int_var2)")
        e.output(r"28\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_contexts_inheritance(self):
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
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        s.sendline("print(str_var1)")
        e.output(r"str test1 new value\n").prompt().eval()

        s.sendline("print(int_var1)")
        e.output(r"8\n").prompt().eval()

        s.sendline("print(str_var2)")
        e.output(r"str test2 value\n").prompt().eval()

        s.sendline("print(int_var2)")
        e.output(r"28\n").prompt().eval()

        s.sendline("print(other_var)")
        e.output(r"other var value\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_slow_context(self):
        utils.add_command(
            """
            @context
            def some_context(self) -> Dict[str, Any]:
                from time import sleep
                sleep(2)
                return {"slow_var": "slow var value"}
            """
        )
        s = utils.shell()
        e = s.expecter

        e.prompt(utils.PromptState.MAYBE_LOADING).eval()

        s.sendline("print(slow_var)")
        e.output(r"xonsh:.*is not defined\n")
        e.prompt(utils.PromptState.LOADING).eval()

        sleep(1.5)

        e.expected.pop()
        e.prompt().eval()

        s.sendline("print(slow_var)")
        e.output(r"slow var value\n").prompt().eval()

        s.exit()
        e.exit().eval()
