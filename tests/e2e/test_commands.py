from tests.e2e import utils
import os
from pathlib import Path

import pexpect


class TestCommands(utils.TestBase):
    def test_command_no_prop_no_glob(self):
        utils.flake_cmd(prop=False, glob=False)
        utils.mypy_cmd(prop=False, glob=False)
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()
        s.sendline("repr(env.flake)")
        e.output(r"'Command\(name=\\'flake\\', type=\\'command\\'.*?\n").prompt().eval()

        s.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("env.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        s.sendline("flake")
        e.output(r".*not found.*\n").prompt().eval()

        s.sendline("flake()")
        e.output(r".*NameError: name 'flake' is not defined\n").prompt().eval()
        s.exit()
        e.exit().eval()

    def test_decorator_kwargs_validation(self):
        utils.add_command(
            """
            @command(unexistent_arg1=False, unexistent_arg2=False, prop=True)
            def flake(self) -> None:
                print("Flake all good")
                return "Flake return value"
            """
        )

        s = utils.shell()
        e = s.expecter

        e.output("Traceback.*got an unexpected keyword argument.*\n")
        e.prompt(utils.PromptState.EMERGENCY).eval(4)

        s.exit()
        e.exit().eval()

    def test_command_prop_no_glob(self):
        utils.flake_cmd(prop=True, glob=False)
        utils.mypy_cmd(prop=True, glob=False)
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()
        s.sendline("repr(env.flake)")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("repr(env.mypy)")
        e.output(r"Mypy all good\n''\n").prompt().eval()

        s.sendline("env.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        s.sendline("flake")
        e.output(r".*not found.*\n").prompt().eval()

        s.sendline("flake()")
        e.output(r".*NameError: name 'flake' is not defined\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_command_no_prop_glob(self):
        utils.flake_cmd(prop=False, glob=True)
        utils.mypy_cmd(prop=False, glob=True)
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()
        s.sendline("repr(env.flake)")
        e.output(r"'Command\(name=\\'flake\\', type=\\'command\\'.*?\n").prompt().eval()

        s.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("env.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        s.sendline("repr(mypy)")
        e.output(r"'Command\(name=\\'mypy\\', type=\\'command\\'.*?\n").prompt().eval()
        s.sendline("flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_command_prop_glob(self):
        utils.flake_cmd(prop=True, glob=True)
        utils.mypy_cmd(prop=True, glob=True)
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        s.sendline("repr(env.flake)")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("repr(env.mypy)")
        e.output(r"Mypy all good\n''\n").prompt().eval()

        s.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("env.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        s.sendline("flake")
        e.output(r"Flake all good\nFlake return value\n").prompt().eval()

        s.sendline("mypy")
        e.output(r"Mypy all good\n").prompt().eval()

        s.sendline("flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_cmd_in_non_root_dir(self):
        utils.add_command(
            """
            @command(glob=True, prop=True)
            def flake(self) -> None:
                print("flake good")
            """
        )
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        child_dir = Path("child_dir")
        child_dir.mkdir()

        os.chdir(str(child_dir))

        s.sendline("flake")
        e.output(r"flake good\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_cmd_without_args(self):
        utils.add_command(
            """
            @command
            def flake(self) -> None:
                print("Flake all good")
                return "Flake return value"
            """
        )
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        s.sendline("repr(env.flake)")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("env.flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.sendline("flake")
        e.output(r"Flake all good\nFlake return value\n").prompt().eval()

        s.sendline("flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        s.exit()
        e.exit().eval()

    def test_cmd_execution_with_args(self):
        utils.flake_cmd(prop=True, glob=True)
        s = utils.shell()
        e = s.expecter

        e.prompt().eval()

        s.sendline('flake("dd")')
        e.output(r"Flake all gooddd\n'Flake return value'\n").prompt().eval()

        s.exit()
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

    def test_cant_find_env(self):
        utils.flake_cmd(prop=True, glob=True)
        res = utils.single_command("flake")

        assert res == "Flake all good\r\nFlake return value\r\n"
