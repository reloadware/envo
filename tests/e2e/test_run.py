from tests import facade
from tests.e2e import utils
from tests.e2e.utils import PromptState


class TestCommands(utils.TestBase):
    def test_verbose(self, shell):
        utils.add_meta("verbose_run: bool = True")

        utils.add_command(
            """
        @command(in_root=False)
        def cmd(self) -> str:
            run(f"echo test output")
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("cmd")
        e.output(r"─+ echo test output ─+\n")
        e.output(r"test output\n")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        # remove
        utils.replace_in_code("verbose_run: bool = True", "verbose_run: bool = False")
        shell.envo.wait_until_ready()

        shell.sendline("cmd")
        e.output(r"test output\n")
        e.prompt(PromptState.MAYBE_LOADING).eval()

        shell.exit()
        e.exit().eval()

    def test_envs_persist(self, shell):
        utils.add_definition("self.e.pythonpath = 'test_dir'")
        utils.add_command(
            """
        @command(in_root=False)
        def cmd(self) -> str:
            run(f"echo $PYTHONPATH")
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("cmd")
        e.output(r"test_dir\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_background(self, shell):
        utils.add_command(
            """
        @command(in_root=False)
        def cmd(self) -> str:
            run(f"sleep 10", background=True)
            print("Finished")
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("cmd")
        e.output(r"Finished\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_multiple_cmds(self, shell):
        utils.add_command(
            """
        @command(in_root=False)
        def cmd(self) -> str:
            run(["echo test1", "echo test2"])
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("cmd")
        e.output(r"test1\ntest2\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_progress_bar(self, shell):
        utils.add_command(
            """
        @command(in_root=False)
        def cmd(self) -> str:
            run(["echo test1", "echo test2", "echo test3", "echo test4"], progress_bar="Processing", print_output=False)
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("cmd")
        e.output(r"Processing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_inject(self, shell):
        utils.add_command(
            """
        @command(in_root=False)
        def cmd(self) -> str:
            inject("print('Cake')")
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("cmd")
        e.output(r"Cake\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_inject_fail(self, shell):
        utils.add_command(
            """
        @command(in_root=False)
        def cmd(self) -> str:
            inject("failing")
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("cmd")
        if facade.is_linux():
            e.output(r".*failing: command not found.*")
        elif facade.is_darwin():
            e.output(r"xonsh: subprocess mode: command not found: failing\n")

        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_inject_fail_dot(self, shell):
        utils.add_command(
            """
        @command(in_root=False)
        def cmd(self) -> str:
            inject("failing .")
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("cmd")
        if facade.is_linux():
            e.output(r".*failing: command not found.*")
        elif facade.is_darwin():
            e.output(r"xonsh: subprocess mode: command not found: failing\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()
