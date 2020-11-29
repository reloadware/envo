import os
import sys
from pathlib import Path
from typing import Any, Optional, List

from dataclasses import dataclass

import envo
from envo import Env, logger, onload, onunload, BaseEnv, Namespace

__all__ = [
    "Plugin",
    "VirtualEnv",
]

from envo.logging import Logger


class Plugin(envo.env.EnvoEnv):
    @classmethod
    def init(cls, *args, **kwargs):
        cls.__init__(*args, **kwargs)


class CantFindEnv(Exception):
    pass


@dataclass
class VenvPath:
    root_path: Path
    venv_dir_name: str

    @property
    def path(self) -> Path:
        return self.root_path / self.venv_dir_name

    @property
    def venv_lib_path(self) -> Path:
        return self.path / "lib"

    @property
    def venv_bin_path(self) -> Path:
        return self.path / "bin"

    @property
    def site_packages_path(self) -> Path:
        try:
            return next(self.venv_lib_path.glob("*")) / "site-packages"
        except StopIteration:
            raise CantFindEnv()

    @property
    def possible_site_packages(self) -> List[Path]:
        versions = [f"python3.{v}" for v in range(0, 20)]
        versions += [f"python2.{v}" for v in range(0, 10)]
        ret = [self.venv_lib_path / v / "site-packages" for v in versions]
        return ret


class BaseVenv:
    venv_path: VenvPath

    def __init__(self, root: Path, venv_dir_name: str) -> None:
        self.root = root
        self.venv_dir_name = venv_dir_name

    def _get_path(self):
        path = f"""{str(self.venv_path.venv_bin_path)}:"""
        return path

    def activate(self, env: BaseEnv) -> None:
        env.path = f"""{self._get_path()}{env.path}"""

    def deactivate(self, env: BaseEnv) -> None:
        if self._get_path() in env.path:
            env.path = env.path.replace(self._get_path(), "")


class PredictedVenv(BaseVenv):
    def __init__(self, root: Path, venv_dir_name: str) -> None:
        super().__init__(root, venv_dir_name)

        self.venv_path = VenvPath(root_path=root, venv_dir_name=venv_dir_name)

    def activate(self, env: BaseEnv) -> None:
        super().activate(env)
        for d in self.venv_path.possible_site_packages:
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))

    def deactivate(self, env: BaseEnv) -> None:
        super().deactivate(env)
        for d in self.venv_path.possible_site_packages:
            if str(d) in sys.path:
                sys.path.remove(str(d))


class ExistingVenv(BaseVenv):
    def __init__(self, root: Path, venv_dir_name: str, discover: bool = False) -> None:
        super().__init__(root, venv_dir_name)
        self.discover = discover

        root_path = self._get_venv_dir() if discover else root

        self.venv_path = VenvPath(root_path=root_path, venv_dir_name=venv_dir_name)

        if not self.venv_path.path.exists():
            raise CantFindEnv

    def _get_venv_dir(self) -> Optional[Path]:
        path = self.root

        while path.parent:
            if (path / self.venv_dir_name).exists():
                return path
            path = path.parent

        raise CantFindEnv()

    def activate(self, env: BaseEnv) -> None:
        super().activate(env)

        if str(self.venv_path.site_packages_path) not in sys.path:
            sys.path.insert(0, str(self.venv_path.site_packages_path))

    def deactivate(self, env: BaseEnv) -> None:
        super().deactivate(env)

        try:
            while str(self.venv_path.site_packages_path) in sys.path:
                sys.path.remove(str(self.venv_path.site_packages_path))
        except CantFindEnv:
            pass


venv = Namespace("__venv")


class VirtualEnv(Plugin):
    """
    Env that activates virtual environment.
    """

    venv_path: Path

    def __init__(self, venv_path: Optional[Path] = None, venv_dir_name: str = ".venv") -> None:
        self.venv_path = self.root if not venv_path else venv_path

        self._possible_site_packages = []
        self._venv_dir_name = venv_dir_name

        self.__logger: Logger = logger.create_child("venv", descriptor="VirtualEnv")

        self.__logger.info("VirtualEnv plugin init")

        try:
            self._venv = ExistingVenv(root=self.venv_path,
                                venv_dir_name=venv_dir_name, discover=venv_path is None)
        except CantFindEnv:
            self.__logger.info("Couldn't find venv. Falling back to predicting")
            self._venv = PredictedVenv(root=self.venv_path, venv_dir_name=venv_dir_name)

    @classmethod
    def init(cls, self: BaseEnv, venv_path: Optional[Path] = None, venv_dir_name: str = ".venv"):
        super().init(self, venv_path, venv_dir_name)

    @venv.onload
    def __activate(self) -> None:
        self.__logger.info("Activating VirtualEnv")
        self._venv.activate(self)
        self.__logger.info(f"Activated {self._venv.venv_path.path}")

    @venv.onunload
    def __deactivate(self) -> None:
        self.__logger.info("Deactivating VirtualEnv")
        self._venv.deactivate(self)
