from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import envo

root = Path(__file__).parent.absolute()
envo.add_source_roots([root])

from env_comm import ThisEnv as ParentEnv
from envo import Namespace, logger, run

p = Namespace("p")


class EnvoCiEnv(ParentEnv):
    class Meta(ParentEnv.Meta):
        root: str = root
        stage: str = "ci"
        emoji: str = "🧪"
        verbose_run = True

    class Environ(ParentEnv.Environ):
        pass

    e: Environ

    @p.command
    def bootstrap(self) -> None:
        raise NotImplementedError

    @p.command
    def test(self) -> None:
        logger.info("Running tests")
        run("pytest tests -v -n auto")

    @p.command
    def unit_test(self) -> None:
        run("pytest tests/unit -v")

    @p.command
    def build(self) -> None:
        run("poetry build")

    @p.command
    def publish(self) -> None:
        run("poetry publish --username $PYPI_USERNAME --password $PYPI_PASSWORD")

    @p.command
    def rstcheck(self) -> None:
        pass
        # run("rstcheck README.rst | tee ./workspace/rstcheck.txt")

    @p.command
    def flake(self) -> None:
        pass
        # run("flake8 . | tee ./workspace/flake8.txt")

    @p.command
    def check_black(self) -> None:
        pass
        # run("black --check . | tee ./workspace/black.txt")

    @p.command
    def mypy(self) -> None:
        pass
        # run("mypy . | tee ./workspace/mypy.txt")

    @p.command
    def generate_version(self) -> None:
        import toml

        config = toml.load(str(self.meta.root / "pyproject.toml"))
        version: str = config["tool"]["poetry"]["version"]

        version_file = self.meta.root / "envo/__version__.py"
        Path(version_file).touch()

        version_file.write_text(f'__version__ = "{version}"\n')


ThisEnv = EnvoCiEnv
