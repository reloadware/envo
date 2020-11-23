import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from envo import Env, logger, onload, onunload, BaseEnv

__all__ = [
    "Plugin",
    "VirtualEnv",
]


class Plugin(BaseEnv):
    pass


class VirtualEnv(Plugin):
    """
    Env that activates virtual environment.
    """

    venv_path: Path
    venv_lib_path: Path

    def __init__(self) -> None:
        self.venv_path = Path()
        self.venv_lib_path = Path()
        self._possible_site_packages = []

        logger.info("VirtualEnv plugin init")

        self.venv_lib_path = self.root / ".venv/lib"

        # possible python site-packages
        versions = [f"python3.{v}" for v in range(0, 20)]
        versions += [f"python2.{v}" for v in range(0, 10)]
        self._possible_site_packages = [self.venv_lib_path / v / "site-packages" for v in versions]

        self.venv_path = self.root / ".venv/bin"

        self.path = f"""{str(self.venv_path)}:{os.environ['PATH']}"""

        if not (Path(self.root) / ".venv").exists():
            for d in self._possible_site_packages:
                if d not in sys.path:
                    sys.path.insert(0, str(d))
        else:
            # cleanup after above
            for d in self._possible_site_packages:
                if d in sys.path:
                    sys.path.remove(str(d))

            path = str(next(self.venv_lib_path.glob("*")) / "site-packages")

            if path not in sys.path:
                sys.path.insert(0, path)

    @onunload
    def __onunload(self) -> None:
        logger.info("VirtualEnv plugin onunload")

        for d in self._possible_site_packages:
            if d in sys.path:
                sys.path.remove(str(d))
