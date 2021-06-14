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
)


class EnvoCommEnv(envo.env.BaseEnv):  # type: ignore
    class Meta(envo.env.BaseEnv.Meta):  # type: ignore
        root = Path(__file__).parent.absolute()
        stage: str = "emergency"
        emoji: str = const.emojis["emergency"]
        parents: List[str] = []
        plugins: List[Plugin] = []
        name: str = "emergency"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    def __init__(self) -> None:
        pass


Env = EnvoCommEnv
