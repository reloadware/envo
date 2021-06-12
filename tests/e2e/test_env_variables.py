from pathlib import Path

from envo.env import NoValueError, RedefinedVarError
from tests.e2e import utils


class TestEnvVariables(utils.TestBase):
    def test_nested(self, shell):
        utils.add_declaration(
            """
            class Python(var):
                version: str = var()
                name: str = var()

            python = Python()
            """
        )
        utils.add_definition(
            """
            self.python.version = "3.8.2"
            self.python.name = "python"
            """,
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.prompt().eval()

        environ = shell.envo.get_os_environ()

        assert environ["SANDBOX_STAGE"] == "test"
        assert environ["SANDBOX_PYTHON_VERSION"] == "3.8.2"
        assert environ["SANDBOX_PYTHON_NAME"] == "python"

        shell.exit()
        e.exit().eval()

    def test_raw_nested(self, shell):
        utils.add_declaration(
            """
            class Python(var):
                version: str = var()
                name: str = var()

            python = Python(raw=True)
            """
        )
        utils.add_definition(
            """
            self.python.version = "3.8.2"
            self.python.name = "python"
            """,
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.prompt().eval()

        environ = shell.envo.get_os_environ()

        assert environ["SANDBOX_STAGE"] == "test"
        assert environ["PYTHON_VERSION"] == "3.8.2"
        assert environ["PYTHON_NAME"] == "python"

        shell.exit()
        e.exit().eval()

    def test_raw_double_nested(self, shell):
        utils.add_declaration(
            """
            class Python(var):
                class Version(var):
                    major: str = var()
                    minor: str = var()

                version = Version()
                name: str = var()

            python = Python(raw=True)
            """
        )
        utils.add_definition(
            """
            self.python.version.major = "3"
            self.python.version.minor = "6"
            self.python.name = "python"
            """,
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.prompt().eval()

        environ = shell.envo.get_os_environ()

        assert environ["SANDBOX_STAGE"] == "test"
        assert environ["PYTHON_VERSION_MINOR"] == "6"
        assert environ["PYTHON_VERSION_MAJOR"] == "3"
        assert environ["PYTHON_NAME"] == "python"

        shell.exit()
        e.exit().eval()

    def test_validate_non_optional_var_not_set(self, shell):
        utils.add_declaration("test_var: int = var(optional=False)")

        e = shell.start()

        e.output(f"{NoValueError(type_=int, var_name='sandbox.test_var')}\n")
        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()

    def test_raw_in_nested(self, shell):
        utils.add_declaration(
            """
            class Python(var):
                version: str = var(raw=True)

            python: Python = Python()
            """
        )
        utils.add_definition(
            'self.python.version = version="3.8.2"',
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.prompt().eval()

        environ = shell.envo.get_os_environ()
        assert environ["VERSION"] == "3.8.2"

        shell.exit()
        e.exit().eval()

    def test_raw_in_double_nested(self, shell):
        utils.add_declaration(
            """
            class Python(var):
                class Version(var):
                    major: str = var()
                    minor: str = var()
                    raw_var: str = var(raw=True)

                version = Version()
                name: str = var()

            python = Python()
            """
        )
        utils.add_definition(
            'self.python.version.raw_var = "raw_value"',
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.prompt().eval()

        environ = shell.envo.get_os_environ()
        assert environ["RAW_VAR"] == "raw_value"

        shell.exit()
        e.exit().eval()

    def test_raw_nested_redefined(self, shell):
        utils.add_declaration(
            """
            class Python(var):
                version: str = var(raw=True)

            class Javascript(var):
                version: str = var(raw=True)

            python = Python()
            javascript = Javascript()
            """
        )
        utils.add_definition(
            """
            self.python.version = "3.8.2"
            self.javascript.version = "3.8.2"
            """,
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.output(f'{RedefinedVarError("VERSION")}\n')
        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()
