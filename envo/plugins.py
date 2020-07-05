import os
import sys
from pathlib import Path
from typing import Any


from envo import BaseEnv, onload


__all__ = [
    "VirtualEnv",
]


class VirtualEnv(BaseEnv):
    """
    Env that activates virtual environment.
    """

    # TODO: change it to a mixin?
    root: Path
    venv_path: Path

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.venv_path = Path()

    @onload
    def _onload(self) -> None:
        self.venv_path = self.root / ".venv/bin"

        if self.venv_path.exists():
            self.path = f"""{str(self.venv_path)}:{os.environ['PATH']}"""

            site_packages = next((self.root / ".venv/lib").glob("*")) / "site-packages"

            sys.path.insert(0, str(site_packages))
