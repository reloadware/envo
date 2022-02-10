import builtins
import inspect
import os
import re
import sys

# Python >= 3.8
import typing
from abc import ABC, abstractmethod
from collections import OrderedDict
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import dataclass, field, is_dataclass
from functools import wraps
from itertools import product
from pathlib import Path
from threading import Lock, Thread
from time import sleep
from types import FrameType, MethodType, ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import envium
from envium import computed_env_var, env_var
from rhei import Stopwatch
from watchdog import events
from watchdog.events import FileModifiedEvent

from envo import logger, misc
from envo.logs import Logger
from envo.misc import (
    Callback,
    EnvoError,
    FilesWatcher,
    event_dispatcher,
    import_env_from_file,
    import_from_file,
)
from envo.status import Status

__all__ = [
    "Env",
    "command",
    "shell_context",
    "precmd",
    "postcmd",
    "onstdout",
    "onstderr",
    "oncreate",
    "onload",
    "onunload",
    "ondestroy",
    "boot_code",
    "Namespace",
    "Source",
]

T = TypeVar("T")

if TYPE_CHECKING:
    from envo import Plugin
    from envo.scripts import Status
    from envo.shell import FancyShell, Shell


class MagicFunctionData:
    type: str
    namespace: str
    expected_fun_args: List[str]


# magic function data
mfd_field = "mfd"


@dataclass
class MagicFunction:
    type: str
    namespace: str = ""
    expected_fun_args = None

    def __new__(cls, *args, **kwargs) -> Callable:
        if callable(args[0]):
            fun = cast(Callable[..., Any], args[0])
            args = args[1:]

            @wraps(fun)
            def wrapped(*fun_args, **fun_kwargs):
                return cls._call(fun, fun_args, fun_kwargs, args, kwargs)

            cls._inject_data(wrapped, *args, **kwargs)
            return wrapped
        else:

            def decor(fun):
                @wraps(fun)
                def wrapped(*fun_args, **fun_kwargs):
                    return cls._call(fun, fun_args, fun_kwargs, args, kwargs)

                cls._inject_data(wrapped, *args, **kwargs)
                return wrapped

            return decor

    @classmethod
    def _call(cls, fun: Callable, fun_args, fun_kwargs, args, kwargs):
        if not fun_args or not isinstance(fun_args[0], Env):
            if fun_args and fun_args[0] == "__env__":
                fun_args = (builtins.__env__, *fun_args[1:])
            else:
                fun_args = (builtins.__env__, *fun_args)
        try:
            with cls._context(fun_args[0], *args, **kwargs):
                ret = fun(*fun_args, **fun_kwargs)
            return ret
        except BaseException as e:
            sys.stderr.write("\n")
            sys.stderr.flush()
            logger.traceback()
            raise

    @classmethod
    def _inject_data(cls, wrapped: Callable, *args, **kwargs) -> None:
        wrapped.mfd = MagicFunctionData()
        wrapped.mfd.type = cls.type
        wrapped.mfd.namespace = cls.namespace
        wrapped.mfd.expected_fun_args = cls.expected_fun_args

    @contextmanager
    def _context(self, *args, **kwargs) -> None:
        yield


@dataclass
class command(MagicFunction):
    type = "command"

    def __new__(cls, in_root: Optional[bool] = True, cd_back: Optional[bool] = True) -> Callable:
        ret = super().__new__(cls, in_root, cd_back)
        return ret

    @classmethod
    @contextmanager
    def _context(cls, env: "Env", in_root: Optional[bool] = True, cd_back: Optional[bool] = True) -> None:
        cwd = Path(".").absolute()

        if in_root:
            os.chdir(str(env.meta.root))

        yield

        if cd_back:
            os.chdir(str(cwd))


class boot_code(MagicFunction):  # noqa: N801
    type: str = "boot_code"


class Event(MagicFunction):  # noqa: N801
    pass


class onload(Event):  # noqa: N801
    type: str = "onload"


class oncreate(Event):  # noqa: N801
    type: str = "oncreate"


class ondestroy(Event):  # noqa: N801
    type: str = "ondestroy"


class onunload(Event):  # noqa: N801
    type: str = "onunload"


class cmd_hook(MagicFunction):  # noqa: N801
    def __new__(cls, cmd_regex: str = ".*") -> Callable:
        ret = super().__new__(cls, cmd_regex)
        return ret

    @classmethod
    def _inject_data(cls, wrapped: Callable, cmd_regex: str = ".*") -> None:
        super()._inject_data(wrapped, cmd_regex)
        wrapped.mfd.cmd_regex = cmd_regex


class precmd(cmd_hook):  # noqa: N801
    type: str = "precmd"
    expected_fun_args = ["command", "out"]


class onstdout(cmd_hook):  # noqa: N801
    type: str = "onstdout"
    expected_fun_args = ["command", "out"]


class onstderr(cmd_hook):  # noqa: N801
    type: str = "onstderr"
    expected_fun_args = ["command", "out"]


class postcmd(cmd_hook):  # noqa: N801
    type: str = "postcmd"
    expected_fun_args = ["command", "stdout", "stderr"]


class shell_context(MagicFunction):  # noqa: N801
    type: str = "shell_context"

    def __init__(self) -> None:
        super().__init__()


PathLike = Union[Path, str]

magic_functions = {
    "command": command,
    "shell_context": shell_context,
    "boot_code": boot_code,
    "onload": onload,
    "onunload": onunload,
    "oncreate": oncreate,
    "ondestroy": ondestroy,
    "precmd": precmd,
    "onstdout": onstdout,
    "onstderr": onstderr,
}


class Namespace:
    command = command
    shell_context = shell_context
    boot_code = boot_code
    onload = onload
    onunload = onunload
    oncreate = oncreate
    ondestroy = ondestroy
    precmd = precmd
    onstdout = onstdout
    onstderr = onstderr

    def __init__(self, name: str) -> None:
        self._name = name

        for n, f in magic_functions.items():
            namespaced_magic_fun = type(f"namespaced_{n}", (f,), {})
            namespaced_magic_fun.namespace = self._name
            setattr(self, n, namespaced_magic_fun)


@dataclass
class Source:
    root: Path
    watch_files: List[str] = field(default_factory=list)
    ignore_files: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()


class EnvReloader:
    @dataclass
    class Callbacks:
        on_env_edit: Callback

    @dataclass
    class Sets:
        extra_watchers: List[FilesWatcher]
        watch_files: List[str]
        ignore_files: List[str]

    @dataclass
    class Links:
        shell_env: "ShellEnv"
        status: "Status"
        logger: "Logger"

    env_watchers: List[FilesWatcher]
    _modules_before: Dict[str, Any]

    def __init__(self, li: Links, se: Sets, calls: Callbacks) -> None:
        self.li = li
        self.se = se
        self.calls = calls

        self.env_watchers = []

        self._collect_env_watchers()

    def _unload_modules(self) -> None:
        to_pop = set(sys.modules.keys()) - set(self._modules_before.keys())
        for p in to_pop:
            sys.modules.pop(p)

    def _collect_env_watchers(self) -> None:
        # inject callbacks into existing watchers
        for w in self.se.extra_watchers:
            w.calls = FilesWatcher.Callbacks(on_event=self.calls.on_env_edit)
            self.env_watchers.append(w)

        for p in self.li.shell_env.env.get_user_envs():
            watcher = FilesWatcher(
                FilesWatcher.Sets(
                    root=p.Meta.root,
                    include=self.se.watch_files + ["env_*.py"],
                    exclude=self.se.ignore_files + [r"**/.*", r"**/*~", r"**/__pycache__"],
                    name=p.__name__,
                ),
                calls=FilesWatcher.Callbacks(on_event=self.calls.on_env_edit),
            )
            self.env_watchers.append(watcher)

    def start(self) -> None:
        self.li.status.reloader_ready = True

    def stop(self):
        for w in self.env_watchers:
            w.stop()


class BaseEnv(ABC):
    class Meta:
        pass

    @abstractmethod
    def init(self) -> None:
        pass

    @abstractmethod
    def post_init(self) -> None:
        pass


class Env(BaseEnv):
    class Meta:
        """
        Environment metadata.
        """

        root: Path
        name: Optional[str] = None
        version: str = "0.1.0"
        parents: List[str] = []
        plugins: List["Plugin"] = []
        sources: List[Source] = []
        emoji: str = ""
        stage: str = "comm"
        watch_files: List[str] = []
        ignore_files: List[str] = []
        verbose_run: bool = True
        load_env_vars: bool = False

    class Environ(envium.Environ):
        pythonpath: Optional[List[PathLike]] = env_var(raw=True, default_factory=list)
        path: Optional[List[PathLike]] = env_var(raw=True, default_factory=list)
        root: Optional[Path] = env_var()
        stage: Optional[str] = env_var()
        envo_stage: Optional[str] = env_var(raw=True)
        envo_name: Optional[str] = env_var(raw=True)

    class Ctx(envium.Ctx):
        pass

    class Secrets(envium.Secrets):
        pass

    ctx: Ctx
    secrets: Secrets
    meta: Meta

    _environ_before: Optional[Dict[str, str]]

    env_id_to_secrets: ClassVar[Dict[str, Secrets]] = {}

    _shell: "Shell"

    def __init__(self):
        self._environ_before = os.environ.copy()
        self.meta = self.Meta()

        self.e = self.Environ(name=self.meta.name, load=self.meta.load_env_vars)
        self.e.envo_name = self.meta.name

        self.e.root = self.meta.root
        self.e.stage = self.meta.stage
        self.e.envo_stage = self.meta.stage

        self.e.path = self._path_str_to_list(os.environ["PATH"])

        if "PYTHONPATH" not in os.environ:
            self.e.pythonpath = []
        else:
            self.e.pythonpath = self._path_str_to_list(os.environ["PYTHONPATH"])

        self.ctx = self.Ctx(self.meta.name)

        secrets = Env.env_id_to_secrets.get(self.id, self.Secrets(self.meta.name))
        self.secrets = Env.env_id_to_secrets[self.id] = secrets

        self.init()

        self.validate()
        self.activate()

        for c in reversed(self.__class__.__mro__):
            if not issubclass(c, BaseEnv):
                continue

            getattr(c, "post_init")(self)

    def _get_path_delimiter(self) -> str:
        if misc.is_linux() or misc.is_darwin():
            return ":"
        elif misc.is_windows():
            return ";"
        else:
            raise NotImplementedError

    def _path_str_to_list(self, path: str) -> List[Path]:
        paths_str = path.split(self._get_path_delimiter())
        ret = [Path(s) for s in paths_str]
        return ret

    @classmethod
    def instantiate(cls, stage: Optional[str] = None) -> "Env":
        if not stage:
            stage = os.environ.get("ENVO_STAGE", "comm")

        env_class = import_from_file(cls.Meta.root / f"env_{stage}.py").ThisEnv
        return env_class()

    def init(self) -> None:
        super().init()
        pass

    def post_init(self) -> None:
        pass

    @property
    def id(self) -> str:
        return f"{self.__class__.__module__}:{self.__class__.__name__}"

    def validate(self) -> None:
        """
        Validate env
        """

        msgs = []
        if self.ctx.errors:
            msgs.append("Context errors:\n" + f"\n".join([str(e) for e in self.ctx.errors]))

        if self.e.errors:
            msgs.append("Environ errors:\n" + f"\n".join([str(e) for e in self.e.errors]))

        if self.secrets.errors:
            msgs.append("Secrets errors:\n" + f"\n".join([str(e) for e in self.e.errors]))

        msg = "\n".join(msgs)

        if msg:
            raise EnvoError(msg)

    def get_env_vars(self) -> Dict[str, str]:
        ret = self.e.get_env_vars()
        return ret

    def get_parts(self) -> List[Type["Env"]]:
        ret = []
        for c in self.__class__.__mro__:
            if not issubclass(c, BaseEnv) or c is BaseEnv or c is Env:
                continue
            ret.append(c)

        return ret

    def get_user_envs(self) -> List[Type["Env"]]:
        ret = []
        for c in self.__class__.__mro__:
            if not issubclass(c, Env) or c is Env:
                continue
            ret.append(c)

        return ret

    def get_env(self, directory: Union[Path, str], stage: Optional[str] = None) -> "Env":
        stage = stage or self.meta.stage
        directory = Path(directory)
        env_file = directory / f"env_{stage}.py"

        if not env_file.exists():
            logger.traceback()
            raise EnvoError(f"{env_file} does not exit")

        env = import_env_from_file(env_file).ThisEnv()
        return env

    @classmethod
    def get_env_path(cls) -> Path:
        return cls.Meta.root / f"env_{cls.Meta.stage}.py"

    def dump_dot_env(self) -> Path:
        """
        Dump .env file for the current environment.

        File name follows env_{env_name} format.
        """
        path = Path(f".env_{self.meta.stage}")
        content = "\n".join([f'{key}="{value}"' for key, value in self.e.get_env_vars().items()])
        path.write_text(content, "utf-8")
        return path

    def activate(self) -> None:
        if not self._environ_before:
            self._environ_before = os.environ.copy()

        os.environ.update(**self.get_env_vars())

    def deactivate(self) -> None:
        if self._environ_before:
            os.environ = self._environ_before.copy()


class ShellEnv:
    """
    Defines environment.
    """

    @dataclass
    class _Callbacks:
        restart: Callback
        on_error: Callable

    @dataclass
    class _Links:
        shell: Optional["Shell"]
        env: Env
        status: "Status"

    @dataclass
    class _Sets:
        extra_watchers: List[FilesWatcher]
        reloader_enabled: bool = True
        blocking: bool = False

    reloader: EnvReloader
    _sys_modules_snapshot: Dict[str, ModuleType] = OrderedDict()
    magic_functions: Dict[str, Any]
    env: Env

    def __init__(self, calls: _Callbacks, se: _Sets, li: _Links) -> None:
        self._calls = calls
        self._se = se
        self._li = li
        self.env = self._li.env

        self.env._shell = self._li.shell

        self.magic_functions = {
            "shell_context": {},
            "precmd": {},
            "onstdout": {},
            "onstderr": {},
            "postcmd": {},
            "onload": {},
            "oncreate": {},
            "ondestroy": {},
            "onunload": {},
            "boot_code": {},
            "command": {},
        }

        if self.env.meta.verbose_run:
            os.environ["ENVO_VERBOSE_RUN"] = "True"
        elif os.environ.get("ENVO_VERBOSE_RUN"):
            os.environ.pop("ENVO_VERBOSE_RUN")

        self._exiting = False
        self._executing_cmd = False

        self._shell_environ_before = None

        self._reload_lock = Lock()

        self.logger: Logger = logger.create_child("envo", descriptor=self.env.meta.name)

        self._environ_before = None
        self._shell_environ_before = None
        self._collect_magic_functions()

        self.logger.debug("Starting env", metadata={"root": self.env.meta.root, "stage": self.env.meta.stage})

        self._li.shell.calls.pre_cmd = Callback(self._on_precmd)
        self._li.shell.calls.on_stdout = Callback(self._on_stdout)
        self._li.shell.calls.on_stderr = Callback(self._on_stderr)
        self._li.shell.calls.post_cmd = Callback(self._on_postcmd)
        self._li.shell.calls.on_exit = Callback(self._on_destroy)

        self.reloader = None

        if "" in sys.path:
            sys.path.remove("")

        if self._se.reloader_enabled:
            self.reloader = EnvReloader(
                li=EnvReloader.Links(shell_env=self, status=self._li.status, logger=self.logger),
                se=EnvReloader.Sets(
                    extra_watchers=se.extra_watchers,
                    watch_files=self.env.meta.watch_files,
                    ignore_files=self.env.meta.ignore_files,
                ),
                calls=EnvReloader.Callbacks(
                    on_env_edit=Callback(self._on_env_edit),
                ),
            )

        if not self._sys_modules_snapshot:
            self._sys_modules_snapshot = OrderedDict(sys.modules.copy())

        builtins.__env__ = self.env

    def _on_reload_start(self) -> None:
        self.logger.debug("Running reload, trying partial first")
        self._li.status.source_ready = False

    def _on_reload_error(self, error: Exception) -> None:
        logger.traceback()

        self.redraw_prompt()
        self._li.status.source_ready = True

    def _start_reloaders(self) -> None:
        if not self._se.reloader_enabled:
            return

        self.reloader.start()

    def _stop_reloaders(self) -> None:
        if not self._se.reloader_enabled:
            return

        self.reloader.stop()

    def get_name(self) -> str:
        """
        Return env name
        """
        return self.env.meta.name

    def redraw_prompt(self) -> None:
        self._li.shell.redraw()

    def load(self) -> None:
        """
        Called after creation and reload.
        :return:
        """

        def thread(self: "ShellEnv") -> None:
            logger.debug("Starting onload thread")

            sw = Stopwatch()
            sw.start()
            functions = self.magic_functions["onload"].values()

            self._start_reloaders()

            try:
                for h in functions:
                    h()
                self._run_boot_codes()
            except BaseException as e:
                # TODO: pass env code to exception to get relevant traceback?
                self._li.status.shell_context_ready = True
                self._calls.on_error(e)
                self._exit()
                return

            # declare commands
            for name, c in self.magic_functions["command"].items():
                self._li.shell.set_variable(name, c)

            # set context
            self._li.shell.set_context(self._get_shell_context())
            while sw.value <= 0.5:
                sleep(0.1)

            logger.debug("Finished load context thread")
            self._li.status.shell_context_ready = True

        if not self._se.blocking:
            Thread(target=thread, args=(self,)).start()
        else:
            thread(self)

    def _collect_magic_functions(self) -> None:
        """
        Go through fields and transform decorated functions to commands.
        """

        def hasattr_static(obj: Any, field: str) -> bool:
            try:
                inspect.getattr_static(obj, field)
            except AttributeError:
                return False
            else:
                return True

        for c in reversed(self.env.__class__.__mro__):
            for f in dir(c):
                if hasattr_static(self.__class__, f) and inspect.isdatadescriptor(
                    inspect.getattr_static(self.__class__, f)
                ):
                    continue

                attr = inspect.getattr_static(c, f)

                if hasattr(attr, mfd_field):
                    namespaced_name = f"{attr.mfd.namespace}.{f}" if attr.mfd.namespace else f
                    self.magic_functions[attr.mfd.type][namespaced_name] = attr

    def _get_shell_context(self) -> Dict[str, Any]:
        shell_context = {}
        for c in self.magic_functions["shell_context"].values():
            try:
                cont = c()
            except Exception:
                continue
            for k, v in cont.items():
                namespaced_name = f"{c.mfd.namespace}.{k}" if c.mfd.namespace else k
                shell_context[namespaced_name] = v

        return shell_context

    def on_shell_create(self) -> None:
        """
        Called only after creation.
        :return:
        """
        functions = self.magic_functions["oncreate"].values()
        for h in functions:
            h()

    def _on_destroy(self) -> None:
        functions = self.magic_functions["ondestroy"]
        for h in functions.values():
            h()

        self._exit()

    def _on_env_edit(self, event: FileModifiedEvent) -> None:
        if not self._li.status.ready:
            return

        subscribe_events = [
            events.EVENT_TYPE_MOVED,
            events.EVENT_TYPE_MODIFIED,
            events.EVENT_TYPE_CREATED,
            events.EVENT_TYPE_DELETED,
        ]

        if any([s in event.event_type for s in subscribe_events]):
            self.request_reload(metadata={"event": event.event_type, "path": event.src_path})

    def request_reload(self, exc: Optional[Exception] = None, metadata: Optional[Dict] = None) -> None:
        event_dispatcher.flush()

        if self._exiting:
            return

        self._exiting = True

        if not metadata:
            metadata = {}

        while self._executing_cmd:
            sleep(0.2)

        self._stop_reloaders()

        self.logger.debug(
            "Reloading",
            metadata={"type": "reload", **metadata},
        )

        if exc:
            self._calls.on_error(exc)
        else:
            self._calls.restart()

    def _exit(self) -> None:
        self.logger.debug("Exiting env")
        self._stop_reloaders()

    def activate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if not self._shell_environ_before:
            self._shell_environ_before = dict(self._li.shell.environ.items())
        self._li.shell.environ.update(**self.env.get_env_vars())

    def _deactivate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if self._shell_environ_before:
            if self._li.shell:
                tmp_environ = copy(self._li.shell.environ)
                for i, v in tmp_environ.items():
                    self._li.shell.environ.pop(i)
                for k, v in self._shell_environ_before.items():
                    if v is None:
                        continue
                    self._li.shell.environ[k] = v

        self.env.deactivate()

    def _is_python_fire_cmd(self, cmd: str) -> bool:
        # validate if it's a correct format
        if "(" in cmd and ")" in cmd:
            return False

        if not cmd:
            return False

        command_name = cmd.split()[0]
        cmd_fun = self.magic_functions["command"].get(command_name, None)
        if not cmd_fun:
            return False

        return True

    def _pre_cmd(self, command: str) -> Optional[str]:
        self._executing_cmd = True

        if self._is_python_fire_cmd(command):
            fun = command.split()[0]
            command = command.replace('"', '\\"')
            return f'__envo__execute_with_fire__({fun}, "{command}")'

        return command

    def _post_cmd(self, command: str, stderr: str, stdout: str) -> None:
        self._executing_cmd = False

    @command
    def source_reload(self) -> None:
        to_remove = list(sys.modules.keys() - self._sys_modules_snapshot.keys())

        for n in reversed(to_remove):
            m = sys.modules[n]
            if not hasattr(m, "__file__"):
                continue

            sys.modules.pop(n)

        for n in to_remove:
            __import__(n)

        self.logger.debug(f"Full reload")

    def _run_boot_codes(self) -> None:
        self._li.status.source_ready = False
        boot_codes_f = self.magic_functions["boot_code"]

        codes = []

        for f in boot_codes_f.values():
            codes.extend(f(self.env))

        for c in codes:
            self._li.shell.run_code(c)

        self._li.status.source_ready = True

    def _on_precmd(self, command: str) -> Optional[str]:
        functions = self.magic_functions["precmd"]
        for f in functions.values():
            if re.match(f.mfd.cmd_regex, command):
                ret = f(command)  # type: ignore
                command = ret

        command = self._pre_cmd(command)
        return command

    def _on_stdout(self, command: str, out: bytes) -> str:
        functions = self.magic_functions["onstdout"]
        for f in functions.values():
            if re.match(f.mfd.cmd_regex, command):
                ret = f(command, out)  # type: ignore
                if ret:
                    out = ret
        return out

    def _on_stderr(self, command: str, out: bytes) -> str:
        functions = self.magic_functions["onstderr"]
        for f in functions.values():
            if re.match(f.mfd.cmd_regex, command):
                ret = f(command, out)  # type: ignore
                if ret:
                    out = ret
        return out

    def _on_postcmd(self, command: str, stdout: str, stderr: str) -> None:
        self._post_cmd(command, stdout, stderr)
        functions = self.magic_functions["postcmd"]
        for f in functions.values():
            if re.match(f.mfd.cmd_regex, command):
                f(command, stdout, stderr)  # type: ignore

    def _unload(self) -> None:
        self._deactivate()
        functions = self.magic_functions["onunload"]
        for f in functions.values():
            f()
        self._li.shell.calls.reset()
