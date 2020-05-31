from dataclasses import dataclass

from .env_comm import ChildEnv, UnsetEnvComm


@dataclass
class ChildEnv(ChildEnv):
    class Meta(ChildEnv.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()


@dataclass
class UnsetEnv(UnsetEnvComm):
    class Meta(UnsetEnvComm.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()

        self.child_env = ChildEnv()


Env = UnsetEnv
