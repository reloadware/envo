import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from pytest import fixture

from tests import utils

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


@fixture
def sandbox(request) -> Path:
    name = f"sandbox_{uuid4()}"
    cwd = os.getcwd()

    sandbox_dir = Path(request.module.__file__).parent / name

    if sandbox_dir.exists():
        for f in sandbox_dir.glob("*"):
            if f.is_dir():
                shutil.rmtree(f)
            else:
                f.unlink()

    sys.path.insert(0, str(sandbox_dir))

    if not sandbox_dir.exists():
        sandbox_dir.mkdir()

    os.chdir(str(sandbox_dir))

    yield sandbox_dir

    shutil.rmtree(sandbox_dir, ignore_errors=True)

    os.chdir(cwd)


@fixture
def environ_sandbox() -> Path:
    environ_before = os.environ.copy()

    yield
    os.environ = environ_before


@fixture
def env_sandbox() -> Path:
    environ_before = os.environ.copy()

    yield
    os.environ = environ_before


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


@fixture
def envo_imports():
    utils.add_imports_in_envs_in_dir(Path("."))
