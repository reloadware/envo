#!/usr/bin/env python3
import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Dict, List, Literal

from ilock import ILock
from inotify.adapters import Inotify  # type: ignore
from jinja2 import Environment, Template
from loguru import logger

from envo import Env, misc, shell
from envo.misc import import_from_file

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


class Envo:
    @dataclass
    class Sets:
        stage: str
        addons: List[str]
        init: bool

    class EnvoError(Exception):
        pass

    environ_before = Dict[str, str]
    selected_addons: List[str]
    addons: List[str]
    files_watchdog_thread: Thread
    shell: shell.Shell
    inotify: Inotify
    env_dirs: List[Path]
    quit: bool

    def __init__(self, sets: Sets) -> None:
        self.se = sets

        self.addons = ["venv"]

        unknown_addons = [a for a in self.se.addons if a not in self.addons]
        if unknown_addons:
            raise self.EnvoError(f"Unknown addons {unknown_addons}")

        self.inotify = Inotify()

        self.env_dirs = self._get_env_dirs()
        self.quit: bool = False

        self.environ_before = os.environ.copy()  # type: ignore

    def spawn_shell(self, type: Literal["fancy", "simple", "headless"]) -> None:
        """

        :param type: shell type
        """
        if not self.env_dirs:
            raise self.EnvoError(
                "Couldn't find any env!\n" 'Forgot to run envo --init" first?'
            )

        self.shell = shell.shells[type].create()
        self._start_files_watchdog()
        self.restart()
        self.shell.start()
        self._stop_files_watchdog()

    def restart(self) -> None:
        try:
            os.environ = self.environ_before.copy()  # type: ignore
            env: Env = self.create_env()
            env_prefix = f"{env.meta.emoji}({env.get_full_name()})"
            env.validate()
            env.activate()
            self.shell.reset()
            self.shell.set_variable("env", env)
            self.shell.set_variable("environ", self.shell.environ)

            glob_cmds = [c for c in env.get_commands() if c.glob]
            for c in glob_cmds:
                self.shell.set_variable(c.name, c)

            self.shell.environ.update(env.get_env_vars())
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
            if self.quit:
                return

            (_, type_names, path, filename) = event
            if "IN_CLOSE_WRITE" in type_names:
                logger.info(f'\nDetected changes in "{str(path)}".')
                logger.info("Reloading...")
                self.restart()
                print("\r" + self.shell.prompt, end="")

    def _start_files_watchdog(self) -> None:
        for d in self.env_dirs:
            comm_env_file = d / "env_comm.py"
            env_file = d / f"env_{self.se.stage}.py"
            self.inotify.add_watch(str(comm_env_file))
            self.inotify.add_watch(str(env_file))

        self.files_watchdog_thread = Thread(target=self._files_watchdog)
        self.files_watchdog_thread.start()

    def _stop_files_watchdog(self) -> None:
        self.quit = True
        env_comm = self.env_dirs[0] / "env_comm.py"
        # Save the same content to trigger inotify event
        env_comm.read_text()

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
        """
        Create __init__.py files if not exist.

        If exist save them to __init__.py.tmp to recover later.
        This step is needed because there might be some content in existing that might crash envo.
        """

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
        """
        Delete __init__.py files if crated otherwise recover.
        :return:
        """
        for d in self.env_dirs:
            init_file = d / Path("__init__.py")
            init_file_tmp = d / Path("__init__.py.tmp")

            if init_file.read_text() == "# __envo_delete__":
                init_file.unlink()

            if init_file_tmp.exists():
                init_file.touch()
                init_file.write_text(init_file_tmp.read_text())
                init_file_tmp.unlink()

    def create_env(self) -> Env:
        env_dir = self.env_dirs[0]
        package = env_dir.name
        env_name = f"env_{self.se.stage}"
        env_file = env_dir / f"{env_name}.py"

        module_name = f"{package}.{env_name}"

        # We have to lock this part in case there's other shells concurrently executing this code
        with ILock("envo_lock"):
            self._create_init_files()

            # unload modules
            for m in list(sys.modules.keys())[:]:
                if m.startswith("env_"):
                    sys.modules.pop(m)

            try:
                sys.path.insert(0, str(env_dir))
                module = import_from_file(env_file)
                env: Env
                env = module.Env()
                sys.path.pop(0)
                return env
            except ImportError as exc:
                raise self.EnvoError(f"""Couldn't import "{module_name}" ({exc}).""")
            finally:
                self._delete_init_files()

    def _create_from_templ(
        self, templ_file: Path, output_file: Path, is_comm: bool = False
    ) -> None:
        """
        Create env file from template.

        :param templ_file:
        :param output_file:
        :param is_comm:
        :return:
        """
        Environment(keep_trailing_newline=True)
        template = Template((templates_dir / templ_file).read_text())
        if output_file.exists():
            raise self.EnvoError(f"{str(output_file)} file already exists.")

        output_file.touch()
        env_dir = Path(".").absolute()
        package_name = misc.dir_name_to_pkg_name(env_dir.name)
        class_name = misc.dir_name_to_class_name(package_name) + "Env"

        if misc.is_valid_module_name(env_dir.name):
            env_comm_import = f"from env_comm import {class_name}Comm"
        else:
            env_comm_import = (
                "from pathlib import Path\n"
                f"from envo.misc import import_from_file\n\n\n"
                f'{class_name}Comm = import_from_file(Path("env_comm.py")).{class_name}Comm'
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
            self.create_env().dump_dot_env()
            return

        if args.command:
            self.spawn_shell("headless")
            try:
                self.shell.default(args.command)
            except SystemExit as e:
                sys.exit(e.code)
            else:
                sys.exit(self.shell.history[-1].rtn)

        if args.dry_run:
            content = "\n".join(
                [
                    f'export {k}="{v}"'
                    for k, v in self.create_env().get_env_vars().items()
                ]
            )
            print(content)
        else:
            self.spawn_shell(args.shell)


def _main() -> None:
    sys.argv[0] = "/home/kwazar/Code/opensource/envo/.venv/bin/xonsh"
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
    try:
        envo.handle_command(args)
    except Envo.EnvoError as e:
        logger.error(e)


if __name__ == "__main__":
    _main()
