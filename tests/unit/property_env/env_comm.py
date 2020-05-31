import os
from dataclasses import dataclass
from pathlib import Path

from envo import BaseEnv, Env


@dataclass
class PropertyEnvComm(Env):
    class Meta(Env.Meta):
        root = Path(os.path.realpath(__file__)).parent
        name = "property_env"

    @dataclass
    class SomeEnvGroup(BaseEnv):
        value: str

        @property
        def prop(self) -> str:
            return self.value + "_modified"

    group: SomeEnvGroup

    def __init__(self) -> None:
        super().__init__()

        self.group = self.SomeEnvGroup(value="test_value")
