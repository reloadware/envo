from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import envo
from envo import Env, Namespace, VirtualEnv, boot_code, run, var

root = Path(__file__).parent.absolute()
envo.add_source_roots([root])


# Declare your command namespaces here
# like this:
p = Namespace("p")


class EnvoCommEnv(Env, VirtualEnv):
    class Meta(Env.Meta, VirtualEnv):
        root: str = Path(__file__).parent.absolute()
        name: str = "env"
        verbose_run = True

    class Environ(Env.Environ, VirtualEnv.Environ):
        ...

    e: Environ

    def init(self) -> None:
        super().init()

        self.pip_ver = "21.0.1"
        self.poetry_ver = "1.1.7"

    @p.command
    def clean(self):
        run("rm **/*/sandbox -rf")
        run(f"rm **/*.pyi -f")
        run(f"rm **/.pytest_cache -fr")
        run(f"rm **/*.egg-info -fr")
        run(f"rm **/*/__pycache__ -fr")

    @p.command
    def bootstrap(self, create_venv: bool = True):
        run(f"pip install pip=={self.e.pip_ver}")
        run(f"pip install poetry=={self.e.poetry_ver}")
        run(f"poetry config virtualenvs.create {str(create_venv).lower()}")
        run("poetry config virtualenvs.in-project true")
        run("poetry install")

    @boot_code
    def __boot(self) -> List[str]:
        return []


ThisEnv = EnvoCommEnv
