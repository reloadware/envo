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
        root = Path(__file__).parent.absolute()
        stage: str = "comm"
        emoji: str = "👌"
        parents: List[str] = []
        plugins: List[Plugin] = []
        name: str = "env"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    poetry_ver: str
    some_var: str

    def __init__(self) -> None:
        self.poetry_ver = "1.0.5"
        self.some_var = "test"

    @command
    def fun(self) -> None:
        run(
            """
            sudo echo 'test'
            sudo echo "test2"
            """)

    def fun2(self) -> None:
        print("test")

    @command
    def bootstrap(self):
        run(f"pip install poetry=={self.poetry_ver}")
        run("poetry install")

    @onload
    def __on_load(self) -> None:
        print("LOAD")
        return

    @oncreate
    def __on_create(self) -> None:
        print("MOTD")

    @boot_code
    def __boot(self) -> List[str]:
        return [
            "import math",
        ]


Env = EnvoCommEnv

