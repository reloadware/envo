from dataclasses import dataclass

from tests.unit.parent_env.child_env.env_comm import ChildEnvComm


@dataclass
class ChildEnv(ChildEnvComm):
    class Meta(ChildEnvComm.Meta):
        stage = "test"
        emoji = "🛠"

    def __init__(self) -> None:
        super().__init__()
        self.test_var = "test_var_value"


Env = ChildEnv
