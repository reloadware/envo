import shutil
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
        poetry_ver: str = ctx_var(default="1.1.7")

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
        to_clean = ["**/*/sandbox_*", "**/*.pyi", "**/.pytest_cache",
                    "**/*.egg-info", "**/*/__pycache__"]

        for c in to_clean:
            for p in self.meta.root.glob(c):
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()

    @p.command
    def bootstrap(self):
        raise NotImplementedError

    @boot_code
    def __boot(self) -> List[str]:
        return []


ThisEnv = EnvoCommEnv
