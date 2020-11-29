from typing import List, Dict, Any, Optional, Tuple  # noqa: F401

from pathlib import Path

import envo  # noqa: F401

from envo import (  # noqa: F401
    logger,
    command,
    context,
    Raw,
    run,
    precmd,
    onstdout,
    onstderr,
    postcmd,
    onload,
    oncreate,
    onunload,
    ondestroy,
    boot_code,
    Plugin,
    VirtualEnv,
    const
)


class EnvoCommEnv(envo.env.EnvoEnv):  # type: ignore
    class Meta(envo.BaseEnv.Meta):  # type: ignore
        root = Path(__file__).parent.absolute()
        stage: str = "emergency"
        emoji: str = const.emojis["emergency"]
        parents: List[str] = []
        plugins: List[Plugin] = []
        name: str = ""
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    def __init__(self) -> None:
        pass


Env = EnvoCommEnv

