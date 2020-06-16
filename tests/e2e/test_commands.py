from tests.e2e import utils
import os
from pathlib import Path

import pexpect


class TestCommands(utils.TestBase):
    def test_command_no_prop_no_glob(self, envo_prompt):
        utils.flake_cmd(prop=False, glob=False)
        utils.mypy_cmd(prop=False, glob=False)
        s = utils.shell()

        s.sendline("repr(env.flake)")
        s.expect(r"envo\.env\.Command object at")
        s.expect(envo_prompt)

        s.sendline("env.flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.mypy()")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

        s.sendline("flake")
        s.expect("not found")
        s.expect(envo_prompt)

        s.sendline("flake()")
        s.expect("NameError: name 'flake' is not defined")
        s.expect(envo_prompt)

    def test_command_prop_no_glob(self, envo_prompt):
        utils.flake_cmd(prop=True, glob=False)
        utils.mypy_cmd(prop=True, glob=False)
        s = utils.shell()

        s.sendline("repr(env.flake)")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("repr(env.mypy)")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

        s.sendline("env.flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.mypy()")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

        s.sendline("flake")
        s.expect("not found")
        s.expect(envo_prompt)

        s.sendline("flake()")
        s.expect("NameError: name 'flake' is not defined")
        s.expect(envo_prompt)

    def test_command_no_prop_glob(self, envo_prompt):
        utils.flake_cmd(prop=False, glob=True)
        utils.mypy_cmd(prop=False, glob=True)
        s = utils.shell()

        s.sendline("repr(env.flake)")
        s.expect(r"envo\.env\.Command object at")
        s.expect(envo_prompt)

        s.sendline("env.flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.mypy()")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

        s.sendline("repr(flake)")
        s.expect(r"envo\.env\.Command object at")
        s.expect(envo_prompt)

        s.sendline("flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("mypy()")
        s.expect("Mypy all good")
        s.expect(envo_prompt)

    def test_command_prop_glob(self, envo_prompt):
        utils.flake_cmd(prop=True, glob=True)
        utils.mypy_cmd(prop=False, glob=False)
        s = utils.shell()

        s.sendline("repr(env.flake)")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("env.flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("flake")
        s.expect("Flake all good")
        s.expect(envo_prompt)

        s.sendline("flake()")
        s.expect("Flake all good")
        s.expect(envo_prompt)

    def test_cmd_in_non_root_dir(self, envo_prompt):
        utils.add_command(
            """
            @command(glob=True, prop=True)
            def flake(self) -> None:
                print("flake good")
            """
        )
        s = utils.shell()

        child_dir = Path("child_dir")
        child_dir.mkdir()

        os.chdir(str(child_dir))

        s.sendline("flake")
        s.expect("flake good")
        s.expect(envo_prompt)

    def test_single_command(self):
        s = utils.spawn("""envo test -c "print('teest')" """)
        s.expect("teest")
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 0

    def test_single_command_fail(self):
        s = utils.spawn("""envo test -c "import sys;print('some msg');sys.exit(2)" """)
        s.expect("some msg")
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 2

        s = utils.spawn("""envo test -c "cat /home/non_existend_file" """)
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 1
