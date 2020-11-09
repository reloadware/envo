from textwrap import dedent

from envo import const
from tests.e2e import utils
import os
from pathlib import Path
import pytest
from pexpect import run


class TestStubs:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        yield
        self.shell.on_exit()

    def init(self) -> None:
        self.shell = utils.default_shell()
        result = run("envo --init")
        assert b"Created comm environment" in result

    def assert_stub_equal(self, stub_file: str, content: str, stage: str = "comm") -> None:
        self.shell.start()

        e = self.shell.expecter
        e.prompt(emoji=const.STAGES.get_stage_name_to_emoji()[stage]).eval()

        content = dedent(content)

        print(f"Comparing:\n{content} \n to: \n{Path(stub_file).read_text()}")

        assert content.replace(" ", "") in Path(stub_file).read_text().replace(" ", "")

        self.shell.exit()
        e.exit().eval()

    def test_comm_only(self):
        self.init()

        stub = """
        class SandboxEnv:
            class Meta:
                stage: str
                emoji: str
                parents: typing.List[str]
                plugins: typing.List[envo.plugins.Plugin]
                name: str
                version: str
                watch_files: typing.List[str]
                ignore_files: typing.List[str]
                
                
            root: Path
            path: envo.env.Raw[str]
            stage: str
            envo_stage: envo.env.Raw[str]
            pythonpath: envo.env.Raw[str]
        """

        self.assert_stub_equal("env_comm.pyi", stub)

    def test_comm_only_discovery(self):
        self.init()
        Path("some_dir").mkdir()
        os.chdir("some_dir")

        self.assert_healthy_and_correct_files_in_dir(Path(".."), 2)

    def test_comm_other_envs_priority(self, default_shell):
        result = run("envo test --init")
        assert b"Created test environment" in result

        self.shell = default_shell
        self.assert_healthy_and_correct_files_in_dir(Path("."), 4)

    def test_comm_other_envs_priority_local(self, default_shell):
        result = run("envo local --init")
        assert b"Created local environment" in result

        self.shell = default_shell
        self.assert_healthy_and_correct_files_in_dir(Path("."), 4, stage="local")

