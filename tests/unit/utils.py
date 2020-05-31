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
    reload(import_module("sandbox.env_comm"))
    env = reload(import_module("sandbox.env_test")).Env()
    init_file.unlink()
    return env


def shell() -> None:
    command("test")
