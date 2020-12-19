import os

import pytest

from envo import run
from envo.misc import is_linux, is_windows


@pytest.mark.skipif(not is_linux(), reason="Platform specific")
class TestLinuxRun:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        pass

    def test_run_simple_echo(self, capsys):
        result = run('echo "test"', print_output=False)
        assert result == "test\n"
        assert capsys.readouterr().out == ""

    def test_run_simple_echo_print(self, capsys):
        result = run('echo "test"', print_output=True)
        assert capsys.readouterr().out == "test\n"
        assert result == "test\n"

    def test_run_multiple_results(self, capsys):
        result = run(
            """
        export VAR1=123
        echo "test"
        echo "test$VAR1"
        """
        )
        assert result == "test\ntest123\n"

        assert capsys.readouterr().out == "test\ntest123\n"

    def test_exceptions(self, capsys):
        with pytest.raises(SystemExit) as e:
            run(
                """
                echo "test1"
                echo "throws error" && missing_command
                echo "test2"
                """
            )

        out, err = capsys.readouterr()

        assert "missing_command: command not found\n" in out
        assert e.value.code == 127

    def test_multine_command(self):
        result = run(
            """
            export VAR1=123
            echo "test \\
            blabla"
            echo "test\\
             $VAR1"
            """
        )
        assert result == "test blabla\ntest123\n"

    def test_ignore_errors(self):
        result = run("""non_existend_command""", ignore_errors=True)
        assert "non_existend_command: command not found" in result

    def test_pipefail(self):
        with pytest.raises(SystemExit) as e:
            result = run("""non_existend_command | grep command""")

        assert e.value.code == 1


@pytest.mark.skipif(not is_windows(), reason="Platform specific")
class TestWindowsRun:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        pass

    def test_run_simple_echo(self, capsys):
        result = run('echo "test"', print_output=False)
        assert result == '\\"test\\"\r\n'
        assert capsys.readouterr().out == ""

    def test_run_simple_echo_print(self, capsys):
        result = run('echo "test"', print_output=True)
        assert capsys.readouterr().out == '\\"test\\"\r\n'
        assert result == '\\"test\\"\r\n'

    def test_run_multiple_results(self, capsys):
        result = run(
            """
            ECHO "test"
            ECHO "test2"
        """
        )
        assert result == '\\"test\\" \r\n\\"test2\\"\r\n'
        assert capsys.readouterr().out == '\\"test\\" \r\n\\"test2\\"\r\n'

    def test_exceptions(self, capsys):
        with pytest.raises(SystemExit) as e:
            run("missing_command")

        out, err = capsys.readouterr()

        assert "'missing_command' is not recognized" in out
        assert e.value.code == 1

    def test_ignore_errors(self):
        result = run("""non_existend_command""", ignore_errors=True)
        assert "'non_existend_command' is not recognized" in result
