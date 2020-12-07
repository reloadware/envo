from pathlib import Path

from tests.e2e import utils


class TestEnvVariables(utils.TestBase):
    def test_nested(self, shell):
        utils.add_declaration(
            """
            @dataclass
            class Python:
                version: str
                name: str

            python: Python
            """
        )
        utils.add_definition(
            'self.python = self.Python(version="3.8.2", name="python")',
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
            @dataclass
            class Python:
                version: str
                name: str

            python: Raw[Python]
            """
        )
        utils.add_definition(
            'self.python = self.Python(version="3.8.2", name="python")',
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
            @dataclass
            class Python:
                @dataclass
                class Version:
                    major: str
                    minor: str
        
                version: Version
                name: str
        
            python: Raw[Python]
            """
        )
        utils.add_definition(
            'self.python = self.Python(version=self.Python.Version("3", "6"), name="python")',
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

    def test_verify_unset_variable(self, shell):
        utils.add_declaration("test_var: int")

        e = shell.start()
        e.output('Variable "test_var" is unset!\n')
        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()

    def test_verify_variable_undeclared(self, shell):
        utils.add_definition("self.test_var = 12")

        e = shell.start()
        e.output('Variable "test_var" is undeclared!\n')
        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()

    def test_raw_in_nested(self, shell):
        utils.add_declaration(
            """
            @dataclass
            class Python:
                version: Raw[str]

            python: Python
            """
        )
        utils.add_definition(
            'self.python = self.Python(version="3.8.2")',
            file=Path("env_test.py"),
        )

        utils.add_definition(
            """
            self.python = self.Python(version="3.8.2")
            """,
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
            @dataclass
            class Python:
                @dataclass
                class Version:
                    major: str
                    minor: str
                    raw_var: Raw[str]

                version: Version
                name: str

            python: Raw[Python]
            """
        )
        utils.add_definition(
            'self.python = self.Python(version=self.Python.Version("3", "6", "raw_value"), name="python")',
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
            @dataclass
            class Python:
                version: Raw[str]
                
            @dataclass
            class Javascript:
                version: Raw[str]

            python: Python
            javascript: Javascript
            """
        )
        utils.add_definition(
            """
            self.python = self.Python(version="3.8.2")
            self.javascript = self.Javascript(version="3.8.2")
            """,
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.output(f'Variable "version" is redefined\n')
        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()
