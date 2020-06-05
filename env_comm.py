from pathlib import Path

from loguru import logger

import envo
from envo import VenvEnv, command, run


class EnvoEnvComm(envo.Env):
    class Meta(envo.Env.Meta):
        root = Path(__file__).parent
        name = "envo"
        version = "0.1.0"
        parent = None

    venv: VenvEnv

    def __init__(self) -> None:
        super().__init__()

        self.venv = VenvEnv(self)

    @command(glob=True)
    def flake(self) -> None:
        logger.info("Running flake8")
        run("flake8")

    @command(glob=True)
    def mypy(self) -> None:
        logger.info("Running mypy")
        run("mypy envo")

    @command(glob=True)
    def black(self) -> None:
        run("black .")


Env = EnvoEnvComm
