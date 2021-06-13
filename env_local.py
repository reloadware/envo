import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

import envo  # noqa: F401
from envo import (  # noqa: F401
    BaseEnv,
    Namespace,
    Plugin,
    UserEnv,
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
e = Namespace(name="e")

class EnvoLocalEnv(UserEnv):  # type: ignore
    class Meta(UserEnv.Meta):  # type: ignore
        root: Path = Path(__file__).parent.absolute()
        stage: str = "local"
        emoji: str = "🐣"
        parents: List[str] = ["env_comm.py"]
        plugins: List[Plugin] = [VirtualEnv]
        name: str = "env"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []
        verbose_run = True

    def __init__(self) -> None:
        pass

    @onload
    def _dump_env(self) -> None:
        self.dump_dot_env()

    @command
    def test(self) -> None:
        os.chdir(self.root)
        logger.info("Running tests", print_msg=True)
        run("pytest tests -v")

    @e.command
    def verbose_test(self) -> None:
        run("echo verbose cmd")
        print("Output")
        run("echo verbose hihi")

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
        with console.status("Running black and isort..."):
            run("isort .", print_output=False)
            run("black .", print_output=False)

    @command
    def ci(self) -> None:
        self.flake()
        self.mypy()
        self.test()

    @e.command
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


Env = EnvoLocalEnv
