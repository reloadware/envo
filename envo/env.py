import inspect
import os
import re
import sys
import types
from collections import OrderedDict
from copy import copy
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from threading import Lock, Thread
from time import sleep
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import fire
from rhei import Stopwatch
from watchdog import events
from watchdog.events import FileModifiedEvent

from envo import logger
from envo.logging import Logger
from envo.misc import Callback, EnvoError, FilesWatcher, import_from_file

__all__ = [
    "UserEnv",
    "BaseEnv",
    "Env",
    "Raw",
    "command",
    "context",
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
]


T = TypeVar("T")


if TYPE_CHECKING:
    Raw = Union[T]
    from envo import Plugin
    from envo.shell import Shell
else:

    class Raw(Generic[T]):
        pass


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

    def __call__(self, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
        logger.debug(f'Running magic function (name="{self.name}", type={self.type})')
        if args:
            args = (self.env, *args)  # type: ignore
        else:
            kwargs["self"] = self.env  # type: ignore
        return self.func(*args, **kwargs)

    def render(self) -> str:
        kwargs_str = ", ".join([f"{k}={repr(v)}" for k, v in self.kwargs.items()])
        return f"{self.decl}   {{{kwargs_str}}}"

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
            raise EnvoError(
                f"Missing magic function args {list(missing_args)}:\n" f"{func_info}"
            )

    @property
    def namespaced_name(self):
        name = self.name
        name = name.lstrip("_")

        namespace = f"{self.namespace}." if self.namespace else ""
        return namespace + name


@dataclass
class Command(MagicFunction):
    def call(self) -> str:
        assert self.env is not None
        cwd = Path(".").absolute()
        os.chdir(str(self.env.root))

        ret = self.func(self=self.env)

        os.chdir(str(cwd))
        if ret is not None:
            return str(ret)
        else:
            return ""

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

    def __call__(self, func: Callable) -> Callable:
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

    def __new__(cls, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
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


# decorators
class boot_code(magic_function):  # noqa: N801
    type: str = "boot_code"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class event(magic_function):  # noqa: N801
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class onload(event):  # noqa: N801
    type: str = "onload"


class oncreate(event):  # noqa: N801
    type: str = "oncreate"


class ondestroy(event):  # noqa: N801
    type: str = "ondestroy"


class onunload(event):  # noqa: N801
    type: str = "onunload"


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


class onstdout(cmd_hook):  # noqa: N801
    type: str = "onstdout"
    expected_fun_args = ["command", "out"]


class onstderr(cmd_hook):  # noqa: N801
    type: str = "onstderr"
    expected_fun_args = ["command", "out"]


class postcmd(cmd_hook):  # noqa: N801
    type: str = "postcmd"
    expected_fun_args = ["command", "stdout", "stderr"]


class context(magic_function):  # noqa: N801
    type: str = "context"

    def __init__(self) -> None:
        super().__init__()


magic_functions = {
    "command": command,
    "context": context,
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
    command: Type[command]
    context: Type[context]
    boot_code: Type[boot_code]
    onload: Type[onload]
    onunload: Type[onunload]
    oncreate: Type[oncreate]
    ondestroy: Type[ondestroy]
    precmd: Type[precmd]
    onstdout: Type[onstdout]
    onstderr: Type[onstderr]

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
            return (
                f"{self.namespace}_{self.cleaned_name}"
                if self.namespace
                else self.cleaned_name
            )

    @property
    def full_name(self) -> str:
        return (
            f"{self.namespace}.{self.cleaned_name}"
            if self.namespace
            else self.cleaned_name
        )


class BaseEnv:
    class Meta:
        """
        Environment metadata.
        """

        root: Path
        name: Optional[str] = None
        version: str = "0.1.0"
        parents: List[str] = []
        plugins: List["Plugin"] = []
        watch_files: List[str] = []
        ignore_files: List[str] = []
        emoji: str = ""
        stage: str = "comm"

    root: Path
    path: Raw[str]
    stage: str
    envo_stage: Raw[str]
    pythonpath: Raw[str]

    __initialised__ = False

    def init_parts(self) -> None:
        def decorated_init(klass, fun):
            def init(*args, **kwargs):
                if not klass.__initialised__:
                    klass.__initialised__ = True
                    fun(*args, **kwargs)

            return init

        parts = list(reversed(self.get_user_envs()))
        parts.extend(self.get_plugin_envs())

        for p in parts:
            p.__initialised__ = False

        for p in parts:
            p.__undecorated_init__ = p.__init__
            p.__init__ = decorated_init(p, p.__init__)

        for p in parts:
            if not p.__initialised__:
                p.__init__(self)

        for p in parts:
            p.__init__ = p.__undecorated_init__

    @classmethod
    def is_user_env(cls) -> bool:
        return (
            issubclass(cls, UserEnv)
            and cls is not UserEnv
            and "InheritedEnv" not in str(cls)
        )

    @classmethod
    def is_envo_env(cls) -> bool:
        return (
            issubclass(cls, EnvoEnv)
            and cls is not EnvoEnv
            and "InheritedEnv" not in str(cls)
        )

    @classmethod
    def is_plugin_env(cls) -> bool:
        from envo import Plugin

        return (
            issubclass(cls, Plugin)
            and cls is not Plugin
            and "InheritedEnv" not in str(cls)
        )

    @classmethod
    def get_user_envs(cls) -> List[Type["BaseEnv"]]:
        ret = [p for p in cls.__mro__ if issubclass(p, BaseEnv) and p.is_user_env()]
        return ret

    @classmethod
    def get_parts(cls) -> List[Type["BaseEnv"]]:
        ret = cls.get_user_envs() + cls.get_plugin_envs()
        return ret

    @classmethod
    def get_plugin_envs(cls) -> List[Type["BaseEnv"]]:
        ret = [p for p in cls.__mro__ if issubclass(p, BaseEnv) and p.is_plugin_env()]
        return ret

    @classmethod
    def _get_parents_env(cls, env: Type["BaseEnv"]) -> List[Type["BaseEnv"]]:
        parents = []
        for p in env.Meta.parents:
            parent = import_from_file(Path(str(env.Meta.root / p))).Env
            parents.append(parent)
            parents.extend(cls._get_parents_env(parent))
        return parents

    @classmethod
    def _get_plugin_envs(cls, env: Type["BaseEnv"]) -> List["BaseEnv"]:
        plugins = env.Meta.plugins[:]
        for p in cls._get_parents_env(env):
            plugins.extend(cls._get_plugin_envs(p))

        plugins = list(set(plugins))
        return plugins

    @classmethod
    def get_env_path(cls) -> Path:
        return Path(cls.get_user_envs()[0].__module__)


class EnvoEnv(BaseEnv):
    pass


class ImportedEnv(BaseEnv):
    def __init__(self):
        self.meta = self.Meta()
        self._name = self.meta.name

        self.root = self.meta.root
        self.stage = self.meta.stage
        self.envo_stage = self.stage

        self.path = os.environ["PATH"]

        if "PYTHONPATH" not in os.environ:
            self.pythonpath = ""
        else:
            self.pythonpath = os.environ["PYTHONPATH"]
        self.pythonpath = str(self.root) + ":" + self.pythonpath

        self.init_parts()


class EnvBuilder:
    @classmethod
    def build_env(cls, env: Type[BaseEnv]) -> Type["UserEnv"]:
        parents = env._get_parents_env(env)
        plugins = env._get_plugin_envs(env)

        class InheritedEnv(env, *parents, *plugins):
            pass

        env = InheritedEnv
        env.__name__ = cls.__name__
        env._parents = parents
        return env

    @classmethod
    def build_shell_env(cls, env: Type[BaseEnv]) -> Type["Env"]:
        user_env = cls.build_env(env)

        class InheritedEnv(Env, user_env):
            pass

        return InheritedEnv

    @classmethod
    def build_imported_env(cls, env: Type[BaseEnv]) -> Type["ImportedEnv"]:
        user_env = cls.build_env(env)

        class InheritedEnv(ImportedEnv, user_env):
            pass

        return InheritedEnv

    @classmethod
    def build_shell_env_from_file(cls, file: Path) -> Type["Env"]:
        env = import_from_file(file).Env  # type: ignore
        return cls.build_shell_env(env)


class UserEnv(BaseEnv):
    def __new__(cls) -> "UserEnv":
        env_class = EnvBuilder.build_imported_env(cls)
        obj = ImportedEnv.__new__(env_class)
        obj.__init__()
        return obj


class Env(EnvoEnv):
    """
    Defines environment.
    """

    @dataclass
    class Callbacks:
        restart: Callback
        reloader_ready: Callback
        context_ready: Callback
        on_error: Callable

    @dataclass
    class Links:
        shell: Optional["Shell"]

    @dataclass
    class Sets:
        extra_watchers: List[FilesWatcher]
        reloader_enabled: bool = True
        blocking: bool = False

    _parents: List[Type["Env"]]
    _files_watchers: List[FilesWatcher]
    _default_watch_files = ["env_*.py"]
    _default_ignore_files = [r"**/.*", r"**/*~", r"**/__pycache__"]

    def __new__(cls, *args, **kwargs) -> "Env":
        env = BaseEnv.__new__(cls)
        return env

    def __init__(self, calls: Callbacks, se: Sets, li: Links) -> None:
        self._calls = calls
        self._se = se
        self._li = li

        self.meta = self.Meta()
        self._name = self.meta.name

        self.root = self.meta.root
        self.stage = self.meta.stage
        self.envo_stage = self.stage

        self.path = os.environ["PATH"]

        if "PYTHONPATH" not in os.environ:
            self.pythonpath = ""
        else:
            self.pythonpath = os.environ["PYTHONPATH"]
        self.pythonpath = str(self.root) + ":" + self.pythonpath

        self._exiting = False
        self._executing_cmd = False

        self._environ_before = None
        self._shell_environ_before = None

        self._files_watchers = self._se.extra_watchers
        self._reload_lock = Lock()

        self.logger: Logger = logger.create_child("envo", descriptor=self.meta.name)

        self._environ_before = None
        self._shell_environ_before = None

        self.logger.info(
            "Starting env", metadata={"root": self.root, "stage": self.stage}
        )

        self._magic_functions: Dict[str, Any] = {}

        self._magic_functions["context"]: Dict[str, MagicFunction] = {}
        self._magic_functions["precmd"]: Dict[str, MagicFunction] = {}
        self._magic_functions["onstdout"]: Dict[str, MagicFunction] = {}
        self._magic_functions["onstderr"]: Dict[str, MagicFunction] = {}
        self._magic_functions["postcmd"]: Dict[str, MagicFunction] = {}
        self._magic_functions["onload"]: Dict[str, MagicFunction] = {}
        self._magic_functions["oncreate"]: Dict[str, MagicFunction] = {}
        self._magic_functions["ondestroy"]: Dict[str, MagicFunction] = {}
        self._magic_functions["onunload"]: Dict[str, MagicFunction] = {}
        self._magic_functions["boot_code"]: Dict[str, MagicFunction] = {}
        self._magic_functions["command"]: Dict[str, Command] = {}

        self._collect_magic_functions()

        self._li.shell.calls.pre_cmd = Callback(self._on_precmd)
        self._li.shell.calls.on_stdout = Callback(self._on_stdout)
        self._li.shell.calls.on_stderr = Callback(self._on_stderr)
        self._li.shell.calls.post_cmd = Callback(self._on_postcmd)
        self._li.shell.calls.post_cmd = Callback(self._on_postcmd)
        self._li.shell.calls.on_exit = Callback(self._on_destroy)

        self.init_parts()
        if self._se.reloader_enabled:
            self._collect_watchers()

    def validate(self) -> None:
        """
        Validate env
        """
        self.logger.debug("Validating env")
        errors = self._get_errors()
        if errors:
            raise EnvoError("\n".join(errors))

    def _get_errors(self) -> List[str]:
        """
        Return list of detected errors (unset, undeclared)

        :return: error messages
        """
        # look for undeclared variables
        _internal_objs = ("meta", "logger")

        field_names = set()
        for c in self.__class__.mro():
            if not hasattr(c, "__annotations__"):
                continue
            field_names |= set(
                [f for f in c.__annotations__.keys() if not f.startswith("_")]
            )

        var_names = set()
        f: str
        for f in dir(self):
            # skip properties
            if hasattr(self.__class__, f) and inspect.isdatadescriptor(
                getattr(self.__class__, f)
            ):
                continue

            attr: Any = getattr(self, f)

            if (
                inspect.ismethod(attr)
                or f.startswith("_")
                or inspect.isclass(attr)
                or f in _internal_objs
                or isinstance(attr, MagicFunction)
            ):
                continue

            var_names.add(f)

        unset = field_names - var_names
        undeclr = var_names - field_names

        error_msgs: List[str] = []

        if unset:
            error_msgs += [f'Variable "{v}" is unset!' for v in unset]

        if undeclr:
            error_msgs += [f'Variable "{v}" is undeclared!' for v in undeclr]

        return error_msgs

    def get_name(self) -> str:
        """
        Return env name
        """
        return self._name

    @classmethod
    def fields(cls, obj: Any, namespace: Optional[str] = None) -> Dict[str, Field]:
        """
        Return fields.
        """
        ret = OrderedDict()

        for c in obj.__class__.__mro__:
            if not hasattr(c, "__annotations__"):
                continue
            for f, a in c.__annotations__.items():
                if f.startswith("_"):
                    continue
                attr = getattr(obj, f)
                t = type(attr)

                raw = "envo.env.Raw" in str(a)
                if is_dataclass(t):
                    ret.update(
                        cls.fields(
                            attr,
                            namespace=f"{namespace}_{f}"
                            if namespace and not raw
                            else f,
                        )
                    )
                else:
                    field = Field(
                        name=f, namespace=namespace, type=t, value=attr, raw=raw
                    )
                    ret[field.full_name] = field

        ret = OrderedDict(sorted(ret.items(), key=lambda x: x[0]))

        return ret

    def get_env_vars(self) -> Dict[str, str]:
        """
        Return environmental variables in following format:
        {NAMESPACE_ENVNAME}

        :param owner_name:
        """
        envs = {}
        for name, field in self.fields(self, self._name).items():
            if field.namespaced_name in envs:
                raise EnvoError(f'Variable "{field.namespaced_name}" is redefined')

            envs[field.namespaced_name] = str(field.value)

        envs = {k.upper(): v for k, v in envs.items()}

        return envs

    def repr(self, level: int = 0) -> str:
        ret = []
        ret.append("# Variables")

        for n, v in self.fields(self).items():
            intend = "    "
            r = v._repr(level + 1) if isinstance(v, BaseEnv) else repr(v.value)
            ret.append(f"{intend * level}{n}: {type(v).__name__} = {r}")

        return "\n".join(ret) + "\n"

    def load(self) -> None:
        """
        Called after creation and reload.
        :return:
        """

        def thread(self: Env) -> None:
            logger.debug("Starting onload thread")

            sw = Stopwatch()
            sw.start()
            functions = self._magic_functions["onload"].values()

            if self._se.reloader_enabled:
                self._start_watchers()

            for h in functions:
                try:
                    h()
                except BaseException as e:
                    # TODO: pass env code to exception to get relevant traceback?
                    self._calls.context_ready()
                    self._calls.on_error(e)
                    self._exit()
                    return

            # declare commands
            for name, c in self._magic_functions["command"].items():
                self._li.shell.set_variable(name, c)

            # set context
            self._li.shell.set_context(self._get_context())
            while sw.value <= 0.5:
                sleep(0.1)

            logger.debug("Finished load context thread")
            self._calls.context_ready()

        if not self._se.blocking:
            Thread(target=thread, args=(self,)).start()
        else:
            thread(self)

    def _get_context(self) -> Dict[str, Any]:
        context = {}
        for c in self._magic_functions["context"].values():
            for k, v in c().items():
                namespaced_name = f"{c.namespace}.{k}" if c.namespace else k
                context[namespaced_name] = v

        return context

    def on_shell_create(self) -> None:
        """
        Called only after creation.
        :return:
        """
        functions = self._magic_functions["oncreate"].values()
        for h in functions:
            h()

    def _on_destroy(self) -> None:
        functions = self._magic_functions["ondestroy"]
        for h in functions.values():
            h()

        self._exit()

    def _collect_watchers(self) -> None:
        constituents = self.get_user_envs()

        # inject callback int existing
        for w in self._files_watchers:
            w.calls = FilesWatcher.Callbacks(on_event=Callback(self._on_env_edit))

        for p in constituents:
            watcher = FilesWatcher(
                FilesWatcher.Sets(
                    root=p.Meta.root,
                    include=p.Meta.watch_files + self._default_watch_files,
                    exclude=p.Meta.ignore_files + self._default_ignore_files,
                    name=p.__name__,
                ),
                calls=FilesWatcher.Callbacks(on_event=Callback(self._on_env_edit)),
            )
            self._files_watchers.append(watcher)

    def _start_watchers(self) -> None:
        for w in self._files_watchers:
            w.start()

        self._calls.reloader_ready()

    def _stop_watchers(self):
        def fun():
            for w in self._files_watchers:
                w.stop()

        Thread(target=fun).start()

    def _on_env_edit(self, event: FileModifiedEvent) -> None:
        while self._executing_cmd:
            sleep(0.2)
        self._reload_lock.acquire()

        if self._exiting:
            self._reload_lock.release()
            return

        subscribe_events = [
            events.EVENT_TYPE_MOVED,
            events.EVENT_TYPE_MODIFIED,
            events.EVENT_TYPE_CREATED,
            events.EVENT_TYPE_DELETED,
        ]

        if any([s in event.event_type for s in subscribe_events]):
            if self._se.reloader_enabled:
                self._stop_watchers()

            self.logger.info(
                "Reloading",
                metadata={
                    "type": "reload",
                    "event": event.event_type,
                    "path": event.src_path,
                },
            )

            self._calls.restart()
            self._exiting = True

        self._reload_lock.release()

    def _exit(self) -> None:
        self.logger.info("Exiting env")
        if self._se.reloader_enabled:
            self._stop_watchers()

    def activate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if not self._environ_before:
            self._environ_before = os.environ.copy()

        if not self._shell_environ_before:
            self._shell_environ_before = dict(self._li.shell.environ.items())
        self._li.shell.environ.update(**self.get_env_vars())

        os.environ.update(**self.get_env_vars())

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

    def dump_dot_env(self) -> Path:
        """
        Dump .env file for the current environment.

        File name follows env_{env_name} format.
        """
        path = Path(f".env_{self.meta.stage}")
        content = "\n".join(
            [f'{key}="{value}"' for key, value in self.get_env_vars().items()]
        )
        path.write_text(content, "utf-8")
        return path

    def _collect_magic_functions(self) -> None:
        """
        Go through fields and transform decorated functions to commands.
        """
        for f in dir(self):
            if hasattr(self.__class__, f) and inspect.isdatadescriptor(
                getattr(self.__class__, f)
            ):
                continue

            attr = getattr(self, f)

            if isinstance(attr, MagicFunction):
                attr.env = self
                self._magic_functions[attr.type][attr.namespaced_name] = attr

    def get_repr(self) -> str:
        ret = []

        for type, functions in self._magic_functions.items():
            ret.append(f"# {type}")
            for f in functions:
                ret.append(str(f))

        return super()._repr() + "\n".join(ret)

    def _is_python_fire_cmd(self, cmd: str) -> bool:
        # validate if it's a correct format
        if "(" in cmd and ")" in cmd:
            return False

        if not cmd:
            return False

        command_name = cmd.split()[0]
        cmd_fun = self._magic_functions["command"].get(command_name, None)
        if not cmd_fun:
            return False

        return True

    @precmd
    def _pre_cmd(self, command: str) -> Optional[str]:
        self._executing_cmd = True

        if self._is_python_fire_cmd(command):
            fun = command.split()[0]
            return f'__envo__execute_with_fire__({fun}, "{command}")'

        return command

    @postcmd
    def _post_cmd(self, command: str, stderr: str, stdout: str) -> None:
        self._executing_cmd = False

    @command
    def genstub(self) -> None:
        from envo.stub_gen import StubGen

        StubGen(self).generate()

    @onload
    def _on_load(self) -> None:
        boot_codes_f = self._magic_functions["boot_code"]

        codes = []

        for f in boot_codes_f.values():
            codes.extend(f())

        for c in codes:
            try:
                self._li.shell.run_code(c)
            except Exception as e:
                # TODO: make nice traceback?
                raise e from None

        self.genstub()

    def _on_precmd(self, command: str) -> Tuple[Optional[str], Optional[str]]:
        functions = self._magic_functions["precmd"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                ret = f(command=command)  # type: ignore
                command = ret
        return command

    def _on_stdout(self, command: str, out: bytes) -> str:
        functions = self._magic_functions["onstdout"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                ret = f(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def _on_stderr(self, command: str, out: bytes) -> str:
        functions = self._magic_functions["onstderr"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                ret = f(command=command, out=out)  # type: ignore
                if ret:
                    out = ret
        return out

    def _on_postcmd(
        self, command: str, stdout: List[bytes], stderr: List[bytes]
    ) -> None:
        functions = self._magic_functions["postcmd"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                f(command=command, stdout=stdout, stderr=stderr)  # type: ignore

    def _unload(self) -> None:
        self._deactivate()
        functions = self._magic_functions["onunload"]
        for f in functions.values():
            f()
        self._li.shell.calls.reset()
