from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import envo
from envo import (
    CtxGroup,
    Env,
    Namespace,
    SecretsGroup,
    VirtualEnv,
    boot_code,
    ctx_var,
    env_var,
    run,
    secret,
)

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
        load_env_vars = True

    class Environ(Env.Environ, VirtualEnv.Environ):
        ...

    class Ctx(Env.Ctx, VirtualEnv.Ctx):
        pip_ver: str = ctx_var(default="21.0.1")
        poetry_ver: str = ctx_var(default="1.1.11")

    class Secrets(Env.Secrets):
        ...
        # password: str = secret_var()

    e: Environ
    ctx: Ctx

    def init(self) -> None:
        super().init()
        self.e.pythonpath = ["path1", "path2"]

    @p.command
    def clean(self):
        run("rm **/*/sandbox_* -rf")
        run(f"rm **/*.pyi -f")
        run(f"rm **/.pytest_cache -fr")
        run(f"rm **/*.egg-info -fr")
        run(f"rm **/*/__pycache__ -fr")

    @p.command
    def bootstrap(self):
        raise NotImplementedError

    @boot_code
    def __boot(self) -> List[str]:
        return []


ThisEnv = EnvoCommEnv
