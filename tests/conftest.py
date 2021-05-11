import os
import shutil
import sys
from pathlib import Path

from pytest import fixture

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


@fixture
def sandbox() -> Path:
    pwd = Path(os.environ["PWD"])

    test_dir = Path(os.getenv("PYTEST_CURRENT_TEST").split("::")[0]).parent

    sandbox_dir = pwd / test_dir / "sandbox"
    if sandbox_dir.exists():
        shutil.rmtree(str(sandbox_dir), ignore_errors=True)

    sys.path.insert(0, str(sandbox_dir))

    if not sandbox_dir.exists():
        sandbox_dir.mkdir()
    os.chdir(str(sandbox_dir))

    return sandbox_dir


@fixture
def version() -> None:
    file = envo_root / "envo/__version__.py"
    file.touch()
    file.write_text('__version__ = "1.2.3"')

    yield

    file.unlink()


@fixture
def mock_threading(mocker) -> None:
    mocker.patch("threading.Thread.start")


@fixture
def flake_cmd(arg) -> None:
    from tests.utils import add_flake_cmd

    add_flake_cmd()


@fixture
def is_windows():
    from envo.misc import is_windows

    return is_windows()


@fixture
def is_linux():
    from envo.misc import is_linux

    return is_linux()
