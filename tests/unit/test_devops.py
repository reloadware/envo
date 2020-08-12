import os

import pytest

from envo import run


class TestRun:
    @pytest.fixture(autouse=True)
    def setup(self):
        pass

    def test_run_simple_echo(self, capsys):
        result = run('echo "test"', print_output=False)
        assert len(result) == 1
        assert result[0] == "test"
        assert capsys.readouterr().out == ""

    def test_run_simple_echo_print(self, capsys):
        result = run('echo "test"', print_output=True)
        assert capsys.readouterr().out == "test\r\n"
        assert result[0] == "test"

    def test_run_multiple_results(self, capsys):
        result = run(
            """
        export VAR1=123
        echo "test"
        echo "test$VAR1"
        """
        )
        assert len(result) == 2
        assert result[0] == "test"
        assert result[1] == "test123"

        assert capsys.readouterr().out == "test\r\ntest123\r\n"

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

        assert "missing_command: command not found\r\n" in out
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
        assert len(result) == 2
        assert result[0] == "test blabla"
        assert result[1] == "test123"

    def test_ignore_errors(self):
        result = run("""non_existend_command""", ignore_errors=True)
        assert len(result) == 1
        assert "non_existend_command: command not found" in result[0]

    def test_pipefail(self):
        with pytest.raises(SystemExit) as e:
            result = run("""non_existend_command | grep command""")

        assert e.value.code == 1
