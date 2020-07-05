from env_comm import EnvoEnvComm
from envo import Raw, command, run, logger  # noqa: F401


class EnvoEnv(EnvoEnvComm):  # type: ignore
    class Meta(EnvoEnvComm.Meta):  # type: ignore
        stage = "local"
        emoji = "🐣"

    # Declare your variables here

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Define your variables here

    @command(glob=True)
    def test(self) -> None:
        logger.info("Running tests")
        run("pytest tests -v")

    @command(glob=True)
    def ci(self) -> None:
        self.flake()
        self.mypy()
        self.test()


Env = EnvoEnv
