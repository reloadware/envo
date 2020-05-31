import os
from dataclasses import dataclass
from pathlib import Path

from envo import BaseEnv, Env


@dataclass
class ChildEnv(Env):
    class Meta(Env.Meta):
        root = Path(os.path.realpath(__file__)).parent
        name = "child_env"

    child_var: int

    def __init__(self) -> None:
        super().__init__()


@dataclass
class UnsetEnvComm(Env):
    class Meta(Env.Meta):
        root = Path(os.path.realpath(__file__)).parent
        name = "undef_env"

    @dataclass
    class Python(BaseEnv):
        version: str

    python: Python
    child_env: ChildEnv

    def __init__(self) -> None:
        super().__init__()
