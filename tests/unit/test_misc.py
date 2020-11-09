import os
from pathlib import Path

import pytest

import envo.scripts
from envo.const import STAGES
from tests.unit import utils


class TestMisc(utils.TestBase):
    def test_init(self):
        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()

        utils.flake8()
        utils.mypy()

    @pytest.mark.parametrize("dir_name", ["my-sandbox", "my sandbox", ".sandbox", ".san.d- b  ox"])
    def test_init_weird_dir_name(self, dir_name):
        env_dir = Path(dir_name)
        env_dir.mkdir()
        os.chdir(str(env_dir))
        utils.command("test --init")

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()
        utils.command("test")

        utils.flake8()

    @pytest.mark.skip
    def test_importing(self, shell_unit, env):
        # TODO: Add lightweight envo
        assert str(env) == "sandbox"
        assert env.meta.stage == "test"
        assert env.meta.emoji == STAGES.get_stage_name_to_emoji()[env.meta.stage]

    def test_version(self, capsys):
        utils.command("--version")
        assert capsys.readouterr().out == "1.2.3\n"

    def test_shell(self):
        utils.command("test")

    @pytest.mark.skip
    def test_stage(self, env):
        env.activate()
        assert os.environ["SANDBOX_STAGE"] == "test"
        assert os.environ["ENVO_STAGE"] == "test"

    @pytest.mark.skip
    def test_get_name(self, env):
        assert env.get_name() == "sandbox"

    def test_shell_module_with_the_same_name(self):
        Path("sandbox").mkdir()
        Path("sandbox/__init__.py").touch()
        utils.command("test")

    @pytest.mark.skip
    def test_activating(self, env):
        env.activate()
        assert os.environ["SANDBOX_STAGE"] == "test"

    @pytest.mark.skip
    def test_nested(self):
        utils.add_declaration(
            """
            @dataclass
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

    @pytest.mark.skip
    def test_verify_unset_variable(self):
        utils.add_declaration("test_var: int")

        e = utils.env()

        with pytest.raises(envo.EnvoError) as exc:
            e.validate()

        assert str(exc.value) == ('Variable "sandbox.test_var" is unset!')

    @pytest.mark.skip
    def test_verify_variable_undeclared(self):
        utils.add_definition("self.test_var = 12")

        e = utils.env()

        with pytest.raises(envo.EnvoError) as exc:
            e.validate()

        assert str(exc.value) == ('Variable "sandbox.test_var" is undeclared!')

    @pytest.mark.skip
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

    @pytest.mark.skip
    def test_raw(self):
        utils.add_declaration(
            """
            @dataclass
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

    @pytest.mark.skip
    def test_nested_raw(self):
        utils.add_declaration("value: Raw[str]")
        utils.add_definition("self.value = 'test_value'")

        e = utils.env()
        e.activate()
        assert os.environ["VALUE"] == "test_value"

