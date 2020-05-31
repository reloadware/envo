import os
from importlib import import_module, reload
from pathlib import Path
from typing import Type

from pytest import fixture
from tests.unit.nested_env.env_test import NestedEnv
from tests.unit.parent_env.child_env.env_test import ChildEnv
from tests.unit.property_env.env_test import PropertyEnv
from tests.unit.raw_env.env_test import RawEnv
from tests.unit.undecl_env.env_test import UndeclEnv
from tests.unit.unset_env.env_test import UnsetEnv

from envo import Env

test_root = Path(os.path.realpath(__file__)).parent


@fixture
def nested_env() -> NestedEnv:
    env = NestedEnv()
    return env


@fixture
def unset_env() -> UnsetEnv:
    env = UnsetEnv()
    return env


@fixture
def undecl_env() -> UndeclEnv:
    env = UndeclEnv()
    return env


@fixture
def raw_env() -> RawEnv:
    env = RawEnv()
    return env


@fixture
def property_env() -> PropertyEnv:
    env = PropertyEnv()
    return env


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
    env = reload(import_module("sandbox.env_comm")).Env
    return env


@fixture
def mock_shell(mocker) -> None:
    mocker.patch("envo.scripts.Shell.create")
