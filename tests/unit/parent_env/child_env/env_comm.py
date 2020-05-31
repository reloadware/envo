import os
from dataclasses import dataclass
from pathlib import Path

import envo
from envo import Raw


@dataclass
class ChildEnvComm(envo.Env):
    class Meta(envo.Env.Meta):
        root = Path(os.path.realpath(__file__)).parent
        parent = ".."
        name = "ch"

    test_var: str
    path: Raw[str]

    def __init__(self) -> None:
        super().__init__()

        self.path = os.environ["PATH"]
        self.path = "/child_bin_dir:" + self.path


Env = ChildEnvComm
