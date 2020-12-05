import os
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict

from pexpect import run

from envo import const
from envo.misc import import_from_file
from tests.e2e import utils


class TestStubs(utils.TestBase):
    def assert_files_in_dir(self, how_many: int, dir: Path = Path(".")):
        files_n = len([p for p in dir.glob("*") if p.is_file()])
        assert files_n == how_many

    def get_annotations(self, env: Any) -> Dict[str, str]:
        annotations = {}

        for c in env.__mro__:
            if not hasattr(c, "__annotations__"):
                continue
            annotations.update(c.__annotations__)

        return annotations

    def test_comm_only(self, comm_shell, sandbox):

        utils.add_flake_cmd(file=Path("env_comm.py"))
        utils.add_hook(
            r"""
            @precmd(cmd_regex=r"print\(.*\)")
            def pre_print(self, command: str) -> str:
                assert command == 'print("pancake");'
                print("pre")
                return command * 2
            """
        )

        e = comm_shell.start()
        e.prompt().eval()

        stub_file = sandbox / Path("env_comm.pyi")

        self.assert_files_in_dir(3)

        assert stub_file.exists()
        stub = import_from_file(stub_file)
        env = stub.SandboxCommEnv

        # user defined command
        assert "_SandboxCommEnv__flake" in dir(env)
        assert "pre_print" not in dir(env)

        # Envo methods
        assert "genstub" in dir(env)
        assert "repr" in dir(env)

        comm_shell.exit()
        e.exit().eval()

    def test_in_dir(self, shell):
        utils.add_flake_cmd(file=Path("env_comm.py"))

        Path("some_dir").mkdir()
        os.chdir("some_dir")

        e = shell.start()
        e.prompt().eval()

        self.assert_files_in_dir(4, Path(".."))

        assert Path("../env_comm.pyi").exists()
        assert Path("../env_test.pyi").exists()
        stub = import_from_file(Path("../env_test.pyi"))
        env = stub.SandboxTestEnv

        # user defined command
        assert "_SandboxCommEnv__flake" in dir(env)

        # Envo methods
        assert "genstub" in dir(env)
        assert "repr" in dir(env)

        shell.exit()
        e.exit().eval()

    def test_inherited(self, shell):
        utils.add_flake_cmd(file=Path("env_comm.py"))
        utils.add_declaration("comm_var: str", Path("env_comm.py"))
        utils.add_definition("self.comm_var = 'test'", Path("env_comm.py"))

        utils.add_declaration("test_var: int", Path("env_test.py"))
        utils.add_definition("self.test_var = 1", Path("env_test.py"))
        utils.add_mypy_cmd(file=Path("env_test.py"))

        utils.add_flake_cmd(file=Path("env_comm.py"))

        e = shell.start()
        e.prompt().eval()

        self.assert_files_in_dir(4)

        assert Path("env_comm.pyi").exists()
        assert Path("env_test.pyi").exists()

        comm_stub = import_from_file(Path("env_comm.pyi"))
        comm_env = comm_stub.SandboxCommEnv

        test_stub = import_from_file(Path("env_test.pyi"))
        test_env = test_stub.SandboxTestEnv

        # user defined command
        assert "_SandboxCommEnv__flake" in dir(comm_env)
        assert "_SandboxCommEnv__flake" in dir(test_env)

        assert "_SandboxTestEnv__mypy" in dir(test_env)
        assert "_SandboxCommEnv__mypy" not in dir(comm_env)

        assert "comm_var" in self.get_annotations(comm_env)
        assert "comm_var" in self.get_annotations(test_env)
        assert "test_var" in self.get_annotations(test_env)
        assert "test_var" not in self.get_annotations(comm_env)

        # Envo methods
        assert "genstub" in dir(comm_env)
        assert "repr" in dir(comm_env)

        assert "genstub" in dir(test_env)
        assert "repr" in dir(test_env)

        shell.exit()
        e.exit().eval()
