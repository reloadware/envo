import os
import shutil
from pathlib import Path
from typing import Generator

from loguru_caplog import loguru_caplog as caplog  # noqa: ignore F401
from pytest import fixture

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


@fixture
def sandbox() -> Generator:
    sandbox_dir = test_root / "sandbox"
    if sandbox_dir.exists():
        shutil.rmtree(str(sandbox_dir), ignore_errors=True)

    sandbox_dir.mkdir()
    os.chdir(str(sandbox_dir))

    yield
    if sandbox_dir.exists():
        shutil.rmtree(str(sandbox_dir), ignore_errors=True)


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
def flake_cmd() -> None:
    from tests.utils import flake_cmd

    flake_cmd()
