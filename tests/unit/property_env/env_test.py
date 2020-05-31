from dataclasses import dataclass

from .env_comm import PropertyEnvComm


@dataclass
class PropertyEnv(PropertyEnvComm):
    class Meta(PropertyEnvComm.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()


Env = PropertyEnv
