#!/usr/bin/env python3
import argparse
import os
import re
import sys
import traceback
from collections import OrderedDict

from dataclasses import dataclass
from pathlib import Path
from threading import Thread, Lock
from time import sleep
from typing import Dict, List, Any, Optional

from ilock import ILock
from rhei import Stopwatch

import envo.e2e
from envo import Env, misc, shell, logger, const, logging
from envo.misc import import_from_file, EnvoError, Inotify, Callback
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
        return self._reloader_ready

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


class CantFindEnvFile(EnvoError):
    def __init__(self):
        super().__init__("Couldn't find any env!\n" 'Forgot to run envo --init" first?')


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

    prompt: PromptBase = NotImplemented
    reloader_enabled: bool = NotImplemented

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        self.se = se
        self.li = li
        self.calls = calls

        self.env_dirs = self._get_env_dirs()

        if not self.env_dirs:
            raise CantFindEnvFile

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

    def _on_ready(self) -> None:
        self.prompt.state = PromptState.NORMAL
        self.li.shell.set_prompt(self.prompt.as_str())

    def get_context(self) -> Dict[str, Any]:
        return {}

    def load(self) -> None:
        raise NotImplementedError()

    def unload(self) -> None:
        raise NotImplementedError()

    def on_shell_exit(self) -> None:
        self.stop()

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
            if path == Path("/"):
                break

            for p in path.glob("env_*.py"):
                if p.parent not in ret:
                    ret.append(p.parent)

            path = path.parent

        return ret

    def on_precmd(self, command: str) -> str:
        return command

    def on_stdout(self, command: str, out: str) -> str:
        return out

    def on_stderr(self, command: str, out: str) -> str:
        return out

    def on_postcmd(self, command: str, stdout: List[str], stderr: List[str]) -> None:
        pass

    def _create_env_object(self, file: Path) -> Env:
        def on_reloader_ready():
            self.status.reloader_ready=True

        def on_context_ready():
            self.status.context_ready=True

        env_class = Env.build_env_from_file(file)
        env = env_class(self.li.shell,
                        calls=Env.Callbacks(restart=self.calls.restart,
                                            reloader_ready=Callback(on_reloader_ready),
                                            context_ready=Callback(on_context_ready)),
                        reloader_enabled=self.reloader_enabled)
        return env


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
    reloader_enabled: bool = False

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        super(HeadlessMode, self).__init__(se=se, li=li, calls=calls)
        self.se = se
        self.li = li
        self.calls = calls

        self.env = None

        logger.set_level(logging.Level.INFO)

        logger.debug("Creating Headless Mode")

    def unload(self) -> None:
        if self.env:
            self.on_unload()

        self.li.shell.calls.reset()

    def load(self) -> None:
        self.li.shell.set_context({"logger": logger})

        self._create_env()

        assert self.env

        self.li.shell.calls.on_enter = Callback(self.env.on_create)
        self.li.shell.calls.pre_cmd = Callback(self.on_precmd)
        self.li.shell.calls.on_stdout = Callback(self.on_stdout)
        self.li.shell.calls.on_stderr = Callback(self.on_stderr)
        self.li.shell.calls.post_cmd = Callback(self.on_postcmd)

        self.li.shell.set_variable("env", self.env)
        self.li.shell.set_variable("environ", os.environ)

        self.env.on_load()

    def on_shell_exit(self) -> None:
        super(HeadlessMode, self).on_shell_exit()

        functions = self.env.get_magic_functions()["ondestroy"]
        for h in functions.values():
            h()

    def on_unload(self) -> None:
        self.env.deactivate()
        functions = self.env.get_magic_functions()["onunload"]
        for h in functions.values():
            h()
        self.li.shell.calls.reset()

    def on_precmd(self, command: str) -> str:
        command = super(HeadlessMode, self).on_precmd(command)
        functions = self.env.get_magic_functions()["precmd"]
        for h in functions.values():
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command)  # type: ignore
                if ret:
                    command = ret
        return command

    def on_stdout(self, command: str, out: str) -> str:
        functions = self.env.get_magic_functions()["onstdout"]
        for h in functions.values():
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def on_stderr(self, command: str, out: str) -> str:
        functions = self.env.get_magic_functions()["onstderr"]
        for h in functions.values():
            if re.match(h.kwargs["cmd_regex"], command):
                ret = h(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def on_postcmd(self, command: str, stdout: List[str], stderr: List[str]) -> None:
        functions = self.env.get_magic_functions()["postcmd"]
        for h in functions.values():
            if re.match(h.kwargs["cmd_regex"], command):
                h(command=command, stdout=stdout, stderr=stderr)  # type: ignore

        super(HeadlessMode, self).on_postcmd(command, stdout, stderr)

    def _find_env(self) -> Path:
        # TODO: Test this
        if self.se.stage:
            matches: Dict[Path, const.Stage] = OrderedDict()
            for d in self.env_dirs:
                for p in d.glob("env_*.py"):
                    stage = const.STAGES.filename_to_stage(p.name)
                    if stage:
                        matches[p] = stage

            results = [p for p, s in matches.items() if self.se.stage == s.name]
            if results:
                return results[0]
        else:
            for d in self.env_dirs:
                matches: Dict[Path, const.Stage] = OrderedDict()
                for p in d.glob("env_*.py"):
                    stage = const.STAGES.filename_to_stage(p.name)
                    if stage:
                        matches[p] = stage

                results = sorted(matches.items(), key=lambda x: x[1].priority, reverse=True)
                if results:
                    return results[0][0]

        raise CantFindEnvFile()

    def _create_env(self) -> None:
        env_file = self._find_env()

        logger.debug(f'Creating Env from file "{env_file}"')

        # unload modules
        for m in list(sys.modules.keys())[:]:
            if m.startswith("env_"):
                sys.modules.pop(m)
        try:
            self.env = self._create_env_object(env_file)
        except ImportError as exc:
            raise EnvoError(f"""Couldn't import "{env_file}" ({exc}).""")


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
    reloader_enabled: bool = True

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        super(NormalMode, self).__init__(se=se, li=li, calls=calls)
        self.se = se
        self.li = li
        self.calls = calls

        self.prompt = NormalPrompt()

        logger.set_level(logging.Level.ERROR)
        logger.debug("Creating NormalMode")

    def load(self) -> None:
        super(NormalMode, self).load()
        self.prompt.emoji = self.env.meta.emoji
        self.prompt.name = self.env.get_name()

        self.li.shell.set_prompt(str(self.prompt))

    def stop(self) -> None:
        self.env.exit()


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

    def _on_env_edit(self, event: Inotify.Event) -> None:
        if "IN_CLOSE_WRITE" in event.type_names:
            self._reload_lock.acquire()
            self.files_watcher.stop()

            logger.info('Reloading',
                        metadata={"type": "reload", "event": event.type_names, "path": event.path.absolute.resolve()})

            self.calls.restart()

            self._reload_lock.release()

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        super().__init__(se=se, li=li, calls=calls)

        self.se = se
        self.li = li
        self.calls = calls

        self.prompt = EmergencyPrompt()
        self.prompt.state = PromptState.NORMAL
        self.prompt.msg = self.se.msg

        self._reload_lock = Lock()

        self.li.shell.set_prompt(str(self.prompt))

        logger.set_level(logging.Level.ERROR)

        logger.debug("Creating EmergencyMode")

        self.files_watcher = Inotify(
            Inotify.Sets(root=self.env_dirs[0], include=["env_*.py"],
                         exclude=[r"**/.*", r"**/*~", r"**/__pycache__"]),
            calls=Inotify.Callbacks(on_event=Callback(self._on_env_edit)),
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
        self.stop()


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

    def _create_from_templ(self, stage: str, parent: str = "") -> None:
        """
        Create env file from template.

        :param templ_file:
        :param output_file:
        :param is_comm:
        :return:
        """
        from jinja2 import Environment

        Environment(keep_trailing_newline=True)

        output_file = Path(f"env_{stage}.py")

        if output_file.exists():
            raise EnvoError(f"{str(output_file)} file already exists.")

        env_dir = Path(".").absolute()
        package_name = misc.dir_name_to_pkg_name(env_dir.name)
        class_name = misc.dir_name_to_class_name(package_name) + "Env"

        context = {"class_name": class_name, "name": env_dir.name, "stage": stage,
                   "emoji": const.STAGES.get_stage_name_to_emoji().get(stage, "🙂"),
                   "parents": f'"{parent}"'if parent else ""}

        templ_file = Path("env.py.templ")
        misc.render_py_file(templates_dir / templ_file, output=output_file, context=context)

    def create(self) -> None:
        if not self.se.stage:
            self.se.stage = "comm"

        self._create_from_templ(self.se.stage, parent="env_comm.py" if self.se.stage != "comm" else "")

        if self.se.stage != "comm" and not Path("env_comm.py").exists():
            self._create_from_templ("comm")

        print(f"Created {self.se.stage} environment 🍰!")


def _main() -> None:
    logger.debug(f"Starting")

    sys.argv[0] = "/home/kwazar/Code/opensource/envo/.venv/bin/xonsh"
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", type=str, default=None, help="Stage to activate.", nargs="?")
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
