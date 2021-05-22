from tests.e2e import utils


class TestCommands(utils.TestBase):
    def test_verbose(self, shell):
        utils.replace_in_code("verbose_run: bool = False", "verbose_run: bool = True")

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
        e.prompt().eval()

        # remove
        utils.replace_in_code("verbose_run: bool = True", "verbose_run: bool = False")
        shell.envo.wait_until_ready()

        shell.sendline("cmd")
        e.output(r"test output\n")
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
