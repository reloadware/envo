import os
from dataclasses import dataclass
from pathlib import Path

from envo import BaseEnv, Env


@dataclass
class NestedEnvComm(Env):
    class Meta(Env.Meta):
        root = Path(os.path.realpath(__file__)).parent
        name = "te"

    @dataclass
    class Python(BaseEnv):
        version: str

    python: Python

    def __init__(self) -> None:
        super().__init__()
