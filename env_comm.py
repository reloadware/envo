from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

import envo  # noqa: F401
from envo import (  # noqa: F401
    Namespace,
    Plugin,
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
    var,
    Env
)

# Declare your command namespaces here
# like this:
pr = Namespace("pr")


class EnvoCommEnv(Env, VirtualEnv):  # type: ignore
    class Meta(Env.Meta, VirtualEnv):  # type: ignore
        root: str = Path(__file__).parent.absolute()
        stage: str = "comm"
        emoji: str = "👌"
        name: str = "env"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []
        verbose_run = True

    class Environ(Env.Environ, VirtualEnv.Environ):
        pip_ver: str = var(default="21.0.1")
        poetry_ver: str = var(default="1.0.10")

    e: Environ

    @pr.command
    def clean(self):
        run("rm **/*/sandbox -rf")
        run(f"rm **/*.pyi -f")
        run(f"rm **/.pytest_cache -fr")
        run(f"rm **/*.egg-info -fr")
        run(f"rm **/*/__pycache__ -fr")

    @pr.command
    def bootstrap(self):
        run(f"pip install pip=={self.e.pip_ver}")
        run(f"pip install poetry=={self.e.poetry_ver}")
        run("poetry config virtualenvs.create true")
        run("poetry config virtualenvs.in-project true")
        run("poetry install")

    @boot_code
    def __boot(self) -> List[str]:
        return []


Env = EnvoCommEnv
