#!/usr/bin/env python3
import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Dict, List, Optional

from ilock import ILock
from loguru import logger

from envo import Env, misc, shell
from envo.misc import import_from_file, EnvoError, Inotify

from globmatch_temp import glob_match

from envo.shell import Prompt

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal  # type: ignore


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


class FilesWatcher:
    inotify: Optional[Inotify]

    def __init__(self, envo: "Envo"):
        self.envo = envo
        self.inotify = None

    def _thread(self, watch_root: Path) -> None:
        assert self.inotify
        for event in self.inotify.event_gen():
            # check if locked
            # locked means that other envo instance is creating temp __init__.py files
            # we don't want to handle this so we skip
            (_, type_names, path, filename) = event
            full_path = Path(path) / Path(filename)
            full_path_str = str(full_path)

            if full_path.is_dir():
                full_path_str += "/"

            absolute_path = full_path.absolute()

            relative_path = full_path.relative_to(watch_root)
            relative_path_str = str(relative_path)

            if relative_path.is_dir():
                relative_path_str += "/"

            # Disable events on global lock
            if full_path.name == Path(self.envo.global_lock._filepath).name:
                if "IN_CREATE" in type_names:
                    self.inotify.pause(exempt=Path(self.envo.global_lock._filepath))
                    # Enable events for lock file so inotify can be resumed on lock end

                if "IN_DELETE" in type_names:
                    self.inotify.resume()
                continue

            if "IN_CREATE" in type_names:
                self.inotify.add_watch(absolute_path)

            if "IN_DELETE" in type_names:
                self.inotify.remove_watch(absolute_path)

            if ("IN_CLOSE_WRITE" in type_names or "IN_CREATE" in type_names) and Path(
                full_path
            ).is_file():
                if glob_match(relative_path_str, self.inotify.exclude):
                    return

                if not glob_match(relative_path_str, self.inotify.include):
                    return
                logger.info(f'\nDetected changes in "{full_path_str}".')
                logger.info("Reloading...")
                self.envo.restart()
                print("\r" + self.envo.shell.prompt, end="")
                return

    def start(self, emergency_mode: bool = False) -> None:
        if not emergency_mode:
            watch_root = self.envo.env.get_root_env().root
        else:
            # We have to set the watch root the most deep env because
            watch_root = self.envo.env_dirs[-1]

        self.inotify = Inotify(watch_root)
        self.inotify.include = ["**/env_*.py"]

        if not emergency_mode:
            self.inotify.include.extend(self.envo.env.meta.watch_files)
            self.inotify.exclude = list(self.envo.env.meta.ignore_files)

        self.inotify.stop = False
        self.inotify.remove_watches()
        self.inotify.add_watch(watch_root)

        Thread(target=self._thread, args=(watch_root,)).start()

    def stop(self) -> None:
        if not self.inotify:
            return

        self.inotify.stop = True
        env_comm = self.envo.env_dirs[0] / "env_comm.py"
        # Save the same content to trigger inotify event
        env_comm.read_text()


class EnvoHeadless:
    @dataclass
    class Sets:
        stage: str

    env: Env
    shell: shell.Shell

    def __init__(self, se: Sets):
        self.se = se
        self.env_dirs = self._get_env_dirs()
        if not self.env_dirs:
            raise EnvoError(
                "Couldn't find any env!\n" 'Forgot to run envo --init" first?'
            )

        sys.path.insert(0, str(self.env_dirs[0]))

        self.global_lock = ILock("envo_lock")
        self.global_lock._filepath = str(self.env_dirs[0] / "__envo_lock__")

    def create_env(self) -> Env:
        env_dir = self.env_dirs[0]
        package = env_dir.name
        env_name = f"env_{self.se.stage}"
        env_file = env_dir / f"{env_name}.py"

        module_name = f"{package}.{env_name}"

        # We have to lock this part in case there's other shells concurrently executing this code
        with self.global_lock:
            self._create_init_files()

            # unload modules
            for m in list(sys.modules.keys())[:]:
                if m.startswith("env_"):
                    sys.modules.pop(m)
            try:
                module = import_from_file(env_file)
                env: Env
                env = module.Env()
                return env
            except ImportError as exc:
                raise EnvoError(f"""Couldn't import "{module_name}" ({exc}).""")
            finally:
                self._delete_init_files()

    def handle_command(self, args: argparse.Namespace) -> None:
        self.env = self.create_env()
        self.shell = shell.shells["headless"].create()
        self._init_shell()
        try:
            self.shell.default(args.command)
        except SystemExit as e:
            sys.exit(e.code)
        else:
            sys.exit(self.shell.history[-1].rtn)

    def _set_context(self) -> None:
        for c in self.env.get_magic_functions()["context"]:
            context = c()
            self.shell.update_context(context)

    def _init_shell(self) -> None:
        self.shell.reset()
        self.shell.set_variable("env", self.env)
        self.shell.set_variable("environ", self.shell.environ)

        self.context_thread = Thread(target=self._set_context)
        self.context_thread.start()

        glob_cmds = [
            c for c in self.env.get_magic_functions()["command"] if c.kwargs["glob"]
        ]
        for c in glob_cmds:
            self.shell.set_variable(c.name, c)
        self.shell.pre_cmd = self._on_precmd
        self.shell.on_stdout = self._on_stdout
        self.shell.on_stderr = self._on_stderr
        self.shell.post_cmd = self._on_postcmd

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

    def _on_precmd(self, command: str) -> str:
        for h in self.env.get_magic_functions()["precmd"]:
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command)  # type: ignore
                if ret:
                    command = ret
        return command

    def _on_stdout(self, command: str, out: str) -> str:
        for h in self.env.get_magic_functions()["onstdout"]:
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def _on_stderr(self, command: str, out: str) -> str:
        for h in self.env.get_magic_functions()["onstderr"]:
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def _on_postcmd(self, command: str, stdout: List[str], stderr: List[str]) -> None:
        for h in self.env.get_magic_functions()["postcmd"]:
            if re.match(h.kwargs["cmd_regex"], command):
                h(command=command, stdout=stdout, stderr=stderr)  # type: ignore


class Envo(EnvoHeadless):
    @dataclass
    class Sets(EnvoHeadless.Sets):
        pass

    environ_before = Dict[str, str]
    inotify: Inotify
    env_dirs: List[Path]
    quit: bool
    env: Env

    def __init__(self, se: Sets) -> None:
        super().__init__(se)

        self.quit: bool = False

        self.environ_before = os.environ.copy()  # type: ignore
        self.files_watcher = FilesWatcher(self)

        self.lock_dir = Path("/tmp/envo")
        if not self.lock_dir.exists():
            self.lock_dir.mkdir()

        self.prompt = Prompt()

    def spawn_shell(self, type: Literal["fancy", "simple"]) -> None:
        """
        :param type: shell type
        """
        self.shell = shell.shells[type].create()

        self.restart()
        self.shell.start()
        self.files_watcher.stop()
        self._on_unload()
        self._on_destroy()

    def restart(self) -> None:
        try:
            self.prompt.reset()
            self.files_watcher.stop()

            os.environ = self.environ_before.copy()  # type: ignore

            if not hasattr(self, "env"):
                self.env = self.create_env()
                self._on_create()
            else:
                self._on_unload()
                self.env = self.create_env()

            self.env.validate()
            self.env.activate()
            self._on_load()

            self._init_shell()

            if self.context_thread.is_alive():
                self.prompt.loading = True

            self.prompt.emoji = self.env.meta.emoji
            self.prompt.name = self.env.get_full_name()
            self.shell.environ.update(self.env.get_env_vars())
        except EnvoError as exc:
            logger.error(exc)
            self.prompt.emergency = True
            self.files_watcher.start(emergency_mode=True)
        except Exception:
            from traceback import print_exc

            print_exc()
            self.prompt.emergency = True
            self.files_watcher.start(emergency_mode=True)
        else:
            self.files_watcher.start()
        finally:
            self.shell.set_prompt(str(self.prompt))

    def _on_create(self) -> None:
        for h in self.env.get_magic_functions()["oncreate"]:
            h()

    def _on_destroy(self) -> None:
        for h in self.env.get_magic_functions()["ondestroy"]:
            h()

    def _on_load(self) -> None:
        for h in self.env.get_magic_functions()["onload"]:
            h()

    def _on_unload(self) -> None:
        for h in self.env.get_magic_functions()["onunload"]:
            h()

    def _set_context(self) -> None:
        super()._set_context()
        self.prompt.loading = False
        self.shell.set_prompt(str(self.prompt))

    def handle_command(self, args: argparse.Namespace) -> None:
        if args.save:
            self.create_env().dump_dot_env()
            return

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


class EnvoCreator:
    @dataclass
    class Sets:
        stage: str
        addons: List[str]

    def __init__(self, se: Sets) -> None:
        self.se = se

        self.addons = ["venv"]

        unknown_addons = set(self.se.addons) - set(self.addons)
        if unknown_addons:
            raise EnvoError(f"Unknown addons {unknown_addons}")

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
        from jinja2 import Environment

        Environment(keep_trailing_newline=True)

        if output_file.exists():
            raise EnvoError(f"{str(output_file)} file already exists.")

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

        misc.render_py_file(
            templates_dir / templ_file, output=output_file, context=context
        )

    def create(self) -> None:
        env_comm_file = Path("env_comm.py")
        if not env_comm_file.exists():
            self._create_from_templ(
                Path("env_comm.py.templ"), env_comm_file, is_comm=True
            )

        env_file = Path(f"env_{self.se.stage}.py")
        self._create_from_templ(Path("env.py.templ"), env_file)
        logger.info(f"Created {self.se.stage} environment 🍰!")


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

    try:
        if args.version:
            from envo.__version__ import __version__

            logger.info(__version__)
            return

        if args.init:
            if isinstance(args.init, str):
                selected_addons = args.init.split()
            else:
                selected_addons = []
            envo_creator = EnvoCreator(
                EnvoCreator.Sets(stage=args.stage, addons=selected_addons)
            )
            envo_creator.create()
        elif args.command:
            envo = EnvoHeadless(EnvoHeadless.Sets(stage=args.stage))
            envo.handle_command(args)
        else:
            envo = Envo(Envo.Sets(stage=args.stage))
            envo.handle_command(args)
    except EnvoError as e:
        logger.error(e)


if __name__ == "__main__":
    _main()
