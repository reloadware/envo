import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

from dataclasses import dataclass

import envo  # noqa: F401
root = Path(__file__).parent.absolute()
envo.add_source_roots([root])

from envo import (  # noqa: F401,
    Namespace,
    Plugin,
    VirtualEnv,
    boot_code,
    command,
    console,
    context,
    logger,
    oncreate,
    ondestroy,
    onload,
    onstderr,
    onstdout,
    onunload,
    postcmd,
    precmd,
    run,
    inject
)

# Declare your command namespaces here
# like this:

localci = Namespace(name="localci")
p = Namespace(name="p")

from env_comm import ThisEnv as ParentEnv


class EnvoLocalEnv(ParentEnv):  # type: ignore
    class Meta(ParentEnv.Meta):  # type: ignore
        root: Path = Path(__file__).parent.absolute()
        stage: str = "local"
        emoji: str = "🐣"
        name: str = "env"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []
        verbose_run = True

    class Environ(ParentEnv.Environ):
        pass

    e: Environ

    @onload
    def _dump_env(self) -> None:
        self.dump_dot_env()

    @p.command
    def bootstrap(self) -> None:
        super().bootstrap(create_venv=True)
        path_tmp = os.environ["PATH"]

        @dataclass
        class Version:
            version: str
            venv_name: str

        versions = [
            Version("3.6.13", ".venv36"),
            Version("3.7.10", ".venv37"),
            Version("3.8.10", ".venv38"),
            Version("3.9.5", ".venv39")
        ]

        for v in versions:
            run(f"rm {v.venv_name} -rf")
            os.environ["PATH"] = f"/home/kwazar/.pyenv/versions/{v.version}/bin/:{os.environ['PATH']}"
            run(f"python -m venv {v.venv_name}")
            os.environ["PATH"] = f"{v.venv_name}/bin/:{os.environ['PATH']}"
            super().bootstrap(create_venv=False)
            os.environ["PATH"] = path_tmp

    @command
    def test(self) -> None:
        logger.info("Running tests")
        run("pytest tests -v")

    @p.command
    def verbose_test(self) -> None:
        run("echo verbose cmd")
        print("Output")
        run("echo verbose hihi")

    @command
    def flake(self) -> None:
        self.black()
        run("flake8")

    @p.command
    def mypy(self, arg) -> None:
        logger.info("Running mypy")
        run("mypy envo")

    @command
    def black(self) -> None:
        with console.status("Running black and isort..."):
            run("isort .", print_output=False)
            run("black .", print_output=False)

    @command
    def ci(self) -> None:
        self.flake()
        self.mypy()
        self.test()

    @p.command
    def long(self) -> None:
        run("sleep 5")

    @command
    def sandbox(self) -> None:
        run([
            "echo test1 && sleep 1",
            "echo test2 && sleep 1",
            "echo test3 && sleep 1",
             ], progress_bar="", print_output=False)

    @localci.command
    def __flake(self) -> None:
        run("circleci local execute --job flake8")

    @command
    def hihi(self) -> None:
        run('echo "test"')


ThisEnv = EnvoLocalEnv
