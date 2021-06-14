import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import envo
from envo import BaseEnv, Namespace, logger

__all__ = [
    "Plugin",
    "VirtualEnv",
]

from envo.logging import Logger
from envo.misc import is_windows
import envium
from envium import var


class Plugin(envo.env.BaseEnv):
    class Environ(envium.Environ):
        pass

    @classmethod
    def init(cls, *args, **kwargs):
        cls.__init__(*args, **kwargs)


class CantFindEnv(Exception):
    pass


@dataclass
class VenvPath:
    root_path: Path
    venv_name: str

    @property
    def path(self) -> Path:
        return self.root_path / self.venv_name

    @property
    def lib_path(self) -> Path:
        return self.path / "lib"

    @property
    def bin_path(self) -> Path:
        if is_windows():
            return self.path / "Scripts"
        else:
            return self.path / "bin"

    @property
    def site_packages_path(self) -> Path:
        if is_windows():
            ret = self.lib_path / "site-packages"
            return ret
        try:
            ret = next(self.lib_path.glob("*"))
            # on windows there is no python.* in site packages path
            if ret.name != "site-packages":
                ret /= "site-packages"
            return ret
        except StopIteration:
            raise CantFindEnv()

    @property
    def possible_site_packages(self) -> List[Path]:
        if is_windows():
            return [self.site_packages_path]
        versions = [f"python3.{v}" for v in range(0, 20)]
        versions += [f"python2.{v}" for v in range(0, 10)]
        ret = [self.lib_path / v / "site-packages" for v in versions]
        return ret


class BaseVenv:
    venv_path: VenvPath

    def __init__(self, root: Path, venv_dir_name: str) -> None:
        self.root = root
        self.venv_dir_name = venv_dir_name
        self._path_delimiter = ";" if is_windows() else ":"

    def _get_path(self):
        path = f"""{str(self.venv_path.bin_path)}"""
        return path

    def activate(self, env: BaseEnv) -> None:
        env.path = f"""{self._get_path()}{self._path_delimiter}{env.e.path}"""

    def deactivate(self, env: BaseEnv) -> None:
        if self._get_path() in env.path:
            env.path = env.path.replace(self._get_path() + self._path_delimiter, "")


class PredictedVenv(BaseVenv):
    def __init__(self, root: Path, venv_name: str) -> None:
        super().__init__(root, venv_name)

        self.venv_path = VenvPath(root_path=root, venv_name=venv_name)

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
    def __init__(self, root: Path, venv_name: str, discover: bool = False) -> None:
        super().__init__(root, venv_name)
        self.discover = discover

        root_path = self._get_venv_dir() if discover else root

        self.venv_path = VenvPath(root_path=root_path, venv_name=venv_name)

        if not self.venv_path.path.exists():
            raise CantFindEnv

    def _get_venv_dir(self) -> Optional[Path]:
        path = self.root

        while path.parent != path:
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
    class Environ(envium.Environ):
        venv_path: Path = var()


    def __init__(
        self, venv_path: Optional[Path] = None, venv_name: str = ".venv"
    ) -> None:
        self.e.venv_path = self.meta.root if not venv_path else venv_path

        self._possible_site_packages = []
        self._venv_dir_name = venv_name

        self.__logger: Logger = logger.create_child("venv", descriptor="VirtualEnv")

        self.__logger.info("VirtualEnv plugin init")

        try:
            self._venv = ExistingVenv(
                root=self.e.venv_path,
                venv_name=venv_name,
                discover=venv_path is None,
            )

        except CantFindEnv:
            self.__logger.info("Couldn't find venv. Falling back to predicting")
            self._venv = PredictedVenv(root=self.e.venv_path, venv_name=venv_name)

        self._venv.activate(self)

    @classmethod
    def init(
        cls,
        self: "VirtualEnv",
        venv_path: Optional[Path] = None,
        venv_name: str = ".venv",
    ):
        VirtualEnv.__init__(self, venv_path, venv_name)

    @venv.onunload
    def __deactivate(self) -> None:
        self.__logger.info("Deactivating VirtualEnv")
        self._venv.deactivate(self)
