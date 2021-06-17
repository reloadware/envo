from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

import envo  # noqa: F401
from envo import (  # noqa: F401
    Plugin,
    VirtualEnv,
    boot_code,
    command,
    const,
    context,
    logger,
    oncreate,
    ondestroy,
    onload,
    onstderr,
    onstdout,
    onunload,
    postcmd,
    precmd,
    run,
    Env
)


class EmergencyEnv(Env):  # type: ignore
    class Meta(Env.Meta):  # type: ignore
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
