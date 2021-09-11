import os
from pathlib import Path

from pytest import mark

from tests import facade
from tests.e2e import utils
from tests.e2e.utils import PromptState

path_and_pythonpath = mark.parametrize("path", ["pythonpath", "path"], ids=["pythonpath", "path"])


class TestEnvVariables(utils.TestBase):
    def test_nested(self, shell):
        utils.add_env_declaration(
            """
            class Python(EnvGroup):
                version: str = env_var()
                name: str = env_var()

            python = Python()
            """
        )
        utils.add_definition(
            """
            self.e.python.version = "3.8.2"
            self.e.python.name = "python"
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
        utils.add_env_declaration(
            """
            class Python(EnvGroup):
                version: str = env_var()
                name: str = env_var()

            python = Python(raw=True)
            """
        )
        utils.add_definition(
            """
            self.e.python.version = "3.8.2"
            self.e.python.name = "python"
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
        utils.add_env_declaration(
            """
            class Python(EnvGroup):
                class Version(EnvGroup):
                    major: str = env_var()
                    minor: str = env_var()

                version = Version()
                name: str = env_var()

            python = Python(raw=True)
            """
        )
        utils.add_definition(
            """
            self.e.python.version.major = "3"
            self.e.python.version.minor = "6"
            self.e.python.name = "python"
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
        utils.add_env_declaration("test_var: int = env_var()")

        e = shell.start()

        e.output(rf"Environ errors:\n")
        e.output(f"{facade.NoValueError(type_=int, var_name='sandbox.test_var')}\n")
        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()

    def test_available_in_post_init(self, shell):
        utils.add_env_declaration("test_var: str = env_var('Cake', raw=True)")

        utils.add_method(
            """
            def post_init(self):
                import os
                env = os.environ["TEST_VAR"]
                print(env)
            """
        )

        e = shell.start()

        e.output(fr"Cake\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_optional(self, shell):
        utils.add_env_declaration("test_var: Optional[int] = env_var()")

        e = shell.start()

        e.prompt().eval()
        shell.sendline("$SANDBOX_TESTVAR")
        e.output("'None'\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_no_type(self, shell):
        utils.add_env_declaration("test_var = env_var()")

        e = shell.start()
        e.output(rf"Environ errors:\n")
        e.output(rf'{facade.NoTypeError(var_name="sandbox.test_var")}\n')
        e.prompt(PromptState.EMERGENCY_MAYBE_LOADING).eval()

        shell.exit()
        e.exit().eval()

    def test_raw_in_nested(self, shell):
        utils.add_env_declaration(
            """
            class Python(EnvGroup):
                version: str = env_var(raw=True)

            python: Python = Python()
            """
        )
        utils.add_definition(
            'self.e.python.version = version="3.8.2"',
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.prompt().eval()

        environ = shell.envo.get_os_environ()
        assert environ["VERSION"] == "3.8.2"

        shell.exit()
        e.exit().eval()

    def test_raw_in_double_nested(self, shell):
        utils.add_env_declaration(
            """
            class Python(EnvGroup):
                class Version(EnvGroup):
                    major: Optional[str] = env_var()
                    minor: Optional[str] = env_var()
                    raw_var: str = env_var(raw=True)

                version = Version()
                name: Optional[str] = env_var()

            python = Python()
            """
        )
        utils.add_definition(
            'self.e.python.version.raw_var = "raw_value"',
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.prompt().eval()

        environ = shell.envo.get_os_environ()
        assert environ["RAW_VAR"] == "raw_value"

        shell.exit()
        e.exit().eval()

    def test_raw_nested_redefined(self, shell):
        utils.add_env_declaration(
            """
            class Python(EnvGroup):
                version: str = env_var(raw=True)

            class Javascript(EnvGroup):
                version: str = env_var(raw=True)

            python = Python()
            javascript = Javascript()
            """
        )
        utils.add_definition(
            """
            self.e.python.version = "3.8.2"
            self.e.javascript.version = "3.8.2"
            """,
            file=Path("env_test.py"),
        )

        e = shell.start()
        e.output(rf"Environ errors:\n")
        e.output(f'{facade.RedefinedVarError("VERSION")}\n')
        e.prompt(utils.PromptState.EMERGENCY).eval()

        shell.exit()
        e.exit().eval()

    def test_load_env_vars(self, shell, env_sandbox):
        utils.add_meta("load_env_vars: bool = True")

        utils.add_env_declaration(
            """
            test_var: str = env_var() 
            """
        )

        os.environ["SANDBOX_TESTVAR"] = "TestValue"

        e = shell.start()
        e.prompt().eval()
        shell.sendline(f"env.e.test_var")
        e.output(r"'TestValue'\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    @path_and_pythonpath
    def test_pythonpath(self, shell, env_sandbox, path: str):
        utils.add_definition(
            f"""
            self.e.{path} = ["/home/user/path1", "/home/user/path2"]
            """
        )

        e = shell.start()
        e.prompt().eval()

        assert shell.envo.get_os_environ()[path.upper()] == "/home/user/path1:/home/user/path2"

        shell.exit()
        e.exit().eval()

    @path_and_pythonpath
    def test_pythonpath_append(self, shell, env_sandbox, path: str):
        test_path = "/home/user/path1"
        utils.add_definition(
            f"""
            self.e.{path}.append("{test_path}")
            """
        )

        e = shell.start()
        e.prompt().eval()

        assert shell.envo.get_os_environ()[path.upper()][-len(test_path) :] == "/home/user/path1"

        shell.exit()
        e.exit().eval()
