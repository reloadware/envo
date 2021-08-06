import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import envium
from envium import env_var

from envo import Env, Namespace, logger
from envo.misc import is_windows


class CantFindVenv(Exception):
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
            raise CantFindVenv()

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

    def activate(self, e: Env.Environ) -> None:
        e.path = f"""{self._get_path()}{self._path_delimiter}{e.path}"""

    def deactivate(self, e: Env.Environ) -> None:
        if self._get_path() in e.path:
            e.path = e.path.replace(self._get_path() + self._path_delimiter, "")


class PredictedVenv(BaseVenv):
    def __init__(self, root: Path, venv_name: str) -> None:
        super().__init__(root, venv_name)

        self.venv_path = VenvPath(root_path=root, venv_name=venv_name)

    def activate(self, e: Env.Environ) -> None:
        super().activate(e)
        for d in self.venv_path.possible_site_packages:
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))

    def deactivate(self, e: Env.Environ) -> None:
        super().deactivate(e)
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
            raise CantFindVenv

    def _get_venv_dir(self) -> Optional[Path]:
        path = self.root

        while path.parent != path:
            if (path / self.venv_dir_name).exists():
                return path
            path = path.parent

        raise CantFindVenv()

    def activate(self, e: Env.Environ) -> None:
        super().activate(e)

        if str(self.venv_path.site_packages_path) not in sys.path:
            sys.path.insert(0, str(self.venv_path.site_packages_path))

    def deactivate(self, e: Env.Environ) -> None:
        super().deactivate(e)

        try:
            while str(self.venv_path.site_packages_path) in sys.path:
                sys.path.remove(str(self.venv_path.site_packages_path))
        except CantFindVenv:
            pass


@contextmanager
def venv(path: Union[Path, str]) -> None:
    path = Path(path).absolute()

    class Environ(envium.Environ):
        path: str = env_var(raw=True)

    e = Environ(name="envo", load=True)

    venv_obj = ExistingVenv(root=path.parent, venv_name=path.stem)

    venv_obj.activate(e)
    os.environ.update(e.get_env_vars())
    yield
    venv_obj.deactivate(e)
    os.environ.update(e.get_env_vars())
