from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from envo import Env, Plugin, const


class EmergencyEnv(Env):
    class Meta(Env.Meta):
        root = Path(__file__).parent.absolute()
        stage: str = "emergency"
        emoji: str = const.emojis["emergency"]
        plugins: List[Plugin] = []
        name: str = "emergency"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    class Environ(Env.Environ):
        ...

    e: Environ

    def init(self) -> None:
        pass


ThisEnv = EmergencyEnv
