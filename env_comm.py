import time
from pathlib import Path

# from typing import List

from typing import List, Dict, Any, Tuple  # noqa: F401

import envo
from dataclasses import dataclass
from envo import (  # noqa: F401
    command,
    VirtualEnv,
    context,
    Raw,
    run,
    precmd,
    onstdout,
    onstderr,
    postcmd,
    onload,
    onunload,
    logger,
)


@dataclass
class EnvoEnvComm(VirtualEnv, envo.Env):
    class Meta(envo.Env.Meta):
        root = Path(__file__).parent
        name = "envo"
        version = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = ["**/tests/**"]
        parent = None

    poetry_ver: str
    poetry_ver4: str
    some_var: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.poetry_ver = "1.0.5"
        self.some_var = "test"
        self.poetry_ver4 = "fds"

    @command(glob=True)
    def bootstrap(self):
        run(f"pip install poetry=={self.poetry_ver}")
        run("poetry install")

    @context()
    def fdsf(self):
        return {
            "test": 12
        }


Env = EnvoEnvComm


