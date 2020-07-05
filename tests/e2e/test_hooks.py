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
        e = s.expecter

        e.prompt().eval()

        s.sendline('print("pancake");')
        e.output(r"pre\n")
        e.output(r"pancake\n")
        e.output(r"pancake\n")
        e.prompt().eval()

        s.exit()
        e.exit().eval()

    def test_fun_args_validation(self):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self, cmd: str) -> str:
                assert command == 'print("pancake");'
                print("pre")
                return command * 2
            """
        )
        s = utils.shell()
        e = s.expecter

        e.output(
            (
                r"Unexpected magic function args \['cmd'\], should be \['command'\].*"
                r"pre_print\(cmd: str\) -> str.*"
                r'In file ".*".*'
                r"Line number: \d\d\n"
            )
        )
        e.prompt(utils.PromptState.EMERGENCY).eval()

        s.exit()
        e.exit().eval()

    def test_fun_args_validation_missing_arg(self):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self) -> str:
                print("test")
                return "cmd"
            """
        )
        s = utils.shell()
        e = s.expecter

        e.output(
            (
                r"Missing magic function args \['command'\].*"
                r"pre_print\(\) -> str.*"
                r'In file ".*".*'
                r"Line number: \d\d\n"
            )
        )

        e.prompt(utils.PromptState.EMERGENCY).eval()

        s.exit()
        e.exit().eval()

    def test_precmd_not_matching_not_run(self):
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"some_cmd\(.*\)")
            def pre_cmd(self, command: str) -> str:
                print("pre")
                return command
            """
        )

        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        s.sendline('print("pancake");')
        e.output(r"pancake\n").prompt().eval()

        s.exit()
        e.exit().eval()

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
        e = s.expecter

        e.prompt().eval()

        s.sendline('print("pancake");')
        e.output(r"test\npancake\n").prompt().eval()

        s.exit()
        e.exit().eval()

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
        e = s.expecter

        e.prompt().eval()

        s.sendline('print("pancake");print("banana")')
        e.output(r" sweet pancake sweet\n sweet banana sweet\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_onstderr(self):
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

        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        s.sendline("print(1/0)")
        e.output(r"not good :/\nxonsh:.*ZeroDivisionError: division by zero\npost command test\n").prompt().eval()

        s.exit()
        e.exit().eval()

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
        e = s.expecter

        e.prompt().eval()

        s.sendline('print("pancake");print("banana")')
        e.output(r"pancake\nbanana\npost\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_onload_onunload_hook(self):
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

        s = utils.shell()
        e = s.expecter

        e.output(r"on load\n")
        e.output(r"on create\n")
        e.prompt().eval()

        s.exit()
        e.exit()
        e.output(r"on destroy\n")
        e.output(r"on unload")
        e.eval()

    def test_onload_onunload_reload(self):
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

        s = utils.shell()
        e = s.expecter

        e.output(r"on load\n")
        e.prompt().eval()

        s.exit()
        e.exit()
        e.output(r"on unload").eval()
