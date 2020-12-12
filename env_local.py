from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

import envo  # noqa: F401
from envo import (  # noqa: F401
    BaseEnv,
    Plugin,
    Raw,
    UserEnv,
    VirtualEnv,
    boot_code,
    command,
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

# Declare your command namespaces here
# like this:
# my_namespace = command(namespace="my_namespace")


class EnvoLocalEnv(UserEnv):  # type: ignore
    class Meta(UserEnv.Meta):  # type: ignore
        root = Path(__file__).parent.absolute()
        stage: str = "local"
        emoji: str = "🐣"
        parents: List[str] = ["env_comm.py"]
        plugins: List[Plugin] = [VirtualEnv]
        name: str = "env"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    # Declare your variables here
    local_var: str

    def __init__(self) -> None:
        self.local_var = "fdsf"

        # Define your variables here

    @onload
    def _dump_env(self) -> None:
        self.dump_dot_env()

    @command
    def test(self) -> None:
        logger.info("Running tests")
        run("pytest tests -v")

    @command
    def flake(self) -> None:
        self.black()
        run("flake8")

    @command
    def mypy(self) -> None:
        logger.info("Running mypy")
        run("mypy envo")

    @command
    def black(self) -> None:
        run("isort .")
        run("black .")

    @command
    def ci(self) -> None:
        self.flake()
        self.mypy()
        self.test()

    @command
    def sandbox(self) -> None:
        import sys
        import time
        import logging
        from watchdog.observers import Observer
        from watchdog.events import PatternMatchingEventHandler

        class MyEventHandler(PatternMatchingEventHandler):
            def on_any_event(self, event):
                pass

        handler = MyEventHandler("*.py")

        observer = Observer()
        observer.schedule(handler, ".", recursive=True)
        observer.start()


Env = EnvoLocalEnv

