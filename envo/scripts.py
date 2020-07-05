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
from typing import Dict, List, Any

from ilock import ILock

from envo import Env, misc, shell, logger, const
from envo.misc import import_from_file, EnvoError, Inotify, FilesWatcher, Callback
from envo.shell import PromptBase, PromptState, Shell

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal  # type: ignore

package_root = Path(os.path.realpath(__file__)).parent
templates_dir = package_root / "templates"


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

    def __init__(self, se: Sets, li: Links, callbacks: Callbacks) -> None:
        self.se = se
        self.li = li
        self.callbacks = callbacks

        self.env_dirs = self._get_env_dirs()
        self.executing_cmd = False

        if not self.env_dirs:
            raise EnvoError("Couldn't find any env!\n" 'Forgot to run envo --init" first?')

        self.li.shell.callbacks.reset()
        self.li.shell.callbacks.on_exit = Callback(self.on_shell_exit)

        # TODO: remove on exit?
        sys.path.insert(0, str(self.env_dirs[0]))

    def _on_env_edit(self, event: Inotify.Event) -> None:
        while self.executing_cmd:
            sleep(0.2)

        if ("IN_CLOSE_WRITE" in event.type_names or "IN_CREATE" in event.type_names) and event.path.absolute.is_file():
            logger.info(f'\nDetected changes in "{event.path.relative_str}"')
            logger.info("Reloading...")

            self.stop()
            self.callbacks.restart()

    def _update_context(self) -> None:
        self.li.shell.update_context({"logger": logger})

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
    name: str

    def __init__(self) -> None:
        super(PromptBase, self).__init__()

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

    def __init__(self, se: Sets, li: Links, callbacks: Callbacks) -> None:
        super(HeadlessMode, self).__init__(se=se, li=li, callbacks=callbacks)
        self.se = se
        self.li = li
        self.callbacks = callbacks
        logger.set_level("INFO")

        self.global_lock = ILock("envo_lock")
        self.global_lock._filepath = str(self.env_dirs[0] / "__envo_lock__")

        self.loading = False

    def unload(self) -> None:
        if self.env:
            self.on_unload()

        self.li.shell.callbacks.reset()

    def load(self) -> None:
        self._create_env()

        assert self.env

        self.env.validate()

        self.li.shell.callbacks.on_enter = Callback(self.on_shell_enter)
        self.li.shell.callbacks.pre_cmd = Callback(self.on_precmd)
        self.li.shell.callbacks.on_stdout = Callback(self.on_stdout)
        self.li.shell.callbacks.on_stderr = Callback(self.on_stderr)
        self.li.shell.callbacks.post_cmd = Callback(self.on_postcmd)

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

    def _update_context(self) -> None:
        self.loading = True
        super(HeadlessMode, self)._update_context()
        functions = self.env.get_magic_functions()["context"]
        for c in functions:
            context = c()
            self.li.shell.update_context(context)

        self.loading = False

    def _load_context(self) -> None:
        self._update_context()

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
        self.li.shell.callbacks.reset()

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

    def __init__(self, se: Sets, li: Links, callbacks: Callbacks) -> None:
        super(NormalMode, self).__init__(se=se, li=li, callbacks=callbacks)
        self.se = se
        self.li = li
        self.callbacks = callbacks

        logger.set_level("ERROR")

    def _load_context(self) -> None:
        def thread(self: NormalMode) -> None:
            # Don't change to loading emoji on the first run
            Thread(target=self._update_context).start()

            sleep(0.01)

            if self.se.restart_nr == 0:
                if self.loading:
                    self.prompt.state = PromptState.LOADING
                    self.li.shell.set_prompt(self.prompt.as_str())
            else:
                self.prompt.state = PromptState.LOADING
                self.li.shell.set_prompt(self.prompt.as_str())

            if self.se.restart_nr != 0:
                sleep(0.5)

            while self.loading:
                sleep(0.1)

            self.prompt.state = PromptState.NORMAL
            self.li.shell.set_prompt(self.prompt.as_str())

        Thread(target=thread, args=(self,)).start()

    def load(self) -> None:
        super(NormalMode, self).load()

        self.prompt = NormalPrompt()
        self.prompt.state = PromptState.NORMAL
        self.prompt.emoji = self.env.meta.emoji
        self.prompt.name = self.env.get_full_name()

        self.li.shell.set_prompt(str(self.prompt))

        self.files_watcher = FilesWatcher(
            FilesWatcher.Sets(
                watch_root=self.env.get_root_env().root,
                watch_files=self.env.meta.watch_files,
                ignore_files=self.env.meta.ignore_files,
                global_lock_file=Path(self.global_lock._filepath),
            ),
            callbacks=FilesWatcher.Callbacks(on_trigger=Callback(self._on_env_edit)),
        )
        self.files_watcher.start()

    def stop(self) -> None:
        self.files_watcher.stop()

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

    def __init__(self, se: Sets, li: Links, callbacks: Callbacks) -> None:
        super(EmergencyMode, self).__init__(se=se, li=li, callbacks=callbacks)

        self.se = se
        self.li = li
        self.callbacks = callbacks

        self.prompt = EmergencyPrompt()
        self.prompt.state = PromptState.NORMAL
        self.prompt.msg = self.se.msg

        self.li.shell.set_prompt(str(self.prompt))

        logger.set_level("ERROR")

        self.files_watcher = FilesWatcher(
            FilesWatcher.Sets(watch_root=self.env_dirs[0], watch_files=tuple(), ignore_files=tuple()),
            callbacks=FilesWatcher.Callbacks(on_trigger=Callback(self._on_env_edit)),
        )
        self.files_watcher.start()

        self._update_context()

    def stop(self) -> None:
        self.files_watcher.stop()

    def load(self) -> None:
        def _load_context(self: EmergencyMode) -> None:
            self.prompt.state = PromptState.LOADING
            self.li.shell.set_prompt(self.prompt.as_str())

            sleep(0.5)

            self.prompt.state = PromptState.NORMAL
            self.li.shell.set_prompt(self.prompt.as_str())

        if self.se.restart_nr != 0:
            Thread(target=_load_context, args=(self,)).start()

    def unload(self) -> None:
        pass


class EnvoBase:
    @dataclass
    class Sets:
        stage: str

    shell: shell.Shell
    mode: Mode

    def __init__(self, se: Sets):
        self.se = se
        logger.set_level("INFO")

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
        logger.set_level("INFO")

        self.restart_count = -1

    def restart(self, *args: Any, **kwargs: Any) -> None:
        self.restart_count += 1
        self.shell.reset()

        self.mode = HeadlessMode(
            se=HeadlessMode.Sets(stage=self.se.stage, restart_nr=self.restart_count),
            callbacks=HeadlessMode.Callbacks(restart=Callback(self.restart)),
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
        self.mode.env.dump_dot_env()


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
        logger.set_level("ERROR")

    def restart(self, *args: Any, **kwargs: Any) -> None:
        self.restart_count += 1
        try:
            self.shell.reset()

            if hasattr(self, "mode"):
                self.mode.unload()

            self.mode = NormalMode(
                se=NormalMode.Sets(stage=self.se.stage, restart_nr=self.restart_count),
                li=NormalMode.Links(shell=self.shell, envo=self),
                callbacks=NormalMode.Callbacks(restart=Callback(self.restart)),
            )
            self.mode.load()

        except (EnvoError, Exception) as exc:
            if isinstance(exc, EnvoError):
                msg = str(exc)
            else:
                msg_raw = []
                msg_raw.extend(traceback.format_stack(limit=25)[:-2])
                msg_raw.extend(traceback.format_exception(*sys.exc_info())[1:])
                msg_relevant = ["Traceback (Envo relevant):\n"]
                for m in msg_raw:
                    msg_relevant.append(m)

                if len(msg_relevant) > 1:
                    msg = "".join(msg_relevant).rstrip()
                else:
                    msg = "".join(msg_raw).rstrip()
            self.mode = EmergencyMode(
                se=EmergencyMode.Sets(stage=self.se.stage, restart_nr=self.restart_count, msg=msg),
                li=EmergencyMode.Links(shell=self.shell, envo=self),
                callbacks=EmergencyMode.Callbacks(restart=Callback(self.restart)),
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
        logger.info(f"Created {self.se.stage} environment 🍰!")


def _main() -> None:
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
            env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=args.stage))
            env_headless.single_command(args.command)
        elif args.dry_run:
            env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=args.stage))
            env_headless.dry_run()
        elif args.save:
            env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=args.stage))
            env_headless.save()
        else:
            envo = Envo(Envo.Sets(stage=args.stage))
            envo.handle_command(args)
    except EnvoError as e:
        logger.error(str(e))


if __name__ == "__main__":
    _main()
