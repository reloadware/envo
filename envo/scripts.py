#!/usr/bin/env python3
import argparse
import os
import re
import sys
import traceback
from collections import OrderedDict
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Dict, List, Optional

from ilock import ILock
from rhei import Stopwatch

import envo.e2e
from envo import Env, const, logger, logging, misc, shell
from envo.env import EnvBuilder
from envo.misc import Callback, EnvoError, Inotify, import_from_file
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

    def __init__(self, calls: Callbacks) -> None:
        self.calls = calls
        self._context_ready = False
        self._reloader_ready = False

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
    def ready(self) -> bool:
        return self.context_ready and self.reloader_ready

    def _on_status_change(self) -> None:
        if self.ready:
            logger.debug(f"Everything ready")
            self.calls.on_ready()


class CantFindEnvFile(EnvoError):
    def __init__(self):
        super().__init__("Couldn't find any env!\n" 'Forgot to run envo init" first?')


class NormalPrompt(PromptBase):
    msg: str = ""

    @property
    def p_name(self) -> str:
        return f"({self.name})" if self.name else ""

    @property
    def p_msg(self) -> str:
        return f"{{BOLD_RED}}{self.msg}{{RESET}}\n" if self.msg else ""

    def __init__(self) -> None:
        super().__init__()

        self.state_prefix_map = {
            PromptState.LOADING: lambda: f"{self.p_msg}{const.emojis['loading']}{self.p_name}{self.default}",
            PromptState.NORMAL: lambda: f"{self.p_msg}{self.emoji}{self.p_name}{self.default}",
        }


class HeadlessMode:
    @dataclass
    class Links:
        shell: Shell
        envo: "EnvoBase"

    @dataclass
    class Sets:
        stage: str
        restart_nr: int
        msg: str

    @dataclass
    class Callbacks:
        restart: Callback
        on_error: Callback

    env: Env
    reloader_enabled: bool = False
    blocking: bool = True

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        self.se = se
        self.li = li
        self.calls = calls

        self.env_dirs = self._get_env_dirs()

        self.extra_watchers = []

        if not self.env_dirs:
            raise CantFindEnvFile

        self.status = Status(calls=Status.Callbacks(on_ready=Callback(self._on_ready)))

        try:
            sys.path.remove(str(self.env_dirs[0]))
        except ValueError:
            pass
        sys.path.insert(0, str(self.env_dirs[0]))

        self.env = None

        self.li.shell.set_fulll_traceback_enabled(True)

        logger.set_level(logging.Level.INFO)

        logger.debug("Creating Headless Mode")

    def _on_ready(self) -> None:
        self.prompt.state = PromptState.NORMAL
        self.li.shell.set_prompt(self.prompt.as_str())

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

    def unload(self) -> None:
        if self.env:
            self.env._unload()

        self.li.shell.calls.reset()

    def init(self) -> None:
        self.li.shell.set_context({"logger": logger})

        self._create_env()

        self.prompt = NormalPrompt()
        self.prompt.state = PromptState.LOADING
        self.prompt.emoji = self.env.meta.emoji
        self.prompt.name = self.env.get_name()
        self.prompt.msg = self.se.msg

        self.li.shell.set_prompt(str(self.prompt))

        self.li.shell.set_variable("env", self.env)
        self.li.shell.set_variable("environ", os.environ)

        self.env.validate()
        self.env.activate()

        self.env.load()

    def _find_env(self) -> Path:
        # TODO: Test this
        if self.se.stage != "Default":
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

                results = sorted(
                    matches.items(), key=lambda x: x[1].priority, reverse=True
                )
                if results:
                    return results[0][0]

        raise CantFindEnvFile()

    def get_env_file(self) -> Path:
        return self._find_env()

    def _create_env_object(self, file: Path) -> Env:
        def on_reloader_ready():
            self.status.reloader_ready = True

        def on_context_ready():
            self.status.context_ready = True

        env_class = EnvBuilder.build_env_from_file(file)
        env = env_class(
            li=Env.Links(self.li.shell),
            calls=Env.Callbacks(
                restart=self.calls.restart,
                reloader_ready=Callback(on_reloader_ready),
                context_ready=Callback(on_context_ready),
                on_error=self.calls.on_error,
            ),
            se=Env.Sets(
                reloader_enabled=self.reloader_enabled,
                blocking=self.blocking,
                extra_watchers=self.extra_watchers,
            ),
        )
        return env

    def _create_env(self) -> None:
        env_file = self.get_env_file()
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
    blocking: bool = False

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        super(NormalMode, self).__init__(se=se, li=li, calls=calls)
        self.se = se
        self.li = li
        self.calls = calls

        self.li.shell.set_fulll_traceback_enabled(False)

        logger.set_level(logging.Level.ERROR)
        logger.debug("Creating NormalMode")

    def stop(self) -> None:
        self.env._exit()


class EmergencyMode(HeadlessMode):
    @dataclass
    class Links(HeadlessMode.Links):
        pass

    @dataclass
    class Sets(HeadlessMode.Sets):
        pass

    @dataclass
    class Callbacks(HeadlessMode.Callbacks):
        pass

    reloader_enabled: bool = True
    blocking: bool = False

    def __init__(self, se: Sets, li: Links, calls: Callbacks) -> None:
        super().__init__(se=se, li=li, calls=calls)

        self.se = se
        self.li = li
        self.calls = calls

        logger.set_level(logging.Level.ERROR)
        logger.debug("Creating EmergencyMode")
        self.li.shell.set_fulll_traceback_enabled(False)

        self.li.shell.calls.on_exit = Callback(self.stop)

    def get_env_file(self) -> Path:
        return Path(__file__).parent / "emergency_env.py"

    def get_watchers_from_env(self, env: misc.EnvParser) -> List[Inotify]:
        watchers = [
            Inotify(
                Inotify.Sets(
                    root=env.path.parent,
                    include=Env._default_watch_files,
                    exclude=Env._default_ignore_files,
                ),
                calls=Inotify.Callbacks(on_event=Callback(None)),
            )
        ]

        for p in env.parents:
            watchers.extend(self.get_watchers_from_env(p))

        # remove duplicates
        watchers = list({obj.se.root: obj for obj in watchers}.values())
        return watchers

    def _create_env(self) -> None:
        self.extra_watchers = self.get_watchers_from_env(
            misc.EnvParser(super().get_env_file())
        )
        super()._create_env()

        self.env.Meta.root = self.env_dirs[0]

    def stop(self) -> None:
        self.env._exit()


class EnvoBase:
    @dataclass
    class Sets:
        stage: str

    shell: shell.Shell
    mode: Optional[HeadlessMode]

    def __init__(self, se: Sets):
        self.se = se
        logger.set_level(logging.Level.INFO)
        self.mode = None

        self.restart_count = -1

    def init(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError()

    def restart(self) -> None:
        self.init()

    def single_command(self, command: str) -> None:
        raise NotImplementedError()

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

    def on_error(self) -> None:
        pass

    def init(self, *args: Any, **kwargs: Any) -> None:
        self.restart_count += 1
        self.shell.reset()

        self.mode = HeadlessMode(
            se=HeadlessMode.Sets(
                stage=self.se.stage, restart_nr=self.restart_count, msg=""
            ),
            calls=HeadlessMode.Callbacks(
                restart=Callback(self.restart), on_error=Callback(self.on_error)
            ),
            li=HeadlessMode.Links(shell=self.shell, envo=self),
        )
        self.mode.init()

    def single_command(self, command: str) -> None:
        self.shell = shell.shells["headless"].create(Shell.Callbacs())
        self.init()

        try:
            self.shell.default(command)
        except SystemExit as e:
            sys.exit(e.code)
        else:
            sys.exit(self.shell.history[-1].rtn)
        finally:
            self.mode.unload()

    def dry_run(self) -> None:
        self.shell = shell.shells["headless"].create(Shell.Callbacs())
        self.init()
        content = "\n".join(
            [f'export {k}="{v}"' for k, v in self.mode.env.get_env_vars().items()]
        )
        print(content)

    def save(self) -> None:
        self.shell = shell.shells["headless"].create(Shell.Callbacs())
        self.init()
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
    mode: HeadlessMode

    def __init__(self, se: Sets) -> None:
        super().__init__(se)

        self.quit: bool = False
        self.environ_before = os.environ.copy()  # type: ignore
        logger.set_level(logging.Level.ERROR)

    def init(self, *args: Any, **kwargs: Any) -> None:
        self.restart_count += 1
        try:
            self.shell.reset()

            if self.mode:
                self.mode.unload()

            self.mode = NormalMode(
                se=NormalMode.Sets(
                    stage=self.se.stage, restart_nr=self.restart_count, msg=""
                ),
                li=NormalMode.Links(shell=self.shell, envo=self),
                calls=NormalMode.Callbacks(
                    restart=Callback(self.restart), on_error=Callback(self.on_error)
                ),
            )
            self.mode.init()

        except BaseException as exc:
            self.on_error(exc)

    def on_error(self, exc: BaseException) -> None:
        msg = misc.get_envo_relevant_traceback(exc)
        msg = "".join(msg)
        msg = msg.rstrip()

        logger.error(msg)

        if self.mode:
            self.mode.unload()

        self.mode = EmergencyMode(
            se=EmergencyMode.Sets(
                stage=self.se.stage, restart_nr=self.restart_count, msg=msg
            ),
            li=EmergencyMode.Links(shell=self.shell, envo=self),
            calls=EmergencyMode.Callbacks(
                restart=Callback(self.restart), on_error=Callback(None)
            ),
        )

        self.mode.init()

    def spawn_shell(self, type: Literal["fancy", "simple"]) -> None:
        """
        :param type: shell type
        """

        def on_ready():
            pass

        self.shell = shell.shells[type].create(
            calls=Shell.Callbacs(on_ready=Callback(on_ready))
        )
        self.init()

        self.mode.env.on_shell_create()

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
        class_name = (
            f"{misc.dir_name_to_class_name(package_name)}{stage.capitalize()}Env"
        )

        context = {
            "class_name": class_name,
            "name": env_dir.name,
            "stage": stage,
            "emoji": const.STAGES.get_stage_name_to_emoji().get(stage, "🙂"),
            "parents": f'"{parent}"' if parent else "",
        }

        templ_file = Path("env.py.templ")
        misc.render_py_file(
            templates_dir / templ_file, output=output_file, context=context
        )

    def create(self) -> None:
        if not self.se.stage:
            self.se.stage = "comm"

        self._create_from_templ(
            self.se.stage, parent="env_comm.py" if self.se.stage != "comm" else ""
        )

        if self.se.stage != "comm" and not Path("env_comm.py").exists():
            self._create_from_templ("comm")

        print(f"Created {self.se.stage} environment 🍰!")


def _main() -> None:
    logger.debug(f"Starting")

    sys.argv[0] = "/home/kwazar/Code/opensource/envo/.venv/bin/xonsh"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage", type=str, default="Default", help="Stage to activate.", nargs="?"
    )
    parser.add_argument("--init", type=str, default=None, nargs="?")
    parser.add_argument("--dry-run", default=False, action="store_true")
    parser.add_argument("--version", default=False, action="store_true")
    parser.add_argument("--save", default=False, action="store_true")
    parser.add_argument("--shell", default="fancy")
    parser.add_argument("--run", default=None, nargs="?")
    parser.add_argument("-c", "--command", default=None)

    argv = sys.argv[1:]

    if argv and argv[0] == "run":
        argv[0] = "--run"

    if argv and argv[0] == "init":
        argv[0] = "--init"

        if len(argv) == 1:
            argv.append("comm")

    if not argv:
        argv = ["Default"]

    args = parser.parse_args(argv)
    sys.argv = sys.argv[:1]

    try:
        if args.version:
            from envo.__version__ import __version__

            print(__version__)
            return

        if args.command or args.run:
            command = args.command or args.run

            envo.e2e.envo = env_headless = EnvoHeadless(
                EnvoHeadless.Sets(stage=args.stage)
            )
            env_headless.single_command(command)
        elif args.init:
            envo_creator = EnvoCreator(EnvoCreator.Sets(stage=args.init))
            envo_creator.create()
        elif args.dry_run:
            envo.e2e.envo = env_headless = EnvoHeadless(
                EnvoHeadless.Sets(stage=args.stage)
            )
            env_headless.dry_run()
        elif args.save:
            envo.e2e.envo = env_headless = EnvoHeadless(
                EnvoHeadless.Sets(stage=args.stage)
            )
            env_headless.save()
        else:
            envo.e2e.envo = e = Envo(Envo.Sets(stage=args.stage))
            e.handle_command(args)
    except EnvoError as e:
        logger.error(str(e), print_msg=True)
        sys.exit(1)


if __name__ == "__main__":
    _main()
