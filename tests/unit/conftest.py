import os
import sys
from importlib import import_module, reload
from pathlib import Path
from typing import Type

from pytest import fixture

from envo import Env
from tests.unit.parent_env.child_env.env_test import ChildEnv

test_root = Path(os.path.realpath(__file__)).parent


@fixture
def child_env() -> ChildEnv:
    env = ChildEnv()
    return env


@fixture
def init() -> None:
    from tests.unit.utils import init

    init()


@fixture
def shell() -> None:
    from tests.unit.utils import shell

    shell()


@fixture
def env() -> Env:
    from tests.unit.utils import env

    return env()


@fixture
def env_comm() -> Type[Env]:
    env_dir = Path(".").absolute()
    sys.path.insert(0, str(env_dir))
    env = reload(import_module("env_comm")).Env
    sys.path.pop(0)
    return env


@fixture
def mock_shell(mocker) -> None:
    mocker.patch("envo.scripts.Shell.create")
