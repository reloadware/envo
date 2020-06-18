from pathlib import Path
from time import sleep

import pytest

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

        s.sendline("print(str_var)")
        s.expect(r"str test value")

        s.sendline("print(int_var)")
        s.expect(r"8")

        s.sendline('print(dict_var["nested_var"])')
        s.expect(r"some nested value")

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

        s.sendline("print(str_var1)")
        s.expect(r"str test1 value")

        s.sendline("print(int_var1)")
        s.expect(r"8")

        s.sendline("print(str_var2)")
        s.expect(r"str test2 value")

        s.sendline("print(int_var2)")
        s.expect(r"28")

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

        s.sendline("print(str_var1)")
        s.expect(r"str test1 new value")

        s.sendline("print(int_var1)")
        s.expect(r"8")

        s.sendline("print(str_var2)")
        s.expect(r"str test2 value")

        s.sendline("print(int_var2)")
        s.expect(r"28")

        s.sendline("print(other_var)")
        s.expect(r"other var value")

    def test_slow_context(self, envo_prompt):
        utils.add_command(
            """
            @context
            def some_context(self) -> Dict[str, Any]:
                from time import sleep
                sleep(1)
                return {"slow_var": "slow var value"}
            """
        )
        s = utils.shell("⏳".encode("utf-8") + envo_prompt)

        s.sendline("print(slow_var)")
        s.expect(r"is not defined")

        sleep(1)

        s.sendline("print(slow_var)")
        s.expect(r"slow var value")

        from pexpect import TIMEOUT

        with pytest.raises(TIMEOUT):
            s.expect("⏳".encode("utf-8") + envo_prompt, timeout=0.1)

        s.expect(envo_prompt)
