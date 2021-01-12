import os
from pathlib import Path

import pytest

from tests.unit import utils


class TestMisc(utils.TestBase):
    def test_init(self):
        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()

        utils.flake8()
        # utils.mypy()

    @pytest.mark.parametrize(
        "dir_name", ["my-sandbox", "my sandbox", ".sandbox", ".san.d- b  ox"]
    )
    def test_init_weird_dir_name(self, dir_name):
        env_dir = Path(dir_name)
        env_dir.mkdir()
        os.chdir(str(env_dir))
        utils.command("test init")

        assert Path("env_comm.py").exists()
        assert Path("env_test.py").exists()
        utils.command("test")

        utils.flake8()

    def test_version(self, capsys):
        utils.command("version")
        assert capsys.readouterr().out == "1.2.3\n"

    def test_shell(self):
        utils.command("test")

    def test_shell_module_with_the_same_name(self):
        Path("sandbox").mkdir()
        Path("sandbox/__init__.py").touch()
        utils.command("test")

    def test_importing(self):
        env = utils.get_env_class()
        assert env.stage == "test"
