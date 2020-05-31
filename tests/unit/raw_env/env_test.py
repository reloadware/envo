from dataclasses import dataclass

from .env_comm import RawEnvComm


@dataclass
class RawEnv(RawEnvComm):
    class Meta(RawEnvComm.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()

        self.not_nested = "NOT_NESTED_TEST"
        self.group = self.SomeEnvGroup(nested="NESTED_TEST")


Env = RawEnv
