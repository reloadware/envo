from tests.e2e import utils


class TestHooks(utils.TestBase):
    def test_precmd_print_and_modify(self, shell):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self, command: str) -> str:
                assert command == 'print("pancake");'
                print("pre")
                return command * 2
            """
        )

        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline('print("pancake");')
        e.output(r"pre\n")
        e.output(r"pancake\n")
        e.output(r"pancake\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_fun_args_validation(self, shell):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self, cmd: str) -> str:
                assert command == 'print("pancake");'
                print("pre")
                return command * 2
            """
        )
        shell.start()
        e = shell.expecter

        e.output(
            (
                r"Unexpected magic function args \['cmd'\], should be \['command'\].*"
                r"pre_print\(cmd: str\) -> str.*"
                r'In file ".*".*'
                r"Line number: \d\d\n"
            )
        )
        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()

    def test_fun_args_validation_missing_arg(self, shell):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self) -> str:
                print("test")
                return "cmd"
            """
        )
        shell.start()
        e = shell.expecter

        e.output(
            (
                r"Missing magic function args \['command'\].*"
                r"pre_print\(\) -> str.*"
                r'In file ".*".*'
                r"Line number: \d\d\n"
            )
        )

        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()

    def test_precmd_not_matching_not_run(self, shell):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"some_cmd\(.*\)")
            def pre_cmd(self, command: str) -> str:
                print("pre")
                return command
            """
        )

        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline('print("pancake");')
        e.output(r"pancake\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_precmd_access_env_vars(self, shell):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self, command: str) -> str:
                print(self.stage);
                return command
            """
        )

        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline('print("pancake");')
        e.output(r"test\npancake\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_onstdout(self, shell):
        utils.add_hook(
            r"""
            @onstdout(cmd_regex=r"print\(.*\)")
            def on_print(self, command: str, out: str) -> str:
                assert command == 'print("pancake");print("banana")'
                return " sweet " + out
            """
        )

        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline('print("pancake");print("banana")')
        e.output(r" sweet pancake sweet\n sweet banana sweet\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_onstderr(self, shell):
        utils.add_hook(
            r"""
            @onstderr(cmd_regex=r"print\(.*\)")
            def on_stderr(self, command: str, out: str) -> str:
                print("not good :/")
                return ""
            @postcmd(cmd_regex=r"print\(.*\)")
            def post_print(self, command: str, stdout: List[str], stderr: List[str]) -> None:
                assert "ZeroDivisionError: division by zero\n" in stderr
                assert stdout == ['not good :/', '\n', 'not good :/', '\n']
                print("post command test")
            """
        )

        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline("print(1/0)")
        e.output(r"not good :/\nxonsh:.*ZeroDivisionError: division by zero\npost command test\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_post_hook_print(self, shell):
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

        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline('print("pancake");print("banana")')
        e.output(r"pancake\nbanana\npost\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_onload_onunload_hook(self, shell):
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

        shell.start()
        e = shell.expecter

        e.output(r"on load\n")
        e.output(r"on create\n")
        e.prompt().eval()

        shell.exit()
        e.exit()
        e.output(r"on destroy\n")
        e.output(r"on unload")
        e.eval()

    def test_onload_onunload_reload(self, shell):
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

        shell.start()
        e = shell.expecter

        e.output(r"on load\n")
        e.prompt().eval()

        shell.exit()
        e.exit()
        e.output(r"on unload").eval()
