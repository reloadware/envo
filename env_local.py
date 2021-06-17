import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

import envo  # noqa: F401
root = Path(__file__).parent.absolute()
envo.add_source_roots([root])

from envo import (  # noqa: F401,
    Namespace,
    Plugin,
    VirtualEnv,
    boot_code,
    command,
    console,
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

localci = Namespace(name="localci")
pr = Namespace(name="pr")

from env_comm import ThisEnv as ParentEnv


class EnvoLocalEnv(ParentEnv):  # type: ignore
    class Meta(ParentEnv.Meta):  # type: ignore
        root: Path = Path(__file__).parent.absolute()
        stage: str = "local"
        emoji: str = "🐣"
        name: str = "env"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []
        verbose_run = True

    class Environ(ParentEnv.Environ):
        pass

    e: Environ

    @onload
    def _dump_env(self) -> None:
        self.dump_dot_env()

    @command
    def test(self) -> None:
        logger.info("Running tests", print_msg=True)
        run("pytest tests -v")

    @pr.command
    def verbose_test(self) -> None:
        run("echo verbose cmd")
        print("Output")
        run("echo verbose hihi")

    @command
    def flake(self) -> None:
        self.black()
        run("flake8")

    @pr.command
    def mypy(self, arg) -> None:
        logger.info("Running mypy")
        run("mypy envo")

    @command
    def black(self) -> None:
        with console.status("Running black and isort..."):
            run("isort .", print_output=False)
            run("black .", print_output=False)

    @command
    def ci(self) -> None:
        self.flake()
        self.mypy()
        self.test()

    @pr.command
    def long(self) -> None:
        run("sleep 5")

    @command
    def sandbox(self) -> None:
        run([
            "echo test1 && sleep 1",
            "echo test2 && sleep 1",
            "echo test3 && sleep 1",
             ], progress_bar="", print_output=False)

    @localci.command
    def __flake(self) -> None:
        run("circleci local execute --job flake8")


ThisEnv = EnvoLocalEnv
