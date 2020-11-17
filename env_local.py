from env_comm import EnvoEnvComm
from envo import Raw, command, dataclass, logger, onload, run  # noqa: F401


@dataclass
class EnvoEnv(EnvoEnvComm):  # type: ignore
    class Meta(EnvoEnvComm.Meta):  # type: ignore
        name = "envo"
        stage = "local"
        emoji = "🐣"
        parents = ["env_comm.py"]

    # Declare your variables here
    var: int
    raw_var: Raw[float]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.var = 12
        self.raw_var = 12.03

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


Env = EnvoEnv

