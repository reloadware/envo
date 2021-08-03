import os

import pytest
from pytest import raises

from envo.misc import is_linux, is_windows
from tests.facade import run, run_get


@pytest.mark.skipif(not is_linux(), reason="Platform specific")
class TestLinuxRun:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        pass

    def test_print_output_false(self, capfd):
        run('echo "test"', print_output=False, raise_on_error=False, verbose=False)
        read = capfd.readouterr()
        assert read.out == ""
        assert read.err == ""

    def test_run_simple_echo_print(self, capfd):
        run('echo "test"', print_output=True, verbose=False)
        read = capfd.readouterr()
        assert read.err == ""
        assert read.out == "test\n"

    def test_with_debug(self, capfd, env_sandbox):
        os.environ["ENVO_DEBUG"] = "True"
        run('echo "test"', print_output=True, verbose=False)
        read = capfd.readouterr()
        assert read.err == ""
        assert read.out == '\x1b[34m\x1b[1mecho "test"\x1b[0m\ntest\n'

    def test_print_error_false(self, capfd):
        with raises(SystemExit):
            run('echo "test" && sth', print_errors=False, verbose=False)
        assert capfd.readouterr().out == "test\n"
        assert capfd.readouterr().err == ""

    def test_run_multiple_results(self, capfd):
        result = run_get(
            """
        export VAR1=123
        echo "test"
        echo "test$VAR1"
        """
        )
        assert result.stdout == "test\ntest123\n"

    def test_exceptions(self, capfd):
        with pytest.raises(SystemExit) as e:
            run(
                """
                echo "test1"
                echo "throws error" && missing_command
                echo "test2"
                """
            )

        out, err = capfd.readouterr()

        assert "missing_command: command not found\n" in err
        assert e.value.code == 127

    def test_multine_command(self):
        result = run_get(
            """
            export VAR1=123
            echo "test \\
            blabla"
            echo "test\\
             $VAR1"
            """
        )
        assert result.stdout == "test blabla\ntest123\n"

    def test_ignore_errors(self):
        run("""non_existend_command""", raise_on_error=False)

    def test_pipefail(self):
        with pytest.raises(SystemExit) as e:
            run("""non_existend_command | grep command""")

        assert e.value.code == 1


@pytest.mark.skipif(not is_windows(), reason="Platform specific")
class TestWindowsRun:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        pass

    def test_run_simple_echo(self, capfd):
        result = run('echo "test"', print_output=False)
        assert result == '\\"test\\"\r\n'
        assert capfd.readouterr().out == ""

    def test_run_simple_echo_print(self, capfd):
        result = run('echo "test"', print_output=True)
        assert capfd.readouterr().out == '\\"test\\"\r\n'
        assert result == '\\"test\\"\r\n'

    def test_run_multiple_results(self, capfd):
        result = run(
            """
            ECHO "test"
            ECHO "test2"
        """
        )
        assert result == '\\"test\\" \r\n\\"test2\\"\r\n'
        assert capfd.readouterr().out == '\\"test\\" \r\n\\"test2\\"\r\n'

    def test_exceptions(self, capfd):
        with pytest.raises(SystemExit) as e:
            run("missing_command")

        out, err = capfd.readouterr()

        assert "'missing_command' is not recognized" in out
        assert e.value.code == 1

    def test_ignore_errors(self):
        result = run("""non_existend_command""", ignore_errors=True)
        assert "'non_existend_command' is not recognized" in result
