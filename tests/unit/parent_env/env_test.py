from dataclasses import dataclass

from tests.unit.parent_env.env_comm import ParentEnvComm


@dataclass
class ParentEnv(ParentEnvComm):
    class Meta(ParentEnvComm.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()
        self.test_parent_var = "test_value"


Env = ParentEnv
