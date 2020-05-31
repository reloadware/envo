import os
import shutil
from pathlib import Path
from typing import Callable, Generator

import pexpect
from loguru_caplog import loguru_caplog as caplog  # noqa: ignore F401
from pytest import fixture

from . import test_utils

root = Path(".").absolute()


@fixture
def sandbox() -> Generator:
    sandbox_dir = root / "sandbox"
    if sandbox_dir.exists():
        shutil.rmtree(str(sandbox_dir))

    sandbox_dir.mkdir()
    os.chdir(str(sandbox_dir))

    yield
    if sandbox_dir.exists():
        shutil.rmtree(str(sandbox_dir))


@fixture
def assert_no_stderr(capsys) -> Callable[[], None]:  # type: ignore
    def fun() -> None:
        captured = capsys.readouterr()
        assert captured.err == ""

    return fun


@fixture(name="shell")
def shell_fixture() -> pexpect.spawn:
    from .test_utils import shell

    return shell()


@fixture
def envo_prompt() -> bytes:
    return test_utils.envo_prompt


@fixture
def prompt() -> bytes:
    return test_utils.prompt
