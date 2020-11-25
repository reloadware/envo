from typing import List, Dict, Any, Optional, Tuple  # noqa: F401

from pathlib import Path

import envo  # noqa: F401

from envo import (  # noqa: F401
    logger,
    command,
    context,
    Raw,
    run,
    precmd,
    onstdout,
    onstderr,
    postcmd,
    onload,
    oncreate,
    onunload,
    ondestroy,
    boot_code,
    Plugin,
    VirtualEnv,
    Namespace
)

# Declare your command namespaces here
# like this:
# my_namespace = command(namespace="my_namespace")

trop = Namespace("trop")


class EnvoCommEnv(envo.BaseEnv):  # type: ignore
    class Meta(envo.BaseEnv.Meta):  # type: ignore
        root = Path(__file__).parent.absolute()
        stage: str = "comm"
        emoji: str = "👌"
        parents: List[str] = []
        plugins: List[Plugin] = []
        name: str = "envo"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    poetry_ver: str
    some_var: str

    def __init__(self) -> None:
        self.poetry_ver = "1.0.5"
        self.some_var = "test"

    @trop.command
    def __bootstrap(self):
        run(f"pip install poetry=={self.poetry_ver}")
        run("poetry install")

    @trop.command
    def __some_cmd(self):
        run("echo 'test' && sleep 2 && echo 'test 2'")

    @trop.context
    def __some_context(self):
        return {
            "df": 123
        }

    @onload
    def __on_load(self) -> None:
        import time
        return

    @boot_code
    def __boot(self) -> List[str]:
        return [
            "import math",
        ]


Env = EnvoCommEnv

