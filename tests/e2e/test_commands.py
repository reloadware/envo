import os
from pathlib import Path
from subprocess import CalledProcessError

import pexpect
from pytest import raises

from tests.e2e import utils


class TestCommands(utils.TestBase):
    def test_command_simple_case(self, shell):
        utils.add_flake_cmd()
        utils.add_mypy_cmd()

        e = shell.start()

        e.prompt().eval()

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
            @command
            def flake(self) -> None:
                print("flake good")
            """
        )

        child_dir = Path("child_dir")
        child_dir.mkdir()

        os.chdir(str(child_dir))

        e = shell.start()

        e.prompt().eval()

        shell.sendline("flake")
        e.output(r"flake good\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_cmd_execution_with_args(self, shell):
        utils.add_flake_cmd()
        e = shell.start()

        e.prompt().eval()

        shell.sendline('flake("dd")')
        e.output(r"Flake all gooddd\n'Flake return value'\n").prompt().eval()

        shell.sendline("flake dd")
        e.output(r"Flake all gooddd\nFlake return value\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_single_command(self):
        s = utils.run("""envo test -c "print('teest')" """)
        assert s == "teest\r\n\r\r\n\x1b[0m"

    def test_single_command_fail(self):
        with raises(CalledProcessError) as e:
            s = utils.run("""envo test -c "import sys;print('some msg');sys.exit(2)" """)
        assert e.value.returncode == 2
        assert e.value.stdout == b"some msg\r\n\r\r\n\x1b[0m"
        assert e.value.stderr == b""

        with raises(CalledProcessError) as e:
            s = utils.run("""envo test -c "cat /home/non_existend_file" """)
        assert e.value.returncode == 1
        assert e.value.stdout == b"some msg\r\n\r\r\n\x1b[0m"
        assert e.value.stderr == b""

    def test_single_command_command_fail(self):
        utils.add_command(
            """
            @command
            def flake(self) -> None:
                run("flaake . | tee flake.txt")
            """
        )

        s = utils.run("""envo test -c "flake" """)
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 127

    def test_single_command_command_fail_traceback(self):
        utils.add_command(
            """
            @command
            def some_cmd(self) -> None:
                a = 1/0
                return a
            """
        )

        s = utils.run("""envo test -c "some_cmd" """)
        s.expect(r".*Traceback .*ZeroDivisionError: division by zero")
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 1

    def test_headless_error(self):
        s = utils.run("""envo some_env -c "print('test')" """)
        s.expect(pexpect.EOF)
        s.close()
        assert s.exitstatus == 1

    def test_single_command_fire(self):
        utils.add_flake_cmd()
        res = utils.single_command("flake")

        assert res == "Flake all good\r\nFlake return value\r\n"

    def test_envo_run(self):
        utils.add_flake_cmd(file=Path("env_comm.py"))
        res = utils.envo_run("flake")

        assert res == "Flake all good\r\nFlake return value\r\n"

    def test_env_variables_available_in_run(self, shell):
        utils.add_declaration("test_var: Raw[str]")
        utils.add_definition('self.test_var = "test_value"')
        utils.add_command(
            """
            @command
            def print_path(self) -> None:
                run("echo $TEST_VAR")
            """
        )
        e = shell.start()
        e.prompt().eval()

        shell.sendline("print_path")
        e.output(r"test_value\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_namespaces(self, shell):
        namespace_name = "test_namespace"
        utils.add_namespace(namespace_name, file=Path("env_test.py"))
        utils.add_flake_cmd(
            namespace=namespace_name,
            message="Namespaced flake",
            file=Path("env_test.py"),
        )
        utils.add_flake_cmd(file=Path("env_comm.py"))
        utils.add_mypy_cmd(namespace=namespace_name, file=Path("env_test.py"))

        e = shell.start()

        e.prompt().eval()

        shell.sendline("flake")
        e.output(r"Flake all good\nFlake return value\n").prompt().eval()

        shell.sendline("flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("test_namespace.flake")
        e.output(r"Namespaced flake\nFlake return value\n").prompt().eval()

        shell.sendline("test_namespace.flake()")
        e.output(r"Namespaced flake\n'Flake return value'\n").prompt().eval()

        shell.sendline("mypy")
        e.output(
            r".*mypy: error: Missing target module, package, files, or command.\n"
        ).prompt().eval()

        shell.sendline("test_namespace.mypy")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.sendline("test_namespace.mypy()")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_namespaces_shadowing(self, shell, env_test_file, env_comm_file):
        namespace_name = "test_namespace"

        utils.add_namespace(namespace_name, file=env_test_file)
        utils.add_command(
            f"""
        @test_namespace.command
        def __some_cmd(self, test_arg: str = "") -> str:
            print("from env_test!")
            return "from env_test!"
        """,
            file=env_test_file,
        )

        utils.add_command(
            f"""
                @command
                def __some_cmd(self, test_arg: str = "") -> str:
                    print("from env_comm!")
                    return "from env_comm!"
                """,
            file=env_comm_file,
        )

        e = shell.start()

        e.prompt().eval()

        shell.sendline("test_namespace.some_cmd")
        e.output(r"from env_test!\nfrom env_test!\n").prompt().eval()

        shell.sendline("test_namespace.some_cmd()")
        e.output(r"from env_test!\n'from env_test!'\n").prompt().eval()

        shell.sendline("some_cmd")
        e.output(r"from env_comm!\nfrom env_comm!\n").prompt().eval()

        shell.sendline("some_cmd()")
        e.output(r"from env_comm!\n'from env_comm!'\n").prompt().eval()

        shell.exit()
        e.exit().eval()
