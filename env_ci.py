from loguru import logger  # noqa: F401

from env_comm import EnvoEnvComm
from envo import Raw, command, run  # noqa: F401


class EnvoEnv(EnvoEnvComm):  # type: ignore
    class Meta(EnvoEnvComm.Meta):  # type: ignore
        stage = "ci"
        emoji = "🧪"

    # Declare your variables here

    def __init__(self) -> None:
        super().__init__()

        # Define your variables here

    @command(glob=True)
    def test(self) -> None:
        logger.info("Running tests")
        run("mkdir -p workspace")
        run("pytest -v tests --cov-report xml:workspace/cov.xml --cov=envo ./workspace")


Env = EnvoEnv
