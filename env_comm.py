from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

import envo  # noqa: F401
from envo import (  # noqa: F401
    Namespace,
    Plugin,
    Raw,
    UserEnv,
    VirtualEnv,
    boot_code,
    command,
    context,
    logger,
    oncreate,
    ondestroy,
    onload,
    onstderr,
    onstdout,
    onunload,
    postcmd,
    precmd,
    run,
)

# Declare your command namespaces here
# like this:
# my_namespace = command(namespace="my_namespace")


class EnvoCommEnv(UserEnv):  # type: ignore
    class Meta(UserEnv.Meta):  # type: ignore
        root: str = Path(__file__).parent.absolute()
        stage: str = "comm"
        emoji: str = "👌"
        parents: List[str] = []
        plugins: List[Plugin] = [VirtualEnv]
        name: str = "env"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    pip_ver: str
    poetry_ver: str

    def __init__(self) -> None:
        self.pip_ver = "21.0.1"
        self.poetry_ver = "1.0.10"

    @command
    def bootstrap(self):
        run(f"pip install pip=={self.pip_ver}")
        run(f"pip install poetry=={self.poetry_ver}")
        run("poetry config virtualenvs.create true")
        run("poetry config virtualenvs.in-project true")
        run("poetry install")

    @boot_code
    def __boot(self) -> List[str]:
        return []


Env = EnvoCommEnv
