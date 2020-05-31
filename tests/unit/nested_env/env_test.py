from dataclasses import dataclass

from .env_comm import NestedEnvComm


@dataclass
class NestedEnv(NestedEnvComm):
    class Meta(NestedEnvComm.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()
        self.python = self.Python(version="3.8.2")


Env = NestedEnv
