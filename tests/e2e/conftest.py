import os
from pathlib import Path

from pexpect import run
from pytest import fixture

from tests.e2e import utils

test_root = Path(os.path.realpath(__file__)).parent.parent
envo_root = test_root.parent / "envo"


@fixture
def init() -> None:
    result = run("envo test --init")
    assert b"Created test environment" in result

@fixture
def init_bare() -> None:
    result = run("envo --init")
    assert b"Created test environment" in result


@fixture
def init_child_env() -> None:
    child_dir = Path("child")
    utils.init_child_env(child_dir)


@fixture
def init_2_same_childs() -> None:
    sandbox1 = Path("sandbox")
    utils.init_child_env(sandbox1)

    sandbox2 = Path("sandbox/sandbox")
    utils.init_child_env(sandbox2)


@fixture
def shell() -> utils.Spawn:
    from tests.e2e.utils import shell

    s = shell()
    yield s
    s.on_exit()


@fixture
def default_shell() -> utils.Spawn:
    from tests.e2e.utils import default_shell

    s = default_shell()
    yield s
    s.on_exit()


@fixture
def env_test_file() -> Path:
    return Path("env_test.py")


@fixture
def env_comm_file() -> Path:
    return Path("env_comm.py")
