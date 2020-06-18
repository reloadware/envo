from pathlib import Path

# from typing import List

from loguru import logger

from typing import List, Dict, Any  # noqa: F401

import envo
from envo import (  # noqa: F401
    command,
    VenvEnv,
    context,
    Raw,
    run,
    precmd,
    onstdout,
    onstderr,
    postcmd,
    onload,
    onunload,
)

# onstdout, onstderr, postcmd


class EnvoEnvComm(envo.Env):
    class Meta(envo.Env.Meta):
        root = Path(__file__).parent
        name = "envo"
        version = "0.1.0"
        parent = None

    venv: VenvEnv

    def __init__(self) -> None:
        super().__init__()

        self.venv = VenvEnv(self)

    # class Bootstrap:
    #     watch_files = [
    #         "poetry.lock"
    #     ]
    #
    # class Precommit:
    #     checks = [
    #         CheckStaged(
    #             name="Check flake",
    #             files=r".*\.py",
    #             exclude=r"env_.*\.py",
    #             cmd=lambda f: f"flake {f}"
    #         ),
    #         CheckAll(
    #             name="chec",
    #             files=r".*\.py",
    #             exclude=r"env_.*\.py",
    #             cmd=lambda f: f"autoflake {f}"
    #         ),
    #     ]
    #
    @command
    def flake(self) -> None:
        logger.info("Running flake8")
        run("black .", print_output=False)
        run("flake8")
    #
    # @command(prop=False, glob=True)
    # def flake2(self, test_arg: str = "") -> str:
    #     print("Flake all good" + test_arg)
    #     return "Flake return value"
    #
    # @onload
    # def init_sth(self) -> None:
    #     print("on load")
    #
    # @onunload
    # def deinit_sth(self) -> None:
    #     print("on unload")

    # @context
    # def test_context(self) -> None:
    #     return {
    #         "context_value": 1
    #     }

    # @command(glob=False, prop=False)
    # def autoflake(self) -> None:
    #     print("test")
    #     return "test ret"
    # logger.info("Running autoflake")
    # run("autoflake --remove-all-unused-imports -i .")

    @command(glob=True)
    def mypy(self) -> None:
        logger.info("Running mypy")
        run("mypy envo")
    #
    # @command(glob=True)
    # def black(self) -> None:
    #     logger.info("Running black")
    #     run("black .")

    # @command(glob=True)
    # def bootstrap(self):
    #     run(f"pip install poetry=={self.poetry_ver}")
    #     run("poetry install")
    #
    # @precmd(cmd_regex=r"git commit.*")
    # def pre_custom_ls(self) -> None:
    #     checker = SanityChecker()
    #     checker.add_checks([
    #         CheckStaged(
    #             name="Check flake",
    #             files=r".*\.py",
    #             exclude=r"env_.*\.py",
    #             cmd=lambda f: f"flake {f}"
    #         ),
    #         CheckAll(
    #             name="chec",
    #             files=r".*\.py",
    #             exclude=r"env_.*\.py",
    #             cmd=lambda f: f"autoflake {f}"
    #         ),
    #     ])
    #
    #     checker.run()

    @precmd(cmd_regex=r"git commit.*")
    def pre_commit(self, command) -> None:
        print("preee")

    @onstdout(cmd_regex=r"ls")
    def on_custom_ls_out(self, command: str, out: str) -> str:
        out = "a" + out
        return out

    @onstdout(cmd_regex=r"print\(.*\)")
    def on_print(self, out, command) -> str:
        return "sweet"

    @onstderr(cmd_regex=r"print\(.*\)")
    def on_custom_ls_err(self, command: str, out: str) -> str:
        return out

    @postcmd(cmd_regex=r"print\(.*\)")
    def post_custom_ls(
        self, command: str, stdout: List[str], stderr: List[str]
    ) -> None:
        print("post")


Env = EnvoEnvComm
