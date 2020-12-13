import os
import sys
from importlib import import_module, reload
from pathlib import Path
from typing import Type
from unittest.mock import MagicMock

from pytest import fixture

from envo import Env

test_root = Path(os.path.realpath(__file__)).parent


@fixture
def init() -> None:
    from tests.unit.utils import init

    init()


@fixture
def shell_unit() -> None:
    from tests.unit.utils import shell_unit

    shell_unit()


@fixture
def mock_shell(mocker) -> None:
    mocker.patch("envo.shell.Shell.create")


@fixture
def init_child_env() -> None:
    from tests.unit.utils import init_child_env

    init_child_env(Path(".").absolute() / "child")


@fixture
def mock_logger_error(mocker) -> MagicMock:
    return mocker.patch("loguru.logger.error")
