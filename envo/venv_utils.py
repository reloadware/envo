import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
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


@dataclass
class BaseVenv:
    venv_path: VenvPath = field(init=False)

    class Environ(envium.Environ):
        path: str = env_var(raw=True)

    def __post_init__(self) -> None:
        self._path_delimiter = ";" if is_windows() else ":"

        self.e = self.Environ(name="envo", load=True)

    def _get_path(self):
        path = f"""{str(self.venv_path.bin_path)}"""
        return path

    def activate(self, e: Optional[Env.Environ] = None) -> None:
        environ = e or self.e

        path = self._get_path()

        if path not in environ.path.split(self._path_delimiter):
            environ.path = f"""{path}{self._path_delimiter}{environ.path}"""

        if not e:
            self.e.save_to_os_environ()

    def deactivate(self, e: Optional[Env.Environ] = None) -> None:
        environ = e or self.e
        if self._get_path() in environ.path:
            environ.path = environ.path.replace(self._get_path() + self._path_delimiter, "")

        if not e:
            self.e.save_to_os_environ()

    def __enter__(self) -> None:
        self.activate()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.deactivate()


@dataclass
class PredictedVenv(BaseVenv):
    root: Path
    venv_name: str

    def __post_init__(self) -> None:
        super().__post_init__()

        self.venv_path = VenvPath(root_path=self.root, venv_name=self.venv_name)

    def activate(self, e: Optional[Env.Environ] = None) -> None:
        super().activate(e)
        for d in self.venv_path.possible_site_packages:
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))

    def deactivate(self, e: Optional[Env.Environ] = None) -> None:
        super().deactivate(e)
        for d in self.venv_path.possible_site_packages:
            if str(d) in sys.path:
                sys.path.remove(str(d))


@dataclass
class ExistingVenv(BaseVenv):
    def activate(self, e: Optional[Env.Environ] = None) -> None:
        super().activate(e)

        if str(self.venv_path.site_packages_path) not in sys.path:
            sys.path.insert(0, str(self.venv_path.site_packages_path))

    def deactivate(self, e: Optional[Env.Environ] = None) -> None:
        super().deactivate(e)

        try:
            while str(self.venv_path.site_packages_path) in sys.path:
                sys.path.remove(str(self.venv_path.site_packages_path))
        except CantFindVenv:
            pass


@dataclass
class Venv(ExistingVenv):
    path: Union[Path, str]

    def __post_init__(self) -> None:
        super().__post_init__()

        self.path = Path(self.path).absolute()
        self.venv_path = VenvPath(root_path=self.path.parent, venv_name=self.path.stem)


@dataclass
class DiscoveredVenv(ExistingVenv):
    root: Path
    venv_name: str

    def __post_init__(self) -> None:
        super().__post_init__()

        root_path = self._get_venv_dir()

        self.venv_path = VenvPath(root_path=root_path, venv_name=self.venv_name)

        if not self.venv_path.path.exists():
            raise CantFindVenv

    def _get_venv_dir(self) -> Optional[Path]:
        path = self.root

        while path.parent != path:
            if (path / self.venv_name).exists():
                return path
            path = path.parent

        raise CantFindVenv()
