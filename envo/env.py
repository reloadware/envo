import inspect
import os
import re
import sys

# Python >= 3.8
import typing
from abc import ABC, abstractmethod
from collections import OrderedDict
from copy import copy, deepcopy
from dataclasses import dataclass, field, is_dataclass
from pathlib import Path
from threading import Lock, Thread
from time import sleep
from types import MethodType, ModuleType
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
)

import envium
from envium import computed_env_var, env_var
from rhei import Stopwatch
from watchdog import events
from watchdog.events import FileModifiedEvent

from envo import logger
from envo.logs import Logger
from envo.misc import Callback, EnvoError, FilesWatcher, import_env_from_file, import_from_file
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
    "on_partial_reload",
    "onunload",
    "ondestroy",
    "boot_code",
    "Namespace",
    "Source",
]

T = TypeVar("T")

if TYPE_CHECKING:
    from envo import Plugin, misc
    from envo.scripts import Status
    from envo.shell import FancyShell, Shell


@dataclass
class MagicFunction:
    class UnexpectedArgs(Exception):
        pass

    class MissingArgs(Exception):
        pass

    name: str
    type: str
    func: Callable
    kwargs: Dict[str, Any]
    expected_fun_args: List[str]
    namespace: str = ""
    env: Optional["Env"] = field(init=False, default=None)

    def __post_init__(self) -> None:
        search = re.search(r"def ((.|\s)*?):\n", inspect.getsource(self.func))
        if not search:
            return
        decl = search.group(1)
        decl = re.sub(r"self,?\s?", "", decl)
        self.decl = decl

        self._validate_fun_args()

        for k, v in self.kwargs.items():
            setattr(self, k, v)

    def call(self, *args, **kwargs) -> str:
        ret = self.func(*args, **kwargs)
        return ret

    def __call__(self, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
        logger.debug(f'Running magic function (name="{self.name}", type={self.type})')
        if args:
            args = (self.env, *args)  # type: ignore
        else:
            args = (self.env,)  # type: ignore

        try:
            return self.call(*args, **kwargs)
        except BaseException as e:
            logger.traceback()
            raise

    def _validate_fun_args(self) -> None:
        args = inspect.getfullargspec(self.func).args
        args.remove("self")
        unexpected_args = set(args) - set(self.expected_fun_args)
        missing_args = set(self.expected_fun_args) - set(args)

        func_info = (
            f"{self.decl}\n"
            f'In file "{inspect.getfile(self.func)}"\n'
            f"Line number: {inspect.getsourcelines(self.func)[1]}"
        )

        if unexpected_args:
            raise EnvoError(
                f"Unexpected magic function args {list(unexpected_args)}, "
                f"should be {self.expected_fun_args}\n"
                f"{func_info}"
            )

        if missing_args:
            raise EnvoError(f"Missing magic function args {list(missing_args)}:\n" f"{func_info}")

    @property
    def namespaced_name(self):
        name = self.name
        name = name.lstrip("_")

        namespace = f"{self.namespace}." if self.namespace else ""
        return namespace + name


@dataclass
class Command(MagicFunction):
    def call(self, *args, **kwargs) -> str:
        assert self.env is not None
        cwd = Path(".").absolute()

        if self.kwargs["in_root"]:
            os.chdir(str(self.env.meta.root))

        try:
            ret = self.func(*args, **kwargs)
        finally:
            if self.kwargs["cd_back"]:
                os.chdir(str(cwd))

        if ret is not None:
            return str(ret)

    def _validate_fun_args(self) -> None:
        """
        Commands have user defined arguments so we disable this
        """
        pass


class magic_function:  # noqa: N801
    klass = MagicFunction
    kwargs: Dict[str, Any]
    default_kwargs: Dict[str, Any] = {}
    expected_fun_args: List[str] = []
    type: str
    namespace: str = ""

    def __call__(self, func: Callable):
        kwargs = self.default_kwargs.copy()
        kwargs.update(self.kwargs)

        return self.klass(
            name=func.__name__,
            kwargs=kwargs,
            func=func,
            type=self.type,
            expected_fun_args=self.expected_fun_args,
            namespace=self.namespace,
        )

    def __new__(cls, *args: Tuple[Any], **kwargs: Dict[str, Any]):
        # handle case when command decorator is used without arguments and ()
        if not kwargs and args and callable(args[0]):
            kwargs = cls.default_kwargs.copy()
            func: Callable = args[0]  # type: ignore
            return cls.klass(
                name=func.__name__,
                kwargs=kwargs,
                func=func,
                type=cls.type,
                expected_fun_args=cls.expected_fun_args,
                namespace=cls.namespace,
            )
        else:
            obj = super().__new__(cls)
            obj.__init__(**kwargs)
            return obj

    def __init__(self, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> None:
        self.kwargs = kwargs


# decorators
class command(magic_function):  # noqa: N801
    """
    @command decorator class.
    """

    klass = Command
    type: str = "command"
    default_kwargs = {"cd_back": "True", "in_root": "True"}


# Just to satistfy pycharm
if False:

    def command(cd_back: bool = True, in_root: bool = True):
        return MagicFunction()


# decorators
class boot_code(magic_function):  # noqa: N801
    type: str = "boot_code"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


# Just to satistfy pycharm
if False:

    def boot_code(func):
        return MagicFunction()


class event(magic_function):  # noqa: N801
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


# Just to satistfy pycharm
if False:

    def event(func):
        return MagicFunction()


class onload(event):  # noqa: N801
    type: str = "onload"


# Just to satistfy pycharm
if False:

    def onload(func):
        return MagicFunction()


class oncreate(event):  # noqa: N801
    type: str = "oncreate"


# Just to satistfy pycharm
if False:

    def oncreate(func):
        return MagicFunction()


class ondestroy(event):  # noqa: N801
    type: str = "ondestroy"


# Just to satistfy pycharm
if False:

    def ondestroy(func):
        return MagicFunction()


class onunload(event):  # noqa: N801
    type: str = "onunload"


# Just to satistfy pycharm
if False:

    def onunload(func):
        return MagicFunction()


class on_partial_reload(event):  # noqa: N801
    type: str = "on_partial_reload"
    expected_fun_args = ["file", "actions"]


# Just to satistfy pycharm
if False:

    def on_partial_reload(func):
        return MagicFunction()


@dataclass
class Hook(MagicFunction):
    cmd_regex: str = field(init=False, default=None)


class cmd_hook(magic_function):  # noqa: N801
    klass = Hook

    default_kwargs = {"cmd_regex": ".*"}

    def __init__(self, cmd_regex: str = ".*") -> None:
        super().__init__(cmd_regex=cmd_regex)  # type: ignore


class precmd(cmd_hook):  # noqa: N801
    type: str = "precmd"
    expected_fun_args = ["command"]


# Just to satistfy pycharm
if False:

    def precmd(cmd_regex: str = ".*"):
        return MagicFunction()


class onstdout(cmd_hook):  # noqa: N801
    type: str = "onstdout"
    expected_fun_args = ["command", "out"]


# Just to satistfy pycharm
if False:

    def onstdout(func):
        return MagicFunction()


class onstderr(cmd_hook):  # noqa: N801
    type: str = "onstderr"
    expected_fun_args = ["command", "out"]


# Just to satistfy pycharm
if False:

    def onstderr(func):
        return MagicFunction()


class postcmd(cmd_hook):  # noqa: N801
    type: str = "postcmd"
    expected_fun_args = ["command", "stdout", "stderr"]


# Just to satistfy pycharm
if False:

    def postcmd(func):
        return MagicFunction()


@dataclass
class ShellContext(MagicFunction):
    def call(self, *args, **kwargs) -> Dict[str, Any]:
        try:
            ret = self.func(*args, **kwargs)
        except Exception as e:
            logger.traceback()
            ret = {}

        return ret


class shell_context(magic_function):  # noqa: N801
    type: str = "shell_context"

    klass = ShellContext

    def __init__(self) -> None:
        super().__init__()


# Just to satistfy pycharm
if False:

    def shell_context(func):
        return MagicFunction()


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
    "on_partial_reload": on_partial_reload,
}


class Namespace:
    command: Type[Callable]
    shell_context: Type[Callable]
    boot_code: Type[Callable]
    onload: Type[Callable]
    onunload: Type[Callable]
    oncreate: Type[Callable]
    ondestroy: Type[Callable]
    precmd: Type[Callable]
    onstdout: Type[Callable]
    onstderr: Type[Callable]
    on_partial_reload: Type[Callable]

    def __init__(self, name: str) -> None:
        self._name = name

        for n, f in magic_functions.items():
            namespaced_fun = type(f"namespaced_{n}", (f,), {})
            namespaced_fun.namespace = self._name
            setattr(self, n, namespaced_fun)


@dataclass
class Field:
    name: str
    namespace: str
    type: Any
    value: Any
    raw: bool

    @property
    def cleaned_name(self) -> str:
        if self.raw:
            return self.name
        else:
            return self.name.replace("_", "")

    @property
    def namespaced_name(self) -> str:
        if self.raw:
            return self.cleaned_name
        else:
            return f"{self.namespace}_{self.cleaned_name}" if self.namespace else self.cleaned_name

    @property
    def full_name(self) -> str:
        return f"{self.namespace}.{self.cleaned_name}" if self.namespace else self.cleaned_name


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
        for w in self.env_watchers:
            w.start()

        self.li.status.reloader_ready = True

    def stop(self):
        def fun():
            for w in self.env_watchers:
                w.flush()
                w.stop()

        Thread(target=fun).start()


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
        def pythonpath_get(self) -> str:
            return self.pythonpath._value

        def pythonpath_set(self, value: str) -> None:
            parts = value.split(":")

            for p in parts:
                if p in sys.path:
                    continue
                sys.path.append(p)

            self.pythonpath._value = value

        pythonpath: Optional[str] = computed_env_var(raw=True, fget=pythonpath_get, fset=pythonpath_set)
        root: Optional[Path] = env_var()
        path: Optional[str] = env_var(raw=True)
        stage: Optional[str] = env_var()
        envo_stage: Optional[str] = env_var(raw=True)
        envo_name: Optional[str] = env_var(raw=True)

    class Ctx(envium.Ctx):
        pass

    class Secrets(envium.Secrets):
        pass

    ctx: Ctx
    secrets: Secrets
    magic_functions: Dict[str, Any]
    meta: Meta

    env_id_to_secrets: ClassVar[Dict[str, Secrets]] = {}

    def __init__(self):
        self.meta = self.Meta()

        self.e = self.Environ(name=self.meta.name, load=self.meta.load_env_vars)
        self.e.envo_name = self.meta.name

        self.e.root = self.meta.root
        self.e.stage = self.meta.stage
        self.e.envo_stage = self.meta.stage

        self.e.path = os.environ["PATH"]

        if "PYTHONPATH" not in os.environ:
            self.e.pythonpath = ""
        else:
            self.e.pythonpath = os.environ["PYTHONPATH"]

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
            "on_partial_reload": {},
        }

        self._collect_magic_functions()
        self.ctx = self.Ctx(self.meta.name)

        secrets = Env.env_id_to_secrets.get(self.id, self.Secrets(self.meta.name))
        self.secrets = Env.env_id_to_secrets[self.id] = secrets

        self.init()

        self.ctx._validate()
        self.secrets._validate()

        for c in reversed(self.__class__.__mro__):
            if not issubclass(c, BaseEnv):
                continue

            getattr(c, "post_init")(self)

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
        errors = self.e.errors

        if errors:
            raise EnvoError("\n".join([str(e) for e in errors]))

    def get_env_vars(self) -> Dict[str, str]:
        self.e.pythonpath = self.e.pythonpath.strip(":")
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

        for f in dir(self):
            if hasattr_static(self.__class__, f) and inspect.isdatadescriptor(
                inspect.getattr_static(self.__class__, f)
            ):
                continue

            attr = inspect.getattr_static(self, f)

            if isinstance(attr, MagicFunction):
                # inject env into super funtions
                for c in self.__class__.__mro__:
                    try:
                        attr_super = getattr(c, f)
                        attr_super.env = self
                    except AttributeError:
                        pass

                attr.env = self
                self.magic_functions[attr.type][attr.namespaced_name] = attr

    def dump_dot_env(self) -> Path:
        """
        Dump .env file for the current environment.

        File name follows env_{env_name} format.
        """
        path = Path(f".env_{self.meta.stage}")
        content = "\n".join([f'{key}="{value}"' for key, value in self.e.get_env_vars().items()])
        path.write_text(content, "utf-8")
        return path


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
    env: Env

    def __init__(self, calls: _Callbacks, se: _Sets, li: _Links) -> None:
        self._calls = calls
        self._se = se
        self._li = li
        self.env = self._li.env

        if self.env.meta.verbose_run:
            os.environ["ENVO_VERBOSE_RUN"] = "True"
        elif os.environ.get("ENVO_VERBOSE_RUN"):
            os.environ.pop("ENVO_VERBOSE_RUN")

        self._exiting = False
        self._executing_cmd = False

        self._environ_before = None
        self._shell_environ_before = None

        self._files_watchers = self._se.extra_watchers
        self._reload_lock = Lock()

        self.logger: Logger = logger.create_child("envo", descriptor=self.env.meta.name)

        self._environ_before = None
        self._shell_environ_before = None

        self.logger.debug("Starting env", metadata={"root": self.env.meta.root, "stage": self.env.meta.stage})

        self._li.shell.calls.pre_cmd = Callback(self._on_precmd)
        self._li.shell.calls.on_stdout = Callback(self._on_stdout)
        self._li.shell.calls.on_stderr = Callback(self._on_stderr)
        self._li.shell.calls.post_cmd = Callback(self._on_postcmd)
        self._li.shell.calls.on_exit = Callback(self._on_destroy)

        # self.genstub()

        self.reloader = None

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
            functions = self.env.magic_functions["onload"].values()

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
            for name, c in self.env.magic_functions["command"].items():
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

    def _get_shell_context(self) -> Dict[str, Any]:
        shell_context = {}
        for c in self.env.magic_functions["shell_context"].values():
            for k, v in c().items():
                namespaced_name = f"{c.namespace}.{k}" if c.namespace else k
                shell_context[namespaced_name] = v

        return shell_context

    def on_shell_create(self) -> None:
        """
        Called only after creation.
        :return:
        """
        functions = self.env.magic_functions["oncreate"].values()
        for h in functions:
            h()

    def _on_destroy(self) -> None:
        functions = self.env.magic_functions["ondestroy"]
        for h in functions.values():
            h()

        self._exit()

    def _on_env_edit(self, event: FileModifiedEvent) -> None:
        subscribe_events = [
            events.EVENT_TYPE_MOVED,
            events.EVENT_TYPE_MODIFIED,
            events.EVENT_TYPE_CREATED,
            events.EVENT_TYPE_DELETED,
        ]

        if any([s in event.event_type for s in subscribe_events]):
            self.request_reload(metadata={"event": event.event_type, "path": event.src_path})

    def request_reload(self, exc: Optional[Exception] = None, metadata: Optional[Dict] = None) -> None:
        if not metadata:
            metadata = {}

        while self._executing_cmd:
            sleep(0.2)
        self._reload_lock.acquire()

        if self._exiting:
            self._reload_lock.release()
            return

        self._stop_reloaders()

        self.logger.debug(
            "Reloading",
            metadata={"type": "reload", **metadata},
        )

        if exc:
            self._calls.on_error(exc)
        else:
            self._calls.restart()

        self._exiting = True

        self._reload_lock.release()

    def _exit(self) -> None:
        self.logger.debug("Exiting env")
        self._stop_reloaders()

    def activate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if not self._environ_before:
            self._environ_before = os.environ.copy()

        if not self._shell_environ_before:
            self._shell_environ_before = dict(self._li.shell.environ.items())
        self._li.shell.environ.update(**self.env.get_env_vars())

        os.environ.update(**self.env.get_env_vars())

    def validate(self) -> None:
        self.env.validate()

    def _deactivate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if self._environ_before:
            os.environ = self._environ_before.copy()

            if self._li.shell:
                tmp_environ = copy(self._li.shell.environ)
                for i, v in tmp_environ.items():
                    self._li.shell.environ.pop(i)
                for k, v in self._shell_environ_before.items():
                    if v is None:
                        continue
                    self._li.shell.environ[k] = v

    def _is_python_fire_cmd(self, cmd: str) -> bool:
        # validate if it's a correct format
        if "(" in cmd and ")" in cmd:
            return False

        if not cmd:
            return False

        command_name = cmd.split()[0]
        cmd_fun = self.env.magic_functions["command"].get(command_name, None)
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
    def genstub(self) -> None:
        from envo.stub_gen import StubGen

        StubGen(self).generate()

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
        boot_codes_f = self.env.magic_functions["boot_code"]

        codes = []

        for f in boot_codes_f.values():
            codes.extend(f())

        for c in codes:
            self._li.shell.run_code(c)

        self._li.status.source_ready = True

    def _on_precmd(self, command: str) -> Optional[str]:
        functions = self.env.magic_functions["precmd"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                ret = f(command=command)  # type: ignore
                command = ret

        command = self._pre_cmd(command)
        return command

    def _on_stdout(self, command: str, out: bytes) -> str:
        functions = self.env.magic_functions["onstdout"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                ret = f(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def _on_stderr(self, command: str, out: bytes) -> str:
        functions = self.env.magic_functions["onstderr"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                ret = f(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def _on_postcmd(self, command: str, stdout: str, stderr: str) -> None:
        self._post_cmd(command, stdout, stderr)
        functions = self.env.magic_functions["postcmd"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                f(command=command, stdout=stdout, stderr=stderr)  # type: ignore

    def _unload(self) -> None:
        self._deactivate()
        functions = self.env.magic_functions["onunload"]
        for f in functions.values():
            f()
        self._li.shell.calls.reset()
