#!/usr/bin/env python3
import hashlib
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type

import envo.e2e
from envo import Env, const, logger, logging, misc, shell
from envo.env import EnvBuilder
from envo.misc import Callback, EnvoError, FilesWatcher
from envo.shell import FancyShell, PromptBase, PromptState, Shell
from envo.status import Status

package_root = Path(os.path.realpath(__file__)).parent
templates_dir = package_root / "templates"


__all__ = ["_main"]

DEFAULT_STAGE = "Default"


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

    @dataclass
    class Sets:
        stage: str
        restart_nr: int
        msg: str
        env_path: Path

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

        self.extra_watchers = []

        self.status = Status(
            calls=Status.Callbacks(
                on_ready=Callback(self._on_ready),
                on_not_ready=Callback(self._on_not_ready),
            )
        )

        self.env = None

        self.li.shell.set_fulll_traceback_enabled(True)

        logger.set_level(logging.Level.INFO)

        logger.debug("Creating Headless Mode")

    def _on_ready(self) -> None:
        self.prompt.state = PromptState.NORMAL
        self.li.shell.set_prompt(self.prompt.as_str())

    def _on_not_ready(self) -> None:
        self.prompt.state = PromptState.LOADING
        self.li.shell.set_prompt(self.prompt.as_str())

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

    def get_env_file(self) -> Path:
        return self.se.env_path

    def _create_env_object(self, file: Path) -> Env:
        env_class = EnvBuilder.build_shell_env_from_file(file)
        env = env_class(
            li=Env._Links(self.li.shell, status=self.status),
            calls=Env._Callbacks(
                restart=self.calls.restart,
                on_error=self.calls.on_error,
            ),
            se=Env._Sets(
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

    def get_watchers_from_env(self, env: misc.EnvParser) -> List[FilesWatcher]:
        watchers = [
            FilesWatcher(
                FilesWatcher.Sets(
                    root=env.path.parent,
                    include=["env_*.py"],
                    exclude=[],
                ),
                calls=FilesWatcher.Callbacks(on_event=Callback(None)),
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

        self.env.Meta.root = self.se.env_path.parent

    def stop(self) -> None:
        self.env._exit()


class EnvoBase:
    @dataclass
    class Sets:
        stage: str

    shell: shell.Shell
    mode: Optional[HeadlessMode]
    env_dirs: List[Path]

    def __init__(self, se: Sets):
        self.se = se
        logger.set_level(logging.Level.INFO)
        self.mode = None

        self.env_dirs = self._get_env_dirs()

        self.restart_count = -1

    def _get_env_dirs(self) -> List[Path]:
        ret = []
        path = Path(".").absolute()
        while True:
            if path.parent == path:
                break

            for p in path.glob("env_*.py"):
                if p.parent not in ret:
                    ret.append(p.parent)

            path = path.parent

        return ret

    def find_env(self) -> Path:
        # TODO: Test this
        if self.se.stage != DEFAULT_STAGE:
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

    @property
    def data_dir_name(self) -> str:
        hash_object = hashlib.md5(str(self.find_env()).encode("utf-8"))
        ret = hash_object.hexdigest()
        return ret

    def init(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError()

    def restart(self) -> None:
        self.init()

    def single_command(self, command: str) -> None:
        raise NotImplementedError()

    def dry_run(self) -> None:
        raise NotImplementedError()

    def dump(self) -> None:
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

        if not self.env_dirs:
            raise CantFindEnvFile

        self.restart_count = -1

    def on_error(self) -> None:
        pass

    def init(self, *args: Any, **kwargs: Any) -> None:
        self.restart_count += 1
        self.shell.reset()

        self.mode = HeadlessMode(
            se=HeadlessMode.Sets(
                stage=self.se.stage,
                restart_nr=self.restart_count,
                msg="",
                env_path=self.find_env(),
            ),
            calls=HeadlessMode.Callbacks(
                restart=Callback(self.restart), on_error=Callback(self.on_error)
            ),
            li=HeadlessMode.Links(shell=self.shell),
        )
        self.mode.init()

    def single_command(self, command: str) -> None:
        self.shell = Shell.create(Shell.Callbacks(), data_dir_name=self.data_dir_name)
        self.init()

        try:
            self.shell.default(command)
        except SystemExit as e:
            sys.exit(e.code)
        else:
            sys.exit(self.shell.last_return_code)
        finally:
            self.mode.unload()

    def dry_run(self) -> None:
        self.shell = Shell.create(Shell.Callbacks(), data_dir_name=self.data_dir_name)
        self.init()
        content = "\n".join(
            [f'export {k}="{v}"' for k, v in self.mode.env.e.get_env_vars().items()]
        )
        print(content)

    def dump(self) -> None:
        self.shell = Shell.create(Shell.Callbacks(), data_dir_name=self.data_dir_name)
        self.init()
        path = self.mode.env.dump_dot_env()
        logger.info(f"Saved envs to {str(path)} 💾", print_msg=True)


class Envo(EnvoBase):
    @dataclass
    class Sets(EnvoBase.Sets):
        pass

    environ_before = Dict[str, str]
    inotify: FilesWatcher
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
                    stage=self.se.stage,
                    restart_nr=self.restart_count,
                    msg="",
                    env_path=self.find_env(),
                ),
                li=NormalMode.Links(shell=self.shell),
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
                stage=self.se.stage,
                restart_nr=self.restart_count,
                msg=msg,
                env_path=self.find_env(),
            ),
            li=EmergencyMode.Links(shell=self.shell),
            calls=EmergencyMode.Callbacks(
                restart=Callback(self.restart), on_error=Callback(None)
            ),
        )

        self.mode.init()

    def spawn_shell(self) -> None:
        """
        :param type: shell type
        """

        def on_ready():
            pass

        self.shell = FancyShell.create(
            calls=FancyShell.Callbacks(on_ready=Callback(on_ready)),
            data_dir_name=self.data_dir_name,
        )
        self.init()

        self.mode.env.on_shell_create()

        self.shell.start()
        self.mode.unload()


class EnvoCreator:
    @dataclass
    class Sets:
        stage: str

    def __init__(self, se: Sets) -> None:
        logger.debug("Starting EnvoCreator")
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


@dataclass
class BaseOption:
    stage: str
    flesh: str

    keywords: ClassVar[str] = NotImplemented

    def run(self) -> None:
        raise NotImplementedError()


@dataclass
class Command(BaseOption):
    def run(self) -> None:
        envo.e2e.envo = env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=self.stage))
        env_headless.single_command(self.flesh)


@dataclass
class DryRun(BaseOption):
    def run(self) -> None:
        envo.e2e.envo = env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=self.stage))
        env_headless.dry_run()


@dataclass
class Dump(BaseOption):
    def run(self) -> None:
        envo.e2e.envo = env_headless = EnvoHeadless(EnvoHeadless.Sets(stage=self.stage))
        env_headless.dump()


@dataclass
class Version(BaseOption):
    def run(self) -> None:
        from envo.__version__ import __version__

        print(__version__)


@dataclass
class Init(BaseOption):
    def run(self) -> None:
        stage = "comm" if self.stage == DEFAULT_STAGE else self.stage
        envo_creator = EnvoCreator(EnvoCreator.Sets(stage=stage))
        envo_creator.create()


@dataclass
class Start(BaseOption):
    def run(self) -> None:
        envo.e2e.envo = e = Envo(Envo.Sets(stage=self.stage))
        e.spawn_shell()


option_name_to_option: Dict[str, Type[BaseOption]] = {
    "-c": Command,
    "run": Command,
    "dry-run": DryRun,
    "dump": Dump,
    "": Start,
    "init": Init,
    "version": Version,
}


def _main() -> None:
    logger.debug("Starting")

    argv = sys.argv[1:]
    keywords = ["init", "dry-run", "version", "dump", "run"]

    stage = DEFAULT_STAGE
    if argv and argv[0] not in keywords:
        stage = argv[0]
        option_name = argv[1] if len(argv) >= 2 else ""
        flesh = " ".join(argv[2:])
    else:
        option_name = argv[0] if len(argv) >= 1 else ""
        flesh = " ".join(argv[1:])

    option = option_name_to_option[option_name](stage, flesh=flesh)

    try:
        option.run()
    except EnvoError as e:
        logger.error(str(e), print_msg=True)
        if envo.e2e.enabled:
            envo.e2e.on_exit()
        sys.exit(1)
    finally:
        if envo.e2e.enabled:
            envo.e2e.on_exit()


if __name__ == "__main__":
    _main()
