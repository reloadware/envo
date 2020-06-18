from pathlib import Path

from pexpect import EOF

from tests.e2e import utils


class TestHooks(utils.TestBase):
    def test_precmd_print_and_modify(self):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self, command: str) -> str:
                assert command == 'print("pancake");'
                print("pre")
                return command * 2
            """
        )

        s = utils.shell()
        s.sendline('print("pancake");')
        s.expect(r"pre\r\n")
        s.expect(r"pancake\r\n")
        s.expect(r"pancake\r\n")

    def test_fun_args_validation(self, envo_prompt):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self, cmd: str) -> str:
                assert command == 'print("pancake");'
                print("pre")
                return command * 2
            """
        )
        utils.shell(
            envo_prompt.replace(
                r"🛠\(sandbox\)".encode("utf-8"),
                r"Unexpected magic function args \['cmd'\], should be \['command'\].*"
                r"pre_print\(cmd: str\) -> str.*"
                r'In file ".*".*'
                r"Line number: \d\d.*.*❌".encode("utf-8"),
            )
        )

    def test_fun_args_validation_missing_arg(self, envo_prompt):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self) -> str:
                print("test")
                return "cmd"
            """
        )
        utils.shell(
            envo_prompt.replace(
                r"🛠\(sandbox\)".encode("utf-8"),
                r"Missing magic function args \['command'\].*"
                r"pre_print\(\) -> str.*"
                r'In file ".*".*'
                r"Line number: \d\d.*.*❌".encode("utf-8"),
            )
        )

    def test_precmd_access_env_vars(self):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self, command: str) -> str:
                print(self.stage);
                return command
            """
        )

        s = utils.shell()
        s.sendline('print("pancake");')
        s.expect(r"test\r\n")
        s.expect(r"pancake\r\n")

    def test_onstdout(self):
        utils.add_hook(
            r"""
            @onstdout(cmd_regex=r"print\(.*\)")
            def on_print(self, command: str, out: str) -> str:
                assert command == 'print("pancake");print("banana")'
                return " sweet " + out
            """
        )

        s = utils.shell()
        s.sendline('print("pancake");print("banana")')
        s.expect(r" sweet pancake sweet \r\n")
        s.expect(r" sweet banana sweet \r\n")

    def test_onstderr(self):
        utils.add_hook(
            r"""
            @onstderr(cmd_regex=r"print\(.*\)")
            def post_print(self, command: str, out: str) -> str:
                print("not good :/")
                print(out)
                return ""
            """
        )

        s = utils.shell()
        s.sendline("print(1/0)")
        s.expect(r"not good :/")
        s.expect(r"ZeroDivisionError: division by zero")

    def test_post_hook_print(self):
        utils.add_hook(
            r"""
            @postcmd(cmd_regex=r"print\(.*\)")
            def post_print(self, command: str, stdout: List[str], stderr: List[str]) -> None:
                assert command == 'print("pancake");print("banana")'
                assert stderr == []
                assert stdout == ["pancake", "\n", "banana", "\n"]
                print("post")
            """
        )

        s = utils.shell()
        s.sendline('print("pancake");print("banana")')
        s.expect(r"pancake\r\n")
        s.expect(r"banana\r\n")
        s.expect(r"post\r\n")

    def test_onload_onunload_hook(self, envo_prompt):
        utils.add_hook(
            r"""
            @oncreate
            def on_create(self) -> None:
                print("on create")
            @onload
            def init_sth(self) -> None:
                print("on load")
            @onunload
            def deinit_sth(self) -> None:
                print("on unload")
            @ondestroy
            def on_destroy(self) -> None:
                print("on destroy")
            """
        )

        s = utils.shell(rb"on create.*on load.*" + envo_prompt)
        s.sendcontrol("d")
        s.expect(r"on unload")
        s.expect(r"on destroy")
        s.expect(EOF)

    def test_onload_onunload_reload(self, envo_prompt):
        utils.add_hook(
            r"""
            @onload
            def init_sth(self) -> None:
                print("on load")
            @onunload
            def deinit_sth(self) -> None:
                print("on unload")
            """
        )

        s = utils.shell(rb"on load.*" + envo_prompt)
        Path("env_comm.py").write_text(Path("env_comm.py").read_text())
        s.expect(r"on unload")
        s.expect(r"on load")
        s.sendcontrol("d")
        s.expect(r"on unload")
        s.expect(EOF)
