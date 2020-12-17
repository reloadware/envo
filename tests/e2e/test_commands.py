import os
from pathlib import Path
from subprocess import CalledProcessError

import pexpect
from pytest import raises

from envo.misc import is_linux, is_windows
from tests.e2e import utils


class TestCommands(utils.TestBase):
    def test_command_simple_case(self, shell):
        utils.add_flake_cmd()
        utils.add_mypy_cmd()

        e = shell.start()

        e.prompt().eval()

        shell.sendline("my_flake")
        e.output(r"Flake all good\nFlake return value\n").prompt().eval()

        shell.sendline("my_mypy")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.sendline("my_flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("my_mypy()")
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

        shell.sendline('my_flake("dd")')
        e.output(r"Flake all gooddd\n'Flake return value'\n").prompt().eval()

        shell.sendline("my_flake dd")
        e.output(r"Flake all gooddd\nFlake return value\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_single_command(self):
        s = utils.run("""envo test -c "print('teest')" """)
        assert s == "teest\n"

    def test_single_command_fail(self):
        with raises(CalledProcessError) as e:
            s = utils.run("""envo test -c "import sys;print('some msg');sys.exit(2)" """)
        assert e.value.returncode == 2
        assert "some msg" in utils.clean_output(e.value.stdout)
        assert utils.clean_output(e.value.stderr) == ""

        with raises(CalledProcessError) as e:
            s = utils.run("""envo test -c "cd /home/non_existend_file" """)
        assert e.value.returncode == 1
        assert utils.clean_output(e.value.stdout) == "\n"
        assert "no such file or directory" in utils.clean_output(e.value.stderr)

    def test_single_command_command_fail(self):
        utils.add_command(
            """
            @command
            def flake(self) -> None:
                run("flaake . | tee flake.txt")
            """
        )

        with raises(CalledProcessError) as e:
            s = utils.run("""envo test -c "flake" """)

        if is_linux():
            assert e.value.returncode == 127
            assert "flaake: command not found" in utils.clean_output(e.value.stdout)
        if is_windows():
            assert e.value.returncode == 255
            assert "'flaake' is not recognized as an internal or external command" in utils.clean_output(e.value.stdout)

        assert utils.clean_output(e.value.stderr) == ""

    def test_single_command_command_fail_traceback(self):
        utils.add_command(
            """
            @command
            def some_cmd(self) -> None:
                a = 1/0
                return a
            """
        )

        with raises(CalledProcessError) as e:
            s = utils.run("""envo test -c "some_cmd" """)

        if is_linux():
            assert e.value.returncode == 1
            assert utils.clean_output(e.value.stdout) == ""
        if is_windows():
            assert e.value.returncode == 1
            assert utils.clean_output(e.value.stdout) == "\n"

        assert "ZeroDivisionError" in utils.clean_output(e.value.stderr)

    def test_headless_error(self):
        with raises(CalledProcessError) as e:
            s = utils.run("""envo some_env -c "print('test')" """)
        assert e.value.returncode == 1
        assert utils.clean_output(e.value.stdout) == ""
        assert "find any env" in utils.clean_output(e.value.stderr)

    def test_single_command_fire(self):
        utils.add_flake_cmd()
        res = utils.single_command("my_flake")

        assert res == "Flake all good\nFlake return value\n"

    def test_envo_run(self):
        utils.add_flake_cmd(file=Path("env_comm.py"))
        res = utils.envo_run("my_flake")

        assert res == "Flake all good\nFlake return value\n"

    def test_env_variables_available_in_run(self, shell):
        utils.add_declaration("test_var: Raw[str]")
        utils.add_definition('self.test_var = "test_value"')
        if is_linux():
            utils.add_command(
                """
                @command
                def print_path(self) -> None:
                    run("echo $TEST_VAR")
                """
            )
        if is_windows():
            utils.add_command(
                """
                @command
                def print_path(self) -> None:
                    run("echo %TEST_VAR%")
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

        shell.sendline("my_flake")
        e.output(r"Flake all good\nFlake return value\n").prompt().eval()

        shell.sendline("my_flake()")
        e.output(r"Flake all good\n'Flake return value'\n").prompt().eval()

        shell.sendline("test_namespace.my_flake")
        e.output(r"Namespaced flake\nFlake return value\n").prompt().eval()

        shell.sendline("test_namespace.my_flake()")
        e.output(r"Namespaced flake\n'Flake return value'\n").prompt().eval()

        shell.sendline("my_mypy")
        if is_linux():
            e.output(
                r"xonsh: subprocess mode: command not found: my_mypy\nmy_mypy: command not found\n"
            )
        if is_windows():
            e.output(
                r"xonsh: subprocess mode: command not found: my_mypy\n"
            )

        e.prompt().eval()

        shell.sendline("test_namespace.my_mypy")
        e.output(r"Mypy all good\n").prompt().eval()

        shell.sendline("test_namespace.my_mypy()")
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
