from dataclasses import dataclass

from .env_comm import ChildEnv, UndeclEnvComm


@dataclass
class ChildEnv(ChildEnv):
    class Meta(ChildEnv.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()

        self.child_var = "test"


@dataclass
class UndeclEnv(UndeclEnvComm):
    class Meta(UndeclEnvComm.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()

        self.child_env = ChildEnv()


Env = UndeclEnv
