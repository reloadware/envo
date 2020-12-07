import os
from pathlib import Path

import pytest
from pexpect import run

from envo import const
from tests.e2e import utils


class TestActivating:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        yield
        self.shell.on_exit()

    def init(self) -> None:
        self.shell = utils.default_shell()
        result = run("envo init")
        assert b"Created comm environment" in result

    def assert_healthy_and_correct_files_in_dir(
        self, dir: Path, files_n: int = 2, stage: str = "comm"
    ) -> None:
        self.shell.start()

        e = self.shell.expecter
        e.prompt(emoji=const.STAGES.get_stage_name_to_emoji()[stage]).eval()

        assert (dir / Path("env_comm.py")).exists()

        files_n = 0
        for p in dir.glob("*"):
            if p.is_file():
                files_n += 1

        assert files_n == files_n  # env_comm.py and env_comm.pyi

        self.shell.exit()
        e.exit().eval()

    def test_comm_only(self):
        self.init()
        self.assert_healthy_and_correct_files_in_dir(Path("."), 2)

    def test_comm_only_discovery(self):
        self.init()
        Path("some_dir").mkdir()
        os.chdir("some_dir")

        self.assert_healthy_and_correct_files_in_dir(Path(".."), 2)

    def test_comm_other_envs_priority(self, default_shell):
        result = run("envo init test")
        assert b"Created test environment" in result

        self.shell = default_shell
        self.assert_healthy_and_correct_files_in_dir(Path("."), 4)

    def test_comm_other_envs_priority_local(self, default_shell):
        result = run("envo init local")
        assert b"Created local environment" in result

        self.shell = default_shell
        self.assert_healthy_and_correct_files_in_dir(Path("."), 4, stage="local")

    def test_custom_env(self):
        result = run("envo init damian")
        assert b"Created damian environment" in result

        shell = utils.SpawnEnvo("damian")

        self.shell = shell
        self.assert_healthy_and_correct_files_in_dir(Path("."), 4, stage="damian")
