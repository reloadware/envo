from pathlib import Path
from typing import TYPE_CHECKING, Type

from envo import misc

if TYPE_CHECKING:
    from envo import Env


class StubGen:
    env: "Env"

    def __init__(self, env: "Env"):
        self.env = env

    def generate(self) -> None:
        if not self.env.get_user_envs():
            return

        self._generate_env(self.env.__class__)
        for p in self.env._parents:
            self._generate_env(p)

    def _generate_env(self, env: Type["Env"]):
        env_descr = misc.EnvParser(env.get_env_path())

        file = Path(f"{str(env.Meta.root.absolute())}/env_{env.Meta.stage}.pyi")
        file.write_text(env_descr.get_stub(), "utf-8")
