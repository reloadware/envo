#!/usr/bin/env python3
import argparse
import builtins
import os
import sys
import time
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List

from ilock import ILock
from inotify.adapters import Inotify  # type: ignore
from jinja2 import Environment, Template
from loguru import logger
from xonsh.base_shell import BaseShell
from xonsh.execer import Execer
from xonsh.ptk_shell.shell import PromptToolkitShell
from xonsh.readline_shell import ReadlineShell

from envo import Env, comm
from envo.comm import import_module_from_file

__all__ = ["stage_emoji_mapping"]

package_root = Path(os.path.realpath(__file__)).parent
templates_dir = package_root / "templates"

stage_emoji_mapping: Dict[str, str] = {
    "comm": "",
    "test": "🛠",
    "ci": "🧪",
    "local": "🐣",
    "stage": "🤖",
    "prod": "🔥",
}


class Shell(BaseShell):  # type: ignore
    def __init__(self, execer: Execer) -> None:
        super().__init__(execer=execer, ctx={})

        self.environ = builtins.__xonsh__.env  # type: ignore
        self.environ_before = copy(self.environ)
        self.context: Dict[str, Any] = {}

    def set_prompt_prefix(self, prefix: str) -> None:
        from xonsh.prompt.base import DEFAULT_PROMPT

        self.environ["PROMPT"] = prefix + str(DEFAULT_PROMPT)

    def set_variable(self, name: str, value: Any) -> None:
        self.context[name] = value

        built_in_name = f"__envo_{name}__"
        setattr(builtins, built_in_name, value)
        self.default(f"{name} = {built_in_name}")

    def start(self) -> None:
        pass

    def reset(self) -> None:
        self.environ = copy(self.environ_before)
        for n, v in self.context.items():
            self.default(f"del {n}")

        self.context = {}

    @property
    def formated_prompt(self) -> str:
        from xonsh.ansi_colors import ansi_partial_color_format

        return str(ansi_partial_color_format(self.prompt))

    @classmethod
    def create(cls) -> "Shell":
        import signal
        from xonsh.built_ins import load_builtins
        from xonsh.built_ins import XonshSession
        from xonsh.imphooks import install_import_hooks
        from xonsh.xontribs import xontribs_load
        import xonsh.history.main as xhm

        ctx: Dict[str, Any] = {}

        execer = Execer(xonsh_ctx=ctx)

        builtins.__xonsh__ = XonshSession(ctx=ctx, execer=execer)  # type: ignore
        load_builtins(ctx=ctx, execer=execer)
        env = builtins.__xonsh__.env  # type: ignore
        env.update({"XONSH_INTERACTIVE": True, "SHELL_TYPE": "prompt_toolkit"})
        builtins.__xonsh__.history = xhm.construct_history(  # type: ignore
            env=env.detype(), ts=[time.time(), None], locked=True
        )

        builtins.__xonsh__.history.gc.wait_for_shell = False  # type: ignore

        install_import_hooks()
        builtins.aliases.update({"ll": "ls -alF"})  # type: ignore
        xontribs_load([""])

        def func_sig_ttin_ttou(n: Any, f: Any) -> None:
            pass

        signal.signal(signal.SIGTTIN, func_sig_ttin_ttou)
        signal.signal(signal.SIGTTOU, func_sig_ttin_ttou)

        shell = cls(execer)
        builtins.__xonsh__.shell = shell  # type: ignore
        builtins.__xonsh__.shell.shell = shell  # type: ignore

        return shell


class FancyShell(Shell, PromptToolkitShell):  # type: ignore
    @classmethod
    def create(cls) -> "Shell":
        from xonsh.main import _pprint_displayhook

        shell = super().create()
        setattr(sys, "displayhook", _pprint_displayhook)
        return shell

    def start(self) -> None:
        self.cmdloop()
        os._exit(0)


class SimpleShell(Shell, ReadlineShell):  # type: ignore
    def start(self) -> None:
        self.cmdloop()
        os._exit(0)


shells = {"fancy": FancyShell, "simple": SimpleShell, "headless": Shell}


class Envo:
    @dataclass
    class Sets:
        stage: str
        addons: List[str]
        init: bool

    selected_addons: List[str]
    addons: List[str]
    files_watchdog_thread: Thread
    shell: Shell
    inotify: Inotify
    env_dirs: List[Path]

    def __init__(self, sets: Sets) -> None:
        self.se = sets

        self.addons = ["venv"]

        unknown_addons = [a for a in self.se.addons if a not in self.addons]
        if unknown_addons:
            raise RuntimeError(f"Unknown addons {unknown_addons}")

        self.inotify = Inotify()

        self.env_dirs = self._get_env_dirs()

    def spawn_shell(self, type: str) -> None:
        self.shell = shells[type].create()
        self._start_files_watchdog()
        self.send_env_to_shell()
        self.shell.start()

    def send_env_to_shell(self) -> None:
        try:
            env: Env = self.get_env()
            env_prefix = f"{env.meta.emoji}({env.get_full_name()})"
            env.validate()
            env.activate()
            self.shell.reset()
            self.shell.set_variable("env", env)
            self.shell.set_variable("environ", self.shell.environ)

            glob_cmds = [c for c in env.get_commands() if c.glob]
            for c in glob_cmds:
                self.shell.set_variable(c.name, c)

            self.shell.environ.update(env.get_envs())
            self.shell.set_prompt_prefix(env_prefix)

        except Env.EnvException as exc:
            logger.error(exc)
            self.shell.set_prompt_prefix("❌")
        except Exception:
            from traceback import print_exc

            print_exc()
            self.shell.set_prompt_prefix("❌")

    def _files_watchdog(self) -> None:
        for event in self.inotify.event_gen(yield_nones=False):
            (_, type_names, path, filename) = event
            if "IN_CLOSE_WRITE" in type_names:
                logger.info(f'\nDetected changes in "{str(path)}".')
                logger.info("Reloading...")
                self.send_env_to_shell()
                print("\r" + self.shell.formated_prompt, end="")

    def _start_files_watchdog(self) -> None:
        for d in self.env_dirs:
            comm_env_file = d / "env_comm.py"
            env_file = d / f"env_{self.se.stage}.py"
            self.inotify.add_watch(str(comm_env_file))
            self.inotify.add_watch(str(env_file))

        self.files_watchdog_thread = Thread(target=self._files_watchdog)
        self.files_watchdog_thread.start()

    def _get_env_dirs(self) -> List[Path]:
        ret = []
        path = Path(".").absolute()
        while True:
            env_file = path / f"env_{self.se.stage}.py"
            if env_file.exists():
                ret.append(path)
            else:
                if path == Path("/"):
                    break
            path = path.parent

        return ret

    def _create_init_files(self) -> None:
        for d in self.env_dirs:
            init_file = d / "__init__.py"

            if init_file.exists():
                init_file_tmp = d / Path("__init__.py.tmp")
                init_file_tmp.touch()
                init_file_tmp.write_text(init_file.read_text())

            if not init_file.exists():
                init_file.touch()

            init_file.write_text("# __envo_delete__")

    def _delete_init_files(self) -> None:
        for d in self.env_dirs:
            init_file = d / Path("__init__.py")
            init_file_tmp = d / Path("__init__.py.tmp")

            if init_file.read_text() == "# __envo_delete__":
                init_file.unlink()

            if init_file_tmp.exists():
                init_file.touch()
                init_file.write_text(init_file_tmp.read_text())
                init_file_tmp.unlink()

    def get_env(self) -> Env:
        env_dir = self.env_dirs[0]
        package = env_dir.name
        env_name = f"env_{self.se.stage}"
        env_file = env_dir / f"{env_name}.py"

        module_name = f"{package}.{env_name}"

        with ILock("envo_lock"):
            self._create_init_files()

            # unload modules
            for m in list(sys.modules.keys())[:]:
                if m.startswith("env_"):
                    sys.modules.pop(m)

            try:
                sys.path.insert(0, str(env_dir))
                module = import_module_from_file(env_file)
                env: Env
                env = module.Env()
                sys.path.pop(0)
                return env
            except ImportError as exc:
                logger.error(f"""Couldn't import "{module_name}" ({exc}).""")
                raise
            finally:
                self._delete_init_files()

    def _create_from_templ(
        self, templ_file: Path, output_file: Path, is_comm: bool = False
    ) -> None:
        Environment(keep_trailing_newline=True)
        template = Template((templates_dir / templ_file).read_text())
        if output_file.exists():
            logger.error(f"{str(output_file)} file already exists.")
            os._exit(1)

        output_file.touch()
        env_dir = Path(".").absolute()
        package_name = comm.dir_name_to_pkg_name(env_dir.name)
        class_name = comm.dir_name_to_class_name(package_name) + "Env"

        if comm.is_valid_module_name(env_dir.name):
            env_comm_import = f"from env_comm import {class_name}Comm"
        else:
            env_comm_import = (
                "from pathlib import Path\n"
                f"from envo.comm import import_module_from_file\n"
                f'{class_name}Comm = import_module_from_file(Path("env_comm.py")).{class_name}Comm'
            )

        context = {
            "class_name": class_name,
            "name": env_dir.name,
            "package_name": package_name,
            "stage": self.se.stage,
            "emoji": stage_emoji_mapping.get(self.se.stage, "🙂"),
            "selected_addons": self.se.addons,
            "env_comm_import": env_comm_import,
        }

        if not is_comm:
            context["stage"] = self.se.stage

        output_file.write_text(template.render(**context))

    def init_files(self) -> None:
        env_comm_file = Path("env_comm.py")

        if not env_comm_file.exists():
            self._create_from_templ(
                Path("env_comm.py.templ"), env_comm_file, is_comm=True
            )

        env_file = Path(f"env_{self.se.stage}.py")
        self._create_from_templ(Path("env.py.templ"), env_file)
        logger.info(f"Created {self.se.stage} environment 🍰!")

    def handle_command(self, args: argparse.Namespace) -> None:
        if args.version:
            from envo.__version__ import __version__

            logger.info(__version__)
            return

        if args.init:
            self.init_files()
            return

        if args.save:
            self.get_env().dump_dot_env()
            return

        if args.command:
            self.spawn_shell("headless")
            try:
                self.shell.default(args.command)
            except SystemExit as e:
                os._exit(e.code)
            else:
                os._exit(0)

        if args.dry_run:
            self.get_env().print_envs()
        else:
            self.spawn_shell(args.shell)


def _main() -> None:
    # os.environ["PYTHONPATH"] = ":".join(os.environ["PYTHONPATH"].split(":")[:-1])

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage", type=str, default="local", help="Stage to activate.", nargs="?"
    )
    parser.add_argument("--dry-run", default=False, action="store_true")
    parser.add_argument("--version", default=False, action="store_true")
    parser.add_argument("--save", default=False, action="store_true")
    parser.add_argument("--shell", default="fancy")
    parser.add_argument("-c", "--command", default=None)
    parser.add_argument("-i", "--init", nargs="?", const=True, action="store")

    args = parser.parse_args(sys.argv[1:])
    sys.argv = sys.argv[:1]

    if isinstance(args.init, str):
        selected_addons = args.init.split()
    else:
        selected_addons = []

    envo = Envo(
        Envo.Sets(stage=args.stage, addons=selected_addons, init=bool(args.init))
    )
    envo.handle_command(args)


if __name__ == "__main__":
    _main()
