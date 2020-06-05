import os
import sys
from importlib import import_module, reload
from pathlib import Path

from envo import Env

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


def command(*args):
    sys.argv = ("envo",) + args
    from envo import scripts

    scripts._main()
    sys.argv = []


def init() -> None:
    command("test", "--init")


def env() -> Env:
    init_file = Path("__init__.py")
    init_file.touch()

    env_dir = Path(".").absolute()
    sys.path.insert(0, str(env_dir))
    reload(import_module("env_comm"))
    env = reload(import_module("env_test")).Env()
    sys.path.pop(0)
    init_file.unlink()
    return env


def shell() -> None:
    command("test")
