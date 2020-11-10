import os
import sys
from importlib import import_module, reload
from pathlib import Path
from typing import List

import pexpect as pexpect
import pytest

from envo import Env
from tests.utils import add_command  # noqa F401
from tests.utils import add_declaration  # noqa F401
from tests.utils import add_definition  # noqa F401
from tests.utils import change_file  # noqa F401
from tests.utils import add_flake_cmd  # noqa F401
from tests.utils import add_mypy_cmd  # noqa F401
from tests.utils import replace_in_code  # noqa F401

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


__all__ = [
    "TestBase",
    "spawn",
    "flake8",
    "mypy",
]


environ_before = os.environ.copy()


class TestBase:
    @pytest.fixture(autouse=True)
    def setup(
        self, mock_logger_error, mock_threading, mock_shell, sandbox, init, version, capsys,
    ):
        os.environ = environ_before.copy()
        # mocker.patch("envo.scripts.Envo._start_files_watchdog")
        self.mock_logger_error = mock_logger_error

        yield

        # some errors might acually test if this is called
        # for those test self.mock_logger_error should be set to None
        if self.mock_logger_error:
            assert not mock_logger_error.called

        assert capsys.readouterr().err == ""


def command(cmd: str):
    sys.argv = ["envo"] + cmd.split()
    from envo import scripts

    scripts._main()
    sys.argv = []


def init() -> None:

    env_comm_file = Path("env_comm.py")
    if env_comm_file.exists():
        env_comm_file.unlink()

    env_local_file = Path("env_test.py")
    if env_local_file.exists():
        env_local_file.unlink()

    command("test --init")


def env(env_dir: Path = Path(".")) -> Env:
    init_file = env_dir / "__init__.py"
    init_file.touch()

    sys.path.insert(0, str(env_dir))
    reload(import_module("env_comm"))
    env = reload(import_module("env_test")).Env()
    sys.path.pop(0)
    init_file.unlink()
    return env


def shell_unit() -> None:
    command("test")


def init_child_env(child_dir: Path) -> None:
    cwd = Path(".").absolute()
    child_dir.mkdir()

    os.chdir(str(child_dir))
    command("test --init")

    replace_in_code("parent: Optional[str] = None", 'parent: Optional[str] = ".."')

    os.chdir(str(cwd))


def spawn(command: str) -> pexpect.spawn:
    s = pexpect.spawn(command, echo=False, timeout=4)
    s.logfile = sys.stdout.buffer
    return s


def flake8() -> None:
    p = pexpect.run("flake8", echo=False)
    assert p == b""


def mypy() -> None:
    from pexpect import run

    original_dir = Path(".").absolute()
    package_name = original_dir.name
    Path("__init__.py").touch()
    os.chdir("..")
    environ = {"MYPYPATH": str(original_dir), "PYTHONPATH": str(original_dir)}
    environ.update(os.environ)
    p = run(f"mypy {package_name}", env=environ, echo=False)
    assert b"Success: no issues found" in p
    os.chdir(str(original_dir))
    Path("__init__.py").unlink()


def strs_in_regex(strings: List[str]) -> str:
    """
    Return regex that matches strings in any order.
    """
    ret = "".join([rf"(?=.*{s})" for s in strings])
    return ret
