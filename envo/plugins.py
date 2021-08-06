import os
import sys
from pathlib import Path
from typing import List, Optional, Union

from envo import Env, Namespace, logger

__all__ = [
    "Plugin",
    "VirtualEnv",
]

import envium
from envium import Ctx, CtxGroup, Environ, ctx_var, env_var

from envo import venv_utils
from envo.env import BaseEnv
from envo.logs import Logger
from envo.misc import is_windows


class Plugin(BaseEnv):
    class Environ(Environ):
        ...

    class Ctx(Ctx):
        ...


class VirtualEnv(Plugin):
    """
    Env that activates virtual environment.
    """

    class Environ(Plugin.Environ):
        path: str = env_var(raw=True)

    class Ctx(Plugin.Ctx):
        class Venv(CtxGroup):
            dir: Optional[Path] = ctx_var()
            name: str = ctx_var(".venv")
            discover: bool = ctx_var(False)

        venv = Venv()

    ctx: Ctx
    e: Environ

    def init(self):
        super().init()

        self.__logger: Logger = logger.create_child("venv", descriptor="VirtualEnv")
        self.__logger.debug("VirtualEnv plugin init")

    def post_init(self) -> None:
        if not self.ctx.venv.dir:
            self.ctx.venv.dir = self.meta.root

        try:
            if self.ctx.venv.discover:
                self._venv = venv_utils.DiscoveredVenv(root=self.meta.root, venv_name=self.ctx.venv.name)
            else:
                self._venv = venv_utils.Venv(self.ctx.venv.dir / self.ctx.venv.name)
            self._venv.activate(self.e)
        except venv_utils.CantFindVenv:
            self.__logger.debug("Couldn't find venv. Falling back to predicting")
            self._venv = venv_utils.PredictedVenv(root=self.meta.root, venv_name=self.ctx.venv.name)
            self._venv.activate(self.e)
