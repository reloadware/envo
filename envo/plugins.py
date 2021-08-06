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
from envium import env_var

from envo import venv_utils
from envo.env import BaseEnv
from envo.logs import Logger
from envo.misc import is_windows


class Plugin(BaseEnv):
    class Environ:
        pass


class VirtualEnv(Plugin):
    """
    Env that activates virtual environment.
    """

    class Environ(envium.Environ):
        path: str = env_var(raw=True)

    e: Environ

    @classmethod
    def customise(cls, venv_path: Optional[Union[Path, str]] = None, venv_name: str = ".venv"):
        cls.venv_path = Path(venv_path).absolute() if venv_path else None
        cls.venv_name = venv_name

    def init(self):
        super().init()

        root = Path(".").absolute()
        # Handle standalone and inherited case
        if hasattr(self, "e"):
            e = self.e
        else:
            e = VirtualEnv.Environ(name="envo", load=True)
        self.__logger: Logger = logger.create_child("venv", descriptor="VirtualEnv")

        venv_path = root if not self.venv_path else self.venv_path

        self._possible_site_packages = []
        self._venv_dir_name = self.venv_name

        self.__logger.debug("VirtualEnv plugin init")

        try:
            self._venv = venv_utils.ExistingVenv(
                root=venv_path,
                venv_name=self.venv_name,
                discover=self.venv_path is None,
            )

        except venv_utils.CantFindVenv:
            self.__logger.debug("Couldn't find venv. Falling back to predicting")
            self._venv = venv_utils.PredictedVenv(root=venv_path, venv_name=self.venv_name)

        self._venv.activate(e)
        os.environ["PATH"] = e.path


VirtualEnv.customise()
