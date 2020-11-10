import inspect
import os
import re
from copy import copy
from threading import Lock
from time import sleep

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union, Type,
)


from envo import logger
from envo.logging import Logger

from envo.misc import import_from_file, EnvoError, Callback, Inotify


__all__ = [
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
]

T = TypeVar("T")


if TYPE_CHECKING:
    Raw = Union[T]
    from envo.shell import Shell
    from envo import Plugin
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
    env: Optional["Env"] = None

    def __post_init__(self) -> None:
        search = re.search(r"def ((.|\s)*?):\n", inspect.getsource(self.func))
        assert search is not None
        decl = search.group(1)
        decl = re.sub(r"self,?\s?", "", decl)
        self.decl = decl

        self._validate_fun_args()

    def __call__(self, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
        logger.debug(f'Running magic function (name="{self.name}", type={self.type})')
        if args:
            args = (self.env, *args)  # type: ignore
        else:
            kwargs["self"] = self.env  # type: ignore
        return self.func(*args, **kwargs)

    def __str__(self) -> str:
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
            raise EnvoError(f"Missing magic function args {list(missing_args)}:\n" f"{func_info}")


@dataclass
class Command(MagicFunction):
    def __repr__(self) -> str:
        if not self.kwargs["prop"]:
            return super().__repr__()

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
        :return:
        """
        pass


class magic_function:  # noqa: N801
    klass = MagicFunction
    default_kwargs: Dict[str, Any] = {}
    expected_fun_args: List[str] = []

    def __call__(self, func: Callable) -> Callable:
        kwargs = self.default_kwargs.copy()
        kwargs.update(**self.kwargs)

        return self.klass(
            name=func.__name__,
            kwargs=kwargs,
            func=func,
            type=self.__class__.__name__,
            expected_fun_args=self.expected_fun_args,
        )

    def __new__(cls, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
        # handle case when command decorator is used without arguments and ()
        if not kwargs and args and callable(args[0]):
            func: Callable = args[0]  # type: ignore
            return cls.klass(
                name=func.__name__,
                kwargs=cls.default_kwargs,
                func=func,
                type=cls.__name__,
                expected_fun_args=cls.expected_fun_args,
            )
        else:
            return super().__new__(cls)

    def __init__(self, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> None:
        self.kwargs = kwargs


# decorators
class command(magic_function):  # noqa: N801
    """
    @command decorator class.
    """

    klass = Command
    default_kwargs = {"glob": True, "prop": True}

    def __init__(self, glob: bool = True, prop: bool = True) -> None:
        super().__init__(glob=glob, prop=prop)  # type: ignore


class event(magic_function):  # noqa: N801
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class onload(event):  # noqa: N801
    pass


class oncreate(event):  # noqa: N801
    pass


class ondestroy(event):  # noqa: N801
    pass


class onunload(event):  # noqa: N801
    pass


class cmd_hook(magic_function):  # noqa: N801
    default_kwargs = {"cmd_regex": ".*"}

    def __init__(self, cmd_regex: str = ".*") -> None:
        super().__init__(cmd_regex=cmd_regex)  # type: ignore


class precmd(cmd_hook):  # noqa: N801
    expected_fun_args = ["command"]


class onstdout(cmd_hook):  # noqa: N801
    expected_fun_args = ["command", "out"]


class onstderr(cmd_hook):  # noqa: N801
    expected_fun_args = ["command", "out"]


class postcmd(cmd_hook):  # noqa: N801
    expected_fun_args = ["command", "stdout", "stderr"]


class context(magic_function):  # noqa: N801
    def __init__(self) -> None:
        super().__init__()


@dataclass
class Field:
    name: str
    type: Any
    value: Any


@dataclass
class BaseEnv:
    def __init__(self, _name: Optional[str] = None) -> None:
        """
        :param _name: with underscore so it doesn't conflict with possible field with name "name"
        """
        if _name:
            self._name = _name
        else:
            self._name = str(self.__class__.__name__)

    def __post_init__(self) -> None:
        """
        Repeating this code to populate _name when super().__init__() is not called in subclasses
        """

        self.logger: Logger = logger

        if not hasattr(self, "_name"):
            self._name = str(self.__class__.__name__)

    def validate(self) -> None:
        """
        Validate env
        """
        self.logger.debug("Validating env")
        errors = self.get_errors()
        if errors:
            raise EnvoError("\n".join(errors))

    def get_errors(self) -> List[str]:
        """
        Return list of detected errors (unset, undeclared)

        :return: error messages
        """
        # look for undeclared variables
        _internal_objs = ("meta", "logger")

        field_names = set()
        for c in self.__class__.mro():
            if not is_dataclass(c):
                continue
            field_names |= set([f.name for f in fields(c) if not f.name.startswith("_")])

        var_names = set()
        f: str
        for f in dir(self):
            # skip properties
            if hasattr(self.__class__, f) and inspect.isdatadescriptor(getattr(self.__class__, f)):
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

        fields_to_check = field_names - unset - undeclr

        for f in fields_to_check:
            attr2check: Any = getattr(self, f)
            if issubclass(type(attr2check), BaseEnv):
                error_msgs += attr2check.get_errors()

        return error_msgs

    def get_name(self) -> str:
        """
        Return env name
        """
        return self._name

    @property
    def fields(self) -> Dict[str, Field]:
        """
        Return fields.
        """
        ret = {}
        for f in fields(self):
            if f.name.startswith("_"):
                continue

            if hasattr(self, f.name):
                attr = getattr(self, f.name)
                if hasattr(f.type, "__origin__"):
                    t = f.type.__origin__
                else:
                    t = type(attr)
                ret[f.name] = Field(name=f.name, type=t, value=attr)
            else:
                ret[f.name] = Field(name=f.name, type="undefined", value="undefined")

        return ret

    def get_env_vars(self, owner_name: str = "") -> Dict[str, str]:
        """
        Return environmental variables in following format:
        {NAMESPACE_ENVNAME}

        :param owner_name:
        """
        envs = {}
        for f in self.fields.values():
            namespace = f'{owner_name}{self._name.replace("_", "").upper()}_'
            if isinstance(f.value, BaseEnv):
                envs.update(f.value.get_env_vars(owner_name=namespace))
            else:
                if f.type == Raw:
                    var_name = f.name.upper()
                else:
                    var_name = namespace + f.name.replace("_", "").upper()

                envs[var_name] = str(f.value)

        return envs

    def __str__(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return self._repr()

    def _repr(self, level: int = 0) -> str:
        ret = []
        ret.append("# Variables")

        for n, v in self.fields.items():
            intend = "    "
            r = v._repr(level + 1) if isinstance(v, BaseEnv) else repr(v.value)
            ret.append(f"{intend * level}{n}: {type(v).__name__} = {r}")

        return "\n".join(ret) + "\n"


@dataclass
class Env(BaseEnv):
    """
    Defines environment.
    """

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

    @dataclass
    class Callbacks:
        restart: Callback
        reloader_ready: Callback

    root: Path
    path: Raw[str]
    stage: str
    envo_stage: Raw[str]
    pythonpath: Raw[str]

    _parents: List[Type["Env"]]
    _files_watchers: List[Inotify]
    _default_watch_files = ["**/", "env_*.py"]
    _default_ignore_files = [
        r"**/.*",
        r"**/*~",
        r"**/__pycache__",
        r"**/__envo_lock__"
    ]

    def __init__(self, shell: Optional["Shell"], calls: Callbacks,
                 reloader_enabled: bool=True) -> None:
        self._calls = calls
        self.meta = self.Meta()
        super().__init__(self.meta.name)

        self.logger: Logger = logger.create_child("envo", descriptor=self.meta.name)

        self._environ_before = None
        self._shell_environ_before = None
        self._reloader_enabled = reloader_enabled

        self._shell = shell

        self.root = self.meta.root
        self.stage = self.meta.stage
        self.envo_stage = self.stage
        self.logger.info("Starting env", metadata={"root": self.root, "stage": self.stage})

        self.path = os.environ["PATH"]

        if "PYTHONPATH" not in os.environ:
            self.pythonpath = ""
        else:
            self.pythonpath = os.environ["PYTHONPATH"]
        self.pythonpath = str(self.root) + ":" + self.pythonpath

        self._magic_functions: Dict[str, List[MagicFunction]] = {
            "context": [],
            "command": [],
            "precmd": [],
            "onstdout": [],
            "onstderr": [],
            "postcmd": [],
            "onload": [],
            "oncreate": [],
            "ondestroy": [],
            "onunload": [],
        }
        self._collect_commands_and_hooks()

        self._files_watchers = []
        self._reload_lock = Lock()

        self._exiting = False
        self._executing_cmd = False

        if self._reloader_enabled:
            self._start_watchers()

    def __post_init__(self):
        self.validate()

    def _start_watchers(self) -> None:
        constituents = self._parents + [self.__class__]
        for p in constituents:
            watcher = Inotify(
                Inotify.Sets(
                    root=p.Meta.root,
                    include=p.Meta.watch_files + self._default_watch_files,
                    exclude=p.Meta.ignore_files + self._default_ignore_files
                ),
                calls=Inotify.Callbacks(on_event=Callback(self._on_env_edit)),
            )
            watcher.start()

            self._files_watchers.append(watcher)

        self._calls.reloader_ready()

    def _stop_watchers(self):
        for w in self._files_watchers:
            w.stop()

    def _on_env_edit(self, event: Inotify.Event) -> None:
        while self._executing_cmd:
            sleep(0.2)
        self._reload_lock.acquire()

        if self._exiting:
            self._reload_lock.release()
            return

        subscribe_events = ["IN_CLOSE_WRITE", "IN_CREATE", "IN_DELETE", "IN_DELETE_SELF"]

        if any([s in event.type_names for s in subscribe_events]):
            if self._reloader_enabled:
                self._stop_watchers()

            self.logger.info('Reloading',
                        metadata={"type": "reload", "event": event.type_names, "path": event.path.absolute.resolve()})

            self._calls.restart()
            self._exiting = True

        self._reload_lock.release()

    def exit(self) -> None:
        self.logger.info("Exiting env")
        if self._reloader_enabled:
            self._stop_watchers()

    def activate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if not self._environ_before:
            self._environ_before = os.environ.copy()

        if self._shell:
            if not self._shell_environ_before:
                self._shell_environ_before = dict(self._shell.environ.items())
            self._shell.environ.update(**self.get_env_vars())

        os.environ.update(**self.get_env_vars())

    def deactivate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        os.environ = self._environ_before.copy()

        if self._shell:
            tmp_environ = copy(self._shell.environ)
            for i, v in tmp_environ.items():
                self._shell.environ.pop(i)
            self._shell.environ.update(**self._shell_environ_before)

    def get_magic_functions(self) -> Dict[str, List[MagicFunction]]:
        return self._magic_functions

    def dump_dot_env(self) -> Path:
        """
        Dump .env file for the current environment.

        File name follows env_{env_name} format.
        """
        path = Path(f".env_{self.meta.stage}")
        content = "\n".join([f'{key}="{value}"' for key, value in self.get_env_vars().items()])
        path.write_text(content)
        return path

    @classmethod
    def get_name(cls) -> str:
        return cls.Meta.name if cls.Meta.name else ""

    @classmethod
    def get_current_env(cls) -> "Env":
        """
        Return current activated environment.

        Useful in python scripts.
        Import env_comm and run this function to retrieve current environment.
        :return: Current environment object
        """
        stage = os.environ["ENVO_STAGE"]
        env: "Env" = cls.get_env_by_stage(stage)
        return env

    @classmethod
    def build_env(cls) -> Type["Env"]:
        parents = list(reversed([cls.get_parent_env(p) for p in cls.Meta.parents]))

        class InheritedEnv(*cls.Meta.plugins, cls, *parents):
            pass

        env = InheritedEnv
        env.__name__ = cls.__name__
        env._parents = parents
        return env

    @classmethod
    def build_env_from_file(cls, file: Path) -> Type["Env"]:
        Env = import_from_file(file).Env  # type: ignore
        return Env.build_env()

    @classmethod
    def get_parent_env(cls, parent_path: str) -> Type["Env"]:
        return cls.build_env_from_file(Path(str(cls.Meta.root / parent_path)))

    @classmethod
    def get_env_by_stage(cls, stage: str) -> Type["Env"]:
        """
        Return env by stage
        :param stage:
        """

        env: Type["Env"] = cls.build_env_from_file(Path(f"env_{stage}.py"))  # type: ignore
        return env

    def _collect_commands_and_hooks(self) -> None:
        """
        Go through fields and transform decorated functions to commands.
        """
        for f in dir(self):
            if hasattr(self.__class__, f) and inspect.isdatadescriptor(getattr(self.__class__, f)):
                continue

            attr = getattr(self, f)

            if isinstance(attr, MagicFunction):
                attr.env = self
                self._magic_functions[attr.type].append(attr)

    def __repr__(self) -> str:
        ret = []

        for type, functions in self._magic_functions.items():
            ret.append(f"# {type}")
            for f in functions:
                ret.append(str(f))

        return super()._repr() + "\n".join(ret)

    @precmd
    def _pre_cmd(self, command: str) -> str:
        self._executing_cmd = True
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
        self.genstub()
