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
    BaseEnv,
    UserEnv
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
    def __some_cmd(self):
        print("comm lol")

    @command
    def flake(self, arg) -> None:
        print(f"Flake good + {arg}")

        # self.black()
        # run("flake8")

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


Env = EnvoLocalEnv


