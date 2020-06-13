import os
import re
from pathlib import Path

import pytest

import envo.scripts
from tests.unit import utils

environ_before = os.environ.copy()


class TestBase:
    @pytest.fixture(autouse=True)
    def setup(
        self,
        mock_logger_error,
        mock_threading,
        mock_shell,
        sandbox,
        init,
        version,
        capsys,
    ):
        os.environ = environ_before.copy()
        # mocker.patch("envo.scripts.Envo._start_files_watchdog")
        self.mock_logger_error = mock_logger_error

        yield

        # some errors might acually test if this is called
        # for those test self.mock_logger_error should be set to None
        if self.mock_logger_error:
            assert not mock_logger_error.called

        assert capsys.readouterr() == ("", "")


class TestMisc(TestBase):
    def test_init(self):
        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()

        utils.flake8()
        utils.mypy()

    @pytest.mark.parametrize(
        "dir_name", ["my-sandbox", "my sandbox", ".sandbox", ".san.d- b  ox"]
    )
    def test_init_weird_dir_name(self, dir_name):
        env_dir = Path(dir_name)
        env_dir.mkdir()
        os.chdir(str(env_dir))
        utils.command("test --init")

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()
        utils.command("test")

        utils.flake8()

    def test_importing(self, shell, env):
        assert str(env) == "sandbox"
        assert env.meta.stage == "test"
        assert env.meta.emoji == envo.scripts.stage_emoji_mapping[env.meta.stage]

    def test_version(self, caplog):
        utils.command("--version")
        assert caplog.messages[0] == "1.2.3"
        assert len(caplog.messages) == 1

    def test_shell(self):
        utils.command("test")

    def test_stage(self, env):
        env.activate()
        assert os.environ["SANDBOX_STAGE"] == "test"
        assert os.environ["ENVO_STAGE"] == "test"

    def test_get_name(self, env):
        assert env.get_name() == "sandbox"

    def test_shell_module_with_the_same_name(self):
        Path("sandbox").mkdir()
        Path("sandbox/__init__.py").touch()
        utils.command("test")

    def test_dry_run(self, capsys, caplog):
        utils.command("test --dry-run")
        captured = capsys.readouterr()
        assert captured.out != ""
        assert len(caplog.messages) == 0

    def test_save(self, caplog, capsys):
        utils.command("test --save")

        assert len(caplog.messages) == 1
        assert caplog.messages[0] == "Saved envs to .env_test 💾"
        assert Path(".env_test").exists()

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_activating(self, env):
        env.activate()
        assert os.environ["SANDBOX_STAGE"] == "test"

    def test_init_py_created(self, mocker):
        mocker.patch("envo.scripts.Path.unlink")
        utils.command("test")
        assert Path("__init__.py").exists()

    def test_existing_init_py_recovered(self):
        init_file = Path("__init__.py")
        init_file.touch()
        init_file.write_text("import flask")
        utils.command("test")

        assert init_file.read_text() == "import flask"
        assert not Path("__init__.py.tmp").exists()

    def test_init_py_delete_if_not_exists(self):
        assert not Path("__init__.py").exists()

    def test_init_untouched_if_exists(self):
        file = Path("__init__.py")
        file.touch()
        file.write_text("a = 1")

        assert file.read_text() == "a = 1"

    def test_nested(self):
        utils.add_declaration(
            """
            class Python(envo.BaseEnv):
                version: str

            python: Python
            """
        )
        utils.add_definition(
            'self.python = self.Python(version="3.8.2")', file=Path("env_test.py"),
        )

        e = utils.env()
        e.activate()

        assert os.environ["SANDBOX_STAGE"] == "test"
        assert os.environ["SANDBOX_PYTHON_VERSION"] == "3.8.2"

    def test_verify_unset_variable(self):
        utils.add_declaration("test_var: int")

        e = utils.env()

        with pytest.raises(envo.BaseEnv.EnvException) as exc:
            e.activate()

        assert str(exc.value) == (
            "Detected errors!\n" 'Variable "sandbox.test_var" is unset!'
        )

    def test_verify_variable_undeclared(self):
        utils.add_definition("self.test_var = 12")

        e = utils.env()

        with pytest.raises(envo.BaseEnv.EnvException) as exc:
            e.activate()

        assert str(exc.value) == (
            "Detected errors!\n" 'Variable "sandbox.test_var" is undeclared!'
        )

    def test_verify_property(self):
        utils.add_declaration("value: str")
        utils.add_definition("self.value = 'test_value'")
        utils.add_command(
            """
            @property
            def prop(self) -> str:
                return self.value + "_modified"
            """
        )

        e = utils.env()

        assert e.prop == "test_value_modified"

    def test_raw(self):
        utils.add_declaration(
            """
            class Python(envo.BaseEnv):
                version: Raw[str]

            python: Python
            """
        )
        utils.add_definition(
            'self.python = self.Python(version="3.8.2")', file=Path("env_test.py"),
        )

        utils.add_declaration("version: Raw[str]")

        utils.add_definition(
            """
            self.python = self.Python(version="3.8.2")
            self.version = self.python.version + ".1"
            """,
            file=Path("env_test.py"),
        )

        e = utils.env()
        e.activate()
        assert os.environ["VERSION"] == "3.8.2.1"

    def test_nested_raw(self):
        utils.add_declaration("value: Raw[str]")
        utils.add_definition("self.value = 'test_value'")

        e = utils.env()
        e.activate()
        assert os.environ["VALUE"] == "test_value"

    def test_venv_addon(self):
        Path("env_comm.py").unlink()
        Path("env_test.py").unlink()

        utils.command("test --init=venv")

        e = utils.env()

        assert hasattr(e, "venv")
        e.activate()
        assert "SANDBOX_VENV_BIN" in os.environ
        assert f"{Path('.').absolute()}/.venv/bin" in os.environ["PATH"]

        utils.flake8()
        utils.mypy()

    def test_get_current_stage(self, env_comm):
        utils.command("local --init")
        utils.command("stage --init")
        utils.command("local")

        assert env_comm.get_current_env().meta.stage == "local"

    def test_cant_find_env(self):
        utils.command("prod")

        assert re.match(
            r".*Couldn.*find.*env", str(self.mock_logger_error.call_args_list[0].args)
        )

        self.mock_logger_error = None


class TestCommands(TestBase):
    def test_repr(self):
        utils.init()
        utils.flake_cmd(prop=False, glob=False)
        utils.mypy_cmd(prop=False, glob=False)
        e = utils.env()
        assert re.match(
            (
                r"# Variables\n"
                r"root: Field = PosixPath\('.*'\)\n"
                r"stage: Field = 'test'\n"
                r"envo_stage: Field = 'test'\n"
                r"pythonpath: Field = .*\n"
                r"# Commands\n"
                r'flake\(test_arg: str = ""\) -> None  # property=False, global=False\n'
                r'mypy\(test_arg: str = ""\) -> None  # property=False, global=False'
            ),
            repr(e),
        )

        utils.init()
        utils.flake_cmd(prop=True, glob=False)
        utils.mypy_cmd(prop=True, glob=False)
        e = utils.env()
        assert re.match(
            (
                r"# Variables\n"
                r"root: Field = PosixPath\('.*'\)\n"
                r"stage: Field = 'test'\n"
                r"envo_stage: Field = 'test'\n"
                r"pythonpath: Field = .*\n"
                r"# Commands\n"
                r'flake\(test_arg: str = ""\) -> None  # property=True, global=False\n'
                r'mypy\(test_arg: str = ""\) -> None  # property=True, global=False'
            ),
            repr(e),
        )

        utils.init()
        utils.mypy_cmd(prop=True, glob=False)


class TestParentChild(TestBase):
    def test_parents_basic_functionality(self, init_child_env):
        sandbox_dir = Path(".").absolute()
        child_dir = sandbox_dir / "child"

        utils.replace_in_code('name = "sandbox"', 'name = "pa"')
        utils.add_declaration("test_parent_var: str")
        utils.add_definition('self.test_parent_var = "test_parent_value"')

        utils.replace_in_code(
            'name = "child"', 'name = "ch"', file=child_dir / "env_comm.py"
        )
        utils.add_declaration(
            "test_var: str", file=child_dir / "env_comm.py",
        )
        utils.add_definition(
            'self.test_var = "test_value"', file=child_dir / "env_comm.py",
        )

        child_env = utils.env(child_dir)

        assert child_env.get_parent() is not None
        assert child_env.test_var == "test_value"
        assert child_env.get_parent().test_parent_var == "test_parent_value"
        assert child_env.get_parent().get_name() == "pa"

        child_env.activate()
        assert os.environ["PA_TESTPARENTVAR"] == "test_parent_value"
        assert os.environ["CH_TESTVAR"] == "test_value"

    def test_get_full_name(self, init_child_env):
        sandbox_dir = Path(".").absolute()
        child_dir = sandbox_dir / "child"

        utils.replace_in_code('name = "sandbox"', 'name = "pa"')
        utils.replace_in_code(
            'name = "child"', 'name = "ch"', file=child_dir / "env_comm.py"
        )

        child_env = utils.env(child_dir)

        assert child_env.get_full_name() == "pa.ch"

    def test_parents_variables_passed_through(self, init_child_env):
        sandbox_dir = Path(".").absolute()
        child_dir = sandbox_dir / "child"

        utils.replace_in_code('name = "sandbox"', 'name = "pa"')
        utils.add_declaration("path: Raw[str]")
        utils.add_definition(
            """
            import os
            self.path = os.environ["PATH"]
            self.path = "/parent_bin_dir:" + self.path
            """
        )

        utils.replace_in_code(
            'name = "child"', 'name = "ch"', file=child_dir / "env_comm.py"
        )
        utils.add_declaration(
            "path: Raw[str]", file=child_dir / "env_comm.py",
        )
        utils.add_definition(
            """
            import os
            self.path = os.environ["PATH"]
            self.path = "/child_bin_dir:" + self.path
            """,
            file=child_dir / "env_comm.py",
        )

        child_env = utils.env(child_dir)
        child_env.activate()

        assert "child_bin_dir" in os.environ["PATH"]
        assert "parent_bin_dir" in os.environ["PATH"]
