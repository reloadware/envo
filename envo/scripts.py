#!/usr/bin/env python3
import argparse
import os
import re
import sys
import traceback

from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Dict, List, Any, Optional

from ilock import ILock
from rhei import Stopwatch

import envo.e2e
from envo import Env, misc, shell, logger, const, logging
from envo.misc import import_from_file, EnvoError, Inotify, FilesWatcher, Callback
from envo.shell import PromptBase, PromptState, Shell

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal  # type: ignore

package_root = Path(os.path.realpath(__file__)).parent
templates_dir = package_root / "templates"


__all__ = ["_main"]


class Status:
    @dataclass
    class Callbacks:
        on_ready: Callback

    _context_ready: bool
    _reloader_ready: bool
    _shell_ready: bool

    def __init__(self, calls: Callbacks) -> None:
        self.calls = calls
        self._context_ready = False
        self._reloader_ready = False
        self._shell_ready = False

    @property
    def context_ready(self) -> bool:
        return self._context_ready

    @context_ready.setter
    def context_ready(self, value: bool) -> None:
        self._context_ready = value
        logger.debug(f"Context", {"ready": value})
        self._on_status_change()

    @property
    def reloader_ready(self) -> bool:
        return self._context_ready

    @reloader_ready.setter
    def reloader_ready(self, value: bool) -> None:
        self._reloader_ready = value
        logger.debug(f"Reloader", {"ready": value})
        self._on_status_change()

    @property
    def shell_ready(self) -> bool:
        return self._shell_ready

    @shell_ready.setter
    def shell_ready(self, value: bool) -> None:
        self._shell_ready = value
        logger.debug(f"Shell ready", {"ready": value})
        self._on_status_change()

    @property
    def ready(self) -> bool:
        return self.context_ready and self.reloader_ready and self.shell_ready

    def _on_status_change(self) -> None:
        if self.ready:
            logger.debug(f"Everything ready")
            self.calls.on_ready()


class Mode:
    @dataclass
    class Links:
        shell: Shell
        envo: "EnvoBase"

    @dataclass
    class Sets:
        stage: str
        restart_nr: int

    @dataclass
    class Callbacks:
        restart: Callback

    files_watcher: FilesWatcher = NotImplemented
    prompt: PromptBase = NotImplemented

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        self.se = se
        self.li = li
        self.calls = calls

        self.env_dirs = self._get_env_dirs()
        self.executing_cmd = False

        if not self.env_dirs:
            raise EnvoError("Couldn't find any env!\n" 'Forgot to run envo --init" first?')

        self.status = Status(calls=Status.Callbacks(on_ready=Callback(self._on_ready)))

        self.li.shell.calls.reset()
        self.li.shell.calls.on_exit = Callback(self.on_shell_exit)

        self.status.shell_ready = True

        try:
            sys.path.remove(str(self.env_dirs[0]))
        except ValueError:
            pass
        sys.path.insert(0, str(self.env_dirs[0]))

    def __del__(self) -> None:
        env_dir = str(self.env_dirs[0])
        sys.path.remove(env_dir) if env_dir in sys.path else None

    def _on_env_edit(self, event: Inotify.Event) -> None:
        while self.executing_cmd:
            sleep(0.2)

        subscribe_events = ["IN_CLOSE_WRITE", "IN_CREATE", "IN_DELETE", "IN_DELETE_SELF"]

        if any([s in event.type_names for s in subscribe_events]):
            logger.info('Reloading', metadata={"type": "reload", "event": event.type_names, "path": event.path.relative_str})

            self.stop()
            self.calls.restart()
            self.files_watcher.flush()

    def _on_ready(self) -> None:
        self.prompt.state = PromptState.NORMAL
        self.li.shell.set_prompt(self.prompt.as_str())

    def get_context(self) -> Dict[str, Any]:
        return {"logger": logger}

    def load(self) -> None:
        raise NotImplementedError()

    def unload(self) -> None:
        raise NotImplementedError()

    def _on_global_lock_enter(self) -> None:
        self.files_watcher.pause()

    def _on_global_lock_exit(self) -> None:
        self.files_watcher.resume()

    def on_shell_enter(self) -> None:
        raise NotImplementedError()

    def on_shell_exit(self) -> None:
        self.stop()

    def _on_load(self) -> None:
        raise NotImplementedError()

    def _on_unload(self) -> None:
        raise NotImplementedError()

    def start(self) -> None:
        raise NotImplementedError()

    def stop(self) -> None:
        pass

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

    def on_precmd(self, command: str) -> str:
        self.executing_cmd = True
        return command

    def on_stdout(self, command: str, out: str) -> str:
        return out

    def on_stderr(self, command: str, out: str) -> str:
        return out

    def on_postcmd(self, command: str, stdout: List[str], stderr: List[str]) -> None:
        self.executing_cmd = False


class NormalPrompt(PromptBase):
    def __init__(self) -> None:
        super().__init__()

        self.state_prefix_map = {
            PromptState.LOADING: lambda: f"{const.emojis['loading']}({self.name}){self.default}",
            PromptState.NORMAL: lambda: f"{self.emoji}({self.name}){self.default}",
        }


class HeadlessMode(Mode):
    @dataclass
    class Links(Mode.Links):
        pass

    @dataclass
    class Sets(Mode.Sets):
        pass

    @dataclass
    class Callbacks(Mode.Callbacks):
        pass

    env: Env

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        super(HeadlessMode, self).__init__(se=se, li=li, calls=calls)
        self.se = se
        self.li = li
        self.calls = calls
        logger.set_level(logging.Level.INFO)

        logger.debug("Creating Headless Mode")

        self.global_lock = ILock("envo_lock")
        self.global_lock._filepath = str(self.env_dirs[0] / "__envo_lock__")

    def unload(self) -> None:
        if self.env:
            self.on_unload()

        self.li.shell.calls.reset()

    def load(self) -> None:
        self._create_env()

        assert self.env

        self.li.shell.calls.on_enter = Callback(self.on_shell_enter)
        self.li.shell.calls.pre_cmd = Callback(self.on_precmd)
        self.li.shell.calls.on_stdout = Callback(self.on_stdout)
        self.li.shell.calls.on_stderr = Callback(self.on_stderr)
        self.li.shell.calls.post_cmd = Callback(self.on_postcmd)

        self.li.shell.set_variable("env", self.env)
        self.li.shell.set_variable("environ", os.environ)

        self.on_load()

        glob_cmds = [c for c in self.env.get_magic_functions()["command"] if c.kwargs["glob"]]
        for c in glob_cmds:
            self.li.shell.set_variable(c.name, c)

        self._load_context()

    def _on_global_lock_enter(self) -> None:
        self.files_watcher.pause()

    def _on_global_lock_exit(self) -> None:
        self.files_watcher.resume()

    def on_shell_enter(self) -> None:
        functions = self.env.get_magic_functions()["oncreate"]
        for h in functions:
            h()

    def on_shell_exit(self) -> None:
        super(HeadlessMode, self).on_shell_exit()

        functions = self.env.get_magic_functions()["ondestroy"]
        for h in functions:
            h()

    def get_context(self) -> Dict[str, Any]:
        self.status.context_ready = False
        context = super(HeadlessMode, self).get_context()
        functions = self.env.get_magic_functions()["context"]

        for c in functions:
            context.update(c())

        return context

    def _load_context(self) -> None:
        self.li.shell.set_context(self.get_context())

    def on_load(self) -> None:
        self.env.activate()
        functions = self.env.get_magic_functions()["onload"]
        for h in functions:
            h()

    def on_unload(self) -> None:
        self.env.deactivate()
        functions = self.env.get_magic_functions()["onunload"]
        for h in functions:
            h()
        self.li.shell.calls.reset()

    def on_precmd(self, command: str) -> str:
        command = super(HeadlessMode, self).on_precmd(command)
        functions = self.env.get_magic_functions()["precmd"]
        for h in functions:
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command)  # type: ignore
                if ret:
                    command = ret
        return command

    def on_stdout(self, command: str, out: str) -> str:
        functions = self.env.get_magic_functions()["onstdout"]
        for h in functions:
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def on_stderr(self, command: str, out: str) -> str:
        functions = self.env.get_magic_functions()["onstderr"]
        for h in functions:
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def on_postcmd(self, command: str, stdout: List[str], stderr: List[str]) -> None:
        functions = self.env.get_magic_functions()["postcmd"]
        for h in functions:
            if re.match(h.kwargs["cmd_regex"], command):
                h(command=command, stdout=stdout, stderr=stderr)  # type: ignore

        super(HeadlessMode, self).on_postcmd(command, stdout, stderr)

    def _create_env(self) -> None:
        env_dir = self.env_dirs[0]
        package = env_dir.name
        env_name = f"env_{self.se.stage}"
        env_file = env_dir / f"{env_name}.py"

        logger.debug(f'Creating Env from file "{env_file}"')

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
                self.env = module.Env(self.li.shell)
            except ImportError as exc:
                raise EnvoError(f"""Couldn't import "{module_name}" ({exc}).""")
            finally:
                self._delete_init_files()

        self.env.validate()

    def _create_init_files(self) -> None:
        """
        Create __init__.py files if not exist.

        If exist save them to __init__.py.tmp to recover later.
        This step is needed because there might be some content in existing that might crash envo.
        """
        for d in self.env_dirs:
            init_file = d / "__init__.py"

            if init_file.exists():
                logger.debug(f'Attempting to create {str(init_file.absolute())} but exists, renaming to __init__.py.tmp')
                init_file_tmp = d / Path("__init__.py.tmp")
                init_file_tmp.touch()
                init_file_tmp.write_text(init_file.read_text())

            if not init_file.exists():
                logger.debug(f'Creating {str(init_file.absolute())} file')
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
                logger.debug(f'Deleting {str(init_file.absolute())} file')
                init_file.unlink()

            if init_file_tmp.exists():
                init_file.touch()
                init_file.write_text(init_file_tmp.read_text())
                init_file_tmp.unlink()
                logger.debug(f'Recovering {str(init_file)} from {str(init_file_tmp)}')


class NormalMode(HeadlessMode):
    @dataclass
    class Links(HeadlessMode.Links):
        pass

    @dataclass
    class Sets(HeadlessMode.Sets):
        pass

    @dataclass
    class Callbacks(HeadlessMode.Callbacks):
        pass

    env: Env

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        super(NormalMode, self).__init__(se=se, li=li, calls=calls)
        self.se = se
        self.li = li
        self.calls = calls

        self.prompt = NormalPrompt()

        logger.set_level(logging.Level.ERROR)
        logger.debug("Creating NormalMode")

    def _load_context(self) -> None:
        def thread(self: NormalMode) -> None:
            logger.debug("Starting load context thread")

            sw = Stopwatch()
            sw.start()
            self.li.shell.set_context(self.get_context())

            while sw.value <= 0.5:
                sleep(0.1)

            logger.debug("Finished load context thread")
            self.status.context_ready = True

        Thread(target=thread, args=(self,)).start()

    def load(self) -> None:
        def thread(self: NormalMode) -> None:
            self.files_watcher = FilesWatcher(
                FilesWatcher.Sets(
                    watch_root=self.env.get_root_env().root,
                    watch_files=self.env.meta.watch_files,
                    ignore_files=self.env.meta.ignore_files,
                    global_lock_file=Path(self.global_lock._filepath),
                ),
                calls=FilesWatcher.Callbacks(on_trigger=Callback(self._on_env_edit)),
            )
            self.files_watcher.start()
            while not self.files_watcher.ready:
                sleep(0.05)

            self.status.reloader_ready = True

        super(NormalMode, self).load()
        self.prompt.emoji = self.env.meta.emoji
        self.prompt.name = self.env.get_full_name()

        self.li.shell.set_prompt(str(self.prompt))

        Thread(target=thread, args=(self,)).start()

    def stop(self) -> None:
        self.files_watcher.stop()


class EmergencyPrompt(PromptBase):
    msg: str

    def __init__(self) -> None:
        super(PromptBase, self).__init__()

        self.emoji = const.emojis["emergency"]

        self.state_prefix_map = {
            PromptState.LOADING: lambda: f"{{BOLD_RED}}{self.msg}{{NO_COLOR}}\n{const.emojis['loading']}{self.default}",
            PromptState.NORMAL: lambda: f"{{BOLD_RED}}{self.msg}{{NO_COLOR}}\n{self.emoji}{self.default}",
        }


class EmergencyMode(Mode):
    @dataclass
    class Links(Mode.Links):
        pass

    @dataclass
    class Sets(Mode.Sets):
        msg: str

    @dataclass
    class Callbacks(Mode.Callbacks):
        pass

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        super().__init__(se=se, li=li, calls=calls)

        self.se = se
        self.li = li
        self.calls = calls

        self.prompt = EmergencyPrompt()
        self.prompt.state = PromptState.NORMAL
        self.prompt.msg = self.se.msg

        self.li.shell.set_prompt(str(self.prompt))

        logger.set_level(logging.Level.ERROR)

        logger.debug("Creating EmergencyMode")

        self.files_watcher = FilesWatcher(
            FilesWatcher.Sets(watch_root=self.env_dirs[0], watch_files=tuple(), ignore_files=tuple()),
            calls=FilesWatcher.Callbacks(on_trigger=Callback(self._on_env_edit)),
        )
        self.files_watcher.start()
        self.status.reloader_ready = True

    def stop(self) -> None:
        self.files_watcher.stop()

    def load(self) -> None:
        def _load_context(self: EmergencyMode) -> None:
            sleep(0.5)
            self.status.context_ready = True

            self.li.shell.set_context(self.get_context())

        if self.se.restart_nr != 0:
            Thread(target=_load_context, args=(self,)).start()
        else:
            self.status.context_ready = True

    def unload(self) -> None:
        pass


class EnvoBase:
    @dataclass
    class Sets:
        stage: str

    shell: shell.Shell
    mode: Optional[Mode]

    def __init__(self, se: Sets):
        self.se = se
        logger.set_level(logging.Level.INFO)
        self.mode = None

        self.restart_count = -1

    def restart(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError()

    def single_command(self, command: str) -> None:
        self.shell = shell.shells["headless"].create()
        self.restart()

        try:
            self.shell.default(command)
        except SystemExit as e:
            sys.exit(e.code)
        else:
            sys.exit(self.shell.history[-1].rtn)
        finally:
            self.mode.unload()

    def dry_run(self) -> None:
        raise NotImplementedError()

    def save(self) -> None:
        raise NotImplementedError()


class EnvoHeadless(EnvoBase):
    @dataclass
    class Sets(EnvoBase.Sets):
        stage: str

    shell: shell.Shell
    mode: HeadlessMode

    def __init__(self, se: Sets):
        super().__init__(se)
        self.se = se
        logger.set_level(logging.Level.INFO)

        self.restart_count = -1

    def restart(self, *args: Any, **kwargs: Any) -> None:
        self.restart_count += 1
        self.shell.reset()

        self.mode = HeadlessMode(
            se=HeadlessMode.Sets(stage=self.se.stage, restart_nr=self.restart_count),
            calls=HeadlessMode.Callbacks(restart=Callback(self.restart)),
            li=HeadlessMode.Links(shell=self.shell, envo=self),
        )
        self.mode.load()

    def single_command(self, command: str) -> None:
        self.shell = shell.shells["headless"].create()
        self.restart()

        try:
            self.shell.default(command)
        except SystemExit as e:
            sys.exit(e.code)
        else:
            sys.exit(self.shell.history[-1].rtn)
        finally:
            self.mode.unload()

    def dry_run(self) -> None:
        self.shell = shell.shells["headless"].create()
        self.restart()
        content = "\n".join([f'export {k}="{v}"' for k, v in self.mode.env.get_env_vars().items()])
        print(content)

    def save(self) -> None:
        self.shell = shell.shells["headless"].create()
        self.restart()
        path = self.mode.env.dump_dot_env()
        logger.info(f"Saved envs to {str(path)} 💾", print_msg=True)


class Envo(EnvoBase):
    @dataclass
    class Sets(EnvoBase.Sets):
        pass

    environ_before = Dict[str, str]
    inotify: Inotify
    env_dirs: List[Path]
    quit: bool
    env: Env
    mode: Mode

    def __init__(self, se: Sets) -> None:
        super().__init__(se)

        self.quit: bool = False
        self.environ_before = os.environ.copy()  # type: ignore
        logger.set_level(logging.Level.ERROR)

    def restart(self, *args: Any, **kwargs: Any) -> None:
        self.restart_count += 1
        try:
            self.shell.reset()

            if self.mode:
                self.mode.unload()

            self.mode = NormalMode(
                se=NormalMode.Sets(stage=self.se.stage, restart_nr=self.restart_count),
                li=NormalMode.Links(shell=self.shell, envo=self),
                calls=NormalMode.Callbacks(restart=Callback(self.restart)),
            )
            self.mode.load()

        except (EnvoError, Exception) as exc:
            logger.error(f"Cought {type(exc).__name__}", {"error_msg": str(exc)})

            if isinstance(exc, EnvoError):
                msg = str(exc)
            else:
                msg_raw = []
                msg_raw.extend(traceback.format_stack(limit=25)[:-2])
                msg_raw.extend(traceback.format_exception(*sys.exc_info())[1:])
                msg_relevant = ["Traceback (Envo relevant):\n"]
                relevant = False
                for m in msg_raw:
                    if re.search(r"env_.*\.py", m):
                        relevant = True
                    if relevant:
                        msg_relevant.append(m)

                if relevant:
                    msg = "".join(msg_relevant).rstrip()
                else:
                    msg = "".join(msg_raw).rstrip() + "\n"

            self.mode = EmergencyMode(
                se=EmergencyMode.Sets(stage=self.se.stage, restart_nr=self.restart_count, msg=msg),
                li=EmergencyMode.Links(shell=self.shell, envo=self),
                calls=EmergencyMode.Callbacks(restart=Callback(self.restart)),
            )
            self.mode.load()

    def spawn_shell(self, type: Literal["fancy", "simple"]) -> None:
        """
        :param type: shell type
        """
        self.shell = shell.shells[type].create()

        self.restart()
        self.shell.start()
        self.mode.unload()

    def handle_command(self, args: argparse.Namespace) -> None:
        self.spawn_shell(args.shell)


class EnvoCreator:
    @dataclass
    class Sets:
        stage: str

    def __init__(self, se: Sets) -> None:
        logger.debug(f"Starting EnvoCreator")
        self.se = se

    def _create_from_templ(self, templ_file: Path, output_file: Path, is_comm: bool = False) -> None:
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
            "emoji": const.stage_emojis.get(self.se.stage, "🙂"),
            "env_comm_import": env_comm_import,
        }

        if not is_comm:
            context["stage"] = self.se.stage

        misc.render_py_file(templates_dir / templ_file, output=output_file, context=context)

    def create(self) -> None:
        env_comm_file = Path("env_comm.py")
        if not env_comm_file.exists():
            self._create_from_templ(Path("env_comm.py.templ"), env_comm_file, is_comm=True)

        env_file = Path(f"env_{self.se.stage}.py")
        self._create_from_templ(Path("env.py.templ"), env_file)
        print(f"Created {self.se.stage} environment 🍰!")


def _main() -> None:
    logger.debug(f"Starting")

    sys.argv[0] = "/home/kwazar/Code/opensource/envo/.venv/bin/xonsh"
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", type=str, default="local", help="Stage to activate.", nargs="?")
    parser.add_argument("--dry-run", default=False, action="store_true")
    parser.add_argument("--version", default=False, action="store_true")
    parser.add_argument("--save", default=False, action="store_true")
    parser.add_argument("--shell", default="fancy")
    parser.add_argument("-c", "--command", default=None)
    parser.add_argument("-i", "--init", default=False, action="store_true")

    args = parser.parse_args(sys.argv[1:])
    sys.argv = sys.argv[:1]

    try:
        if args.version:
            from envo.__version__ import __version__

            print(__version__)
            return

        if args.init:
            envo_creator = EnvoCreator(EnvoCreator.Sets(stage=args.stage))
            envo_creator.create()
        elif args.command:
            envo.e2e.envo = env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=args.stage))
            env_headless.single_command(args.command)
        elif args.dry_run:
            envo.e2e.envo = env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=args.stage))
            env_headless.dry_run()
        elif args.save:
            envo.e2e.envo = env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=args.stage))
            env_headless.save()
        else:
            envo.e2e.envo = e = Envo(Envo.Sets(stage=args.stage))
            e.handle_command(args)
    except EnvoError as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    _main()
