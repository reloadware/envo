import os
from dataclasses import dataclass
from pathlib import Path

from envo import BaseEnv, Env


@dataclass
class ChildEnv(Env):
    class Meta(Env.Meta):
        root = Path(os.path.realpath(__file__)).parent
        name = "child_env"

    def __init__(self) -> None:
        super().__init__()


@dataclass
class UndeclEnvComm(Env):
    class Meta(Env.Meta):
        root = Path(os.path.realpath(__file__)).parent
        name = "undecl_env"

    @dataclass
    class Python(BaseEnv):
        version: str

    child_env: ChildEnv

    def __init__(self) -> None:
        super().__init__()

        self.some_var = "value"
