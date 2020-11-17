import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple  # noqa: F401

import envo
from envo import (  # noqa: F401
    Raw,
    VirtualEnv,
    boot_code,
    command,
    context,
    logger,
    onload,
    onstderr,
    onstdout,
    onunload,
    postcmd,
    precmd,
    run,
)

# from typing import List



trop = command(namespace="trop")


@dataclass
class EnvoEnvComm(VirtualEnv, envo.Env):
    class Meta(envo.Env.Meta):
        root = Path(__file__).parent
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

    @trop
    def __bootstrap(self):
        run(f"pip install poetry=={self.poetry_ver}")
        run("poetry install")

    @trop
    def __some_cmd(self):
        print("trop lol")

    @boot_code
    def __boot(self) -> List[str]:
        return [
            "import math"
        ]


Env = EnvoEnvComm

