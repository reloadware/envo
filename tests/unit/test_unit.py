import os
from pathlib import Path

import pytest
from tests.unit.utils import command, test_root

import envo.scripts
from envo.comm.test_utils import flake8, mypy

environ_before = os.environ.copy()


class TestMisc:
    @pytest.fixture(autouse=True)
    def setup(
        self, mock_exit, mock_threading, mock_shell, sandbox, version, mocker, capsys
    ):
        mocker.patch("envo.scripts.Envo._start_files_watchdog")
        os.environ = environ_before.copy()
        yield
        out, err = capsys.readouterr()
        assert err == ""

    def test_init(self, init):
        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()

        flake8()
        mypy()

    @pytest.mark.parametrize(
        "dir_name", ["my-sandbox", "my sandbox", ".sandbox", ".san.d- b  ox"]
    )
    def test_init_weird_dir_name(self, dir_name):
        env_dir = Path(dir_name)
        env_dir.mkdir()
        os.chdir(str(env_dir))
        command("test", "--init")

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()
        command("test")

        flake8()

    def test_importing(self, init, shell, env):
        assert str(env) == "sandbox"
        assert env.meta.stage == "test"
        assert env.meta.emoji == envo.scripts.stage_emoji_mapping[env.meta.stage]

    def test_version(self, caplog):
        command("--version")
        assert caplog.messages[0] == "1.2.3"
        assert len(caplog.messages) == 1

    def test_shell(self, init):
        command("test")

    def test_stage(self, init, env):
        env.activate()
        assert os.environ["SANDBOX_STAGE"] == "test"
        assert os.environ["ENVO_STAGE"] == "test"

    def test_get_name(self, init, env):
        assert env.get_name() == "sandbox"

    def test_get_namespace(self, init, env):
        assert env.get_namespace() == "SANDBOX"

    def test_shell_module_with_the_same_name(self, init):
        Path("sandbox").mkdir()
        Path("sandbox/__init__.py").touch()
        command("test")

    def test_dry_run(self, init, capsys, caplog):
        command("test", "--dry-run")
        captured = capsys.readouterr()
        assert captured.out != ""
        assert len(caplog.messages) == 0

    def test_save(self, init, caplog, capsys):
        command("test", "--save")

        assert len(caplog.messages) == 1
        assert caplog.messages[0] == "Saved envs to .env_test 💾"
        assert Path(".env_test").exists()

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_activating(self, init, env):
        env.activate()
        assert os.environ["SANDBOX_STAGE"] == "test"

    def test_init_py_created(self, init, mocker):
        mocker.patch("envo.scripts.Path.unlink")
        command("test")
        assert Path("__init__.py").exists()

    def test_existing_init_py_recovered(self, init):
        init_file = Path("__init__.py")
        init_file.touch()
        init_file.write_text("import flask")
        command("test")

        assert init_file.read_text() == "import flask"
        assert not Path("__init__.py.tmp").exists()

    def test_init_py_delete_if_not_exists(self, init):
        assert not Path("__init__.py").exists()

    def test_init_untouched_if_exists(self):
        file = Path("__init__.py")
        file.touch()
        file.write_text("a = 1")
        command("test", "--init")

        assert file.read_text() == "a = 1"

    def test_nested(self, nested_env):
        nested_env.activate()
        assert os.environ["TE_STAGE"] == "test"
        assert os.environ["TE_PYTHON_VERSION"] == "3.8.2"

    def test_verify_unset_variable(self, unset_env):
        with pytest.raises(envo.BaseEnv.EnvException) as exc:
            unset_env.activate()

        assert str(exc.value) == (
            "Detected errors!\n"
            'Variable "undef_env.python" is unset!\n'
            'Variable "undef_env.child_env.child_var" is unset!'
        )

    def test_verify_variable_undeclared(self, undecl_env):
        with pytest.raises(envo.BaseEnv.EnvException) as exc:
            undecl_env.activate()

        assert str(exc.value) == (
            "Detected errors!\n"
            'Variable "undecl_env.some_var" is undeclared!\n'
            'Variable "undecl_env.child_env.child_var" is undeclared!'
        )

    def test_verify_property_in_env(self, property_env):
        property_env.activate()

        assert property_env.group.prop == "test_value_modified"

    def test_raw(self, raw_env):
        raw_env.activate()
        assert os.environ["NOT_NESTED"] == "NOT_NESTED_TEST"
        assert os.environ["NESTED"] == "NESTED_TEST"

    def test_get_current_stage(self, init, env_comm):
        command("local", "--init")
        command("stage", "--init")
        command("local")

        assert env_comm.get_current_stage().meta.stage == "local"

    def test_venv_addon(self):
        from tests.unit.utils import shell, env

        command("test", "--init=venv")

        shell()
        env = env()

        assert hasattr(env, "venv")
        env.activate()
        assert "SANDBOX_VENV_BIN" in os.environ
        assert f"{Path('.').absolute()}/.venv/bin" in os.environ["PATH"]

        flake8()
        mypy()


class TestParentChild:
    @pytest.fixture(autouse=True)
    def setup(self, mock_exit, mock_shell, sandbox, version, mocker, capsys):
        mocker.patch("envo.scripts.Envo._start_files_watchdog")
        os.environ = environ_before.copy()
        yield
        out, err = capsys.readouterr()
        assert err == ""

    def test_parents_basic_functionality(self, child_env):
        os.chdir(test_root)
        parent_dir = Path(".").absolute() / "parent_env"
        child_dir = Path(".").absolute() / "parent_env/child_env"

        os.chdir(str(child_dir))
        command("test")
        assert child_env.get_parent() is not None
        assert child_env.test_var == "test_var_value"
        assert child_env.get_parent().test_parent_var == "test_value"
        assert child_env.get_parent().get_name() == "pa"

        assert os.environ["PA_TESTPARENTVAR"] == "test_value"
        assert os.environ["CH_TESTVAR"] == "test_var_value"

        assert (child_dir / Path("__init__.py")).exists()
        assert not (child_dir / Path("__init__.py.tmp")).exists()

        assert (parent_dir / Path("__init__.py")).exists()
        assert not (parent_dir / Path("__init__.py.tmp")).exists()

        flake8()
        os.chdir(str(parent_dir))

    def test_get_full_name(self, child_env):
        assert child_env.get_full_name() == "pa.ch"

    def test_parents_variables_passed_through(self, child_env):
        os.chdir(test_root)
        child_dir = Path(".").absolute() / "parent_env/child_env"
        os.chdir(str(child_dir))

        command("test")

        assert "child_bin_dir" in os.environ["PATH"]
        assert "parent_bin_dir" in os.environ["PATH"]
