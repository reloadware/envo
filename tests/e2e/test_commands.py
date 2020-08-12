from tests.e2e import utils
import os
from pathlib import Path

import pexpect


class TestCommands(utils.TestBase):
    def test_command_no_prop_no_glob(self, shell):
        utils.flake_cmd(prop=False, glob=False)
        utils.mypy_cmd(prop=False, glob=False)

        shell.start()
        e = shell.expecter
        e.prompt()

        shell.sendline("repr(env.flake)")
        e.output(r"""'Command\(name=\\'flake\\', type=\\'command\\'.*?\n""").prompt().eval()

        shell.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("env.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.sendline("flake")
        e.output(r".*not found.*\n").prompt().eval()

        shell.sendline("flake()")
        e.output(r".*NameError: name 'flake' is not defined\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_decorator_kwargs_validation(self, shell):
        utils.add_command(
            """
            @command(unexistent_arg1=False, unexistent_arg2=False, prop=True)
            def flake(self) -> None:
                print("Flake all good")
                return "Flake return value"
            """
        )

        shell.start()
        e = shell.expecter

        e.output("Traceback.*got an unexpected keyword argument.*\n")
        e.prompt(utils.PromptState.EMERGENCY).eval(4)

        shell.exit()
        e.exit().eval()

    def test_command_prop_no_glob(self, shell):
        utils.flake_cmd(prop=True, glob=False)
        utils.mypy_cmd(prop=True, glob=False)

        shell.start()
        e = shell.expecter

        e.prompt().eval()
        shell.sendline("repr(env.flake)")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("repr(env.mypy)")
        e.output(r"Mypy all good\n''\n").prompt().eval()

        shell.sendline("env.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.sendline("flake")
        e.output(r".*not found.*\n").prompt().eval()

        shell.sendline("flake()")
        e.output(r".*NameError: name 'flake' is not defined\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_command_no_prop_glob(self, shell):
        utils.flake_cmd(prop=False, glob=True)
        utils.mypy_cmd(prop=False, glob=True)

        shell.start()
        e = shell.expecter

        e.prompt().eval()
        shell.sendline("repr(env.flake)")
        e.output(r"""'Command\(name=\\'flake\\', type=\\'command\\'.*?\n""").prompt().eval()

        shell.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("env.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.sendline("repr(mypy)")
        e.output(r"""'Command\(name=\\'mypy\\', type=\\'command\\'.*?\n""").prompt().eval()
        shell.sendline("flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_command_prop_glob(self, shell):
        utils.flake_cmd(prop=True, glob=True)
        utils.mypy_cmd(prop=True, glob=True)

        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline("repr(env.flake)")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("repr(env.mypy)")
        e.output(r"Mypy all good\n''\n").prompt().eval()

        shell.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("env.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.sendline("flake")
        e.output(r"Flake all good\nFlake return value\n").prompt().eval()

        shell.sendline("mypy")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.sendline("flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_cmd_in_non_root_dir(self, shell):
        utils.add_command(
            """
            @command(glob=True, prop=True)
            def flake(self) -> None:
                print("flake good")
            """
        )

        child_dir = Path("child_dir")
        child_dir.mkdir()

        os.chdir(str(child_dir))

        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline("flake")
        e.output(r"flake good\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_cmd_without_args(self, shell):
        utils.add_command(
            """
            @command
            def flake(self) -> None:
                print("Flake all good")
                return "Flake return value"
            """
        )
        shell.start()
        e = shell.expecter

        e.prompt().eval()

        shell.sendline("repr(env.flake)")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("flake")
        e.output(r"Flake all good\nFlake return value\n").prompt().eval()

        shell.sendline("flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_cmd_execution_with_args(self, shell):
        utils.flake_cmd(prop=True, glob=True)
        shell.start()

        e = shell.expecter

        e.prompt().eval()

        shell.sendline('flake("dd")')
        e.output(r"Flake all gooddd\n'Flake return value'\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_single_command(self):
        s = utils.pexpect_spaw("""envo test -c "print('teest')" """)
        s.expect("teest")
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 0

    def test_single_command_fail(self):
        s = utils.pexpect_spaw("""envo test -c "import sys;print('some msg');sys.exit(2)" """)
        s.expect("some msg")
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 2

        s = utils.pexpect_spaw("""envo test -c "cat /home/non_existend_file" """)
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 1

    def test_single_command_command_fail(self):
        utils.add_command(
            """
            @command
            def flake(self) -> None:
                run("flaake . | tee flake.txt")
            """
        )

        s = utils.pexpect_spaw("""envo test -c "flake" """)
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 127

    def test_headless_error(self):
        s = utils.pexpect_spaw("""envo some_env -c "print('test')" """)
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 1

    def test_cant_find_env(self):
        utils.flake_cmd(prop=True, glob=True)
        res = utils.single_command("flake")

        assert res == "Flake all good\r\nFlake return value\r\n"

    def test_env_variables_available_in_run(self, shell):
        utils.add_plugin("VirtualEnv")
        utils.add_declaration("test_var: Raw[str]")
        utils.add_definition('self.test_var = "test_value"')
        utils.add_command(
            """
            @command
            def print_path(self) -> None:
                run("echo $TEST_VAR")
            """
        )
        shell.start()

        e = shell.expecter
        e.prompt().eval()

        shell.sendline("print_path")
        e.output(r"test_value\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()
