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

from envo import logger
from envo.logging import Logger
from envo.misc import Callback, EnvoError, Inotify, import_from_file

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
    "boot_code"
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
    env: Optional["Env"] = field(init=False, default=None)

    def __post_init__(self) -> None:
        search = re.search(r"def ((.|\s)*?):\n", inspect.getsource(self.func))
        assert search is not None
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
            raise EnvoError(f"Missing magic function args {list(missing_args)}:\n" f"{func_info}")


@dataclass
class Command(MagicFunction):
    namespace: str = field(init=False, default=None)

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

    def __call__(self, func: Callable) -> Callable:
        kwargs = self.default_kwargs.copy()
        kwargs.update(self.kwargs)

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
            kwargs = cls.default_kwargs.copy()
            func: Callable = args[0]  # type: ignore
            return cls.klass(
                name=func.__name__,
                kwargs=kwargs,
                func=func,
                type=cls.__name__,
                expected_fun_args=cls.expected_fun_args,
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
    default_kwargs = {"namespace": ""}

    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace=namespace)  # type: ignore


# decorators
class boot_code(magic_function):  # noqa: N801
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


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


@dataclass
class Hook(MagicFunction):
    cmd_regex: str = field(init=False, default=None)


class cmd_hook(magic_function):  # noqa: N801
    klass = Hook

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
    raw: bool


class BaseFields:
    root: Path
    path: Raw[str]
    stage: str
    envo_stage: Raw[str]
    pythonpath: Raw[str]


class BaseEnv(BaseFields):
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


class Env(BaseFields):
    """
    Defines environment.
    """

    @dataclass
    class Callbacks:
        restart: Callback
        reloader_ready: Callback
        context_ready: Callback
        on_error: Callable


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
        super().__init__()
        self._calls = calls

        self._reloader_enabled = reloader_enabled
        self._shell = shell

        self.meta = self.Meta()

        self._name = self.meta.name

        self.logger: Logger = logger

        self._exiting = False
        self._executing_cmd = False

        self._files_watchers = []
        self._reload_lock = Lock()

        self.logger: Logger = logger.create_child("envo", descriptor=self.meta.name)

        self._environ_before = None
        self._shell_environ_before = None

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

        for p in self.__class__.__mro__:
            if "InheritedEnv" in str(p):
                continue

            if issubclass(p, BaseEnv):
                p.__init__(self)

        self.validate()

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
            field_names |= set([f for f in c.__annotations__.keys() if not f.startswith("_")])

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
                error_msgs += attr2check._get_errors()

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
        ret = OrderedDict()

        for c in self.__class__.mro():
            if not hasattr(c, "__annotations__"):
                continue
            for f, a in c.__annotations__.items():
                if f.startswith("_"):
                    continue
                attr = getattr(self, f)
                t = type(attr)
                raw = "Raw" in str(a)
                ret[f] = Field(name=f, type=t, value=attr, raw=raw)

        ret = OrderedDict(sorted(ret.items(), key=lambda x: x[0]))

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
                if f.raw:
                    var_name = f.name.upper()
                else:
                    var_name = namespace + f.name.replace("_", "").upper()

                envs[var_name] = str(f.value)

        return envs

    def _repr(self, level: int = 0) -> str:
        ret = []
        ret.append("# Variables")

        for n, v in self.fields.items():
            intend = "    "
            r = v._repr(level + 1) if isinstance(v, BaseEnv) else repr(v.value)
            ret.append(f"{intend * level}{n}: {type(v).__name__} = {r}")

        return "\n".join(ret) + "\n"

    def _add_namespace_if_not_exists(self, name: str) -> None:
        self._shell.run_code(f'class Namespace: pass\n{name} = Namespace() if "{name}" not in globals() else {name}')

    def _load(self) -> None:
        """
        Called after creation and reload.
        :return:
        """
        def thread(self: Env) -> None:
            logger.debug("Starting onload thread")

            self._shell.calls.on_enter = Callback(self._on_create)
            self._shell.calls.pre_cmd = Callback(self._on_precmd)
            self._shell.calls.on_stdout = Callback(self._on_stdout)
            self._shell.calls.on_stderr = Callback(self._on_stderr)
            self._shell.calls.post_cmd = Callback(self._on_postcmd)
            self._shell.calls.post_cmd = Callback(self._on_postcmd)
            self._shell.calls.on_exit = Callback(self._on_destroy)

            if self._reloader_enabled:
                self._start_watchers()

            sw = Stopwatch()
            sw.start()
            functions = self._magic_functions["onload"].values()

            for h in functions:
                try:
                    h()
                except BaseException as e:
                    # TODO: pass env code to exception to get relevant traceback?
                    self._calls.on_error(e)
                    self._exit()
                    return

            self._activate()

            # declare commands
            for name, c in self._magic_functions["command"].items():
                if c.namespace:
                    self._add_namespace_if_not_exists(c.namespace)
                self._shell.set_variable(name, c)

            self._shell.set_context(self._get_context())

            while sw.value <= 0.5:
                sleep(0.1)

            logger.debug("Finished load context thread")
            self._calls.context_ready()

        Thread(target=thread, args=(self,)).start()

    def _on_create(self) -> None:
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

    def _exit(self) -> None:
        self.logger.info("Exiting env")
        if self._reloader_enabled:
            self._stop_watchers()

    def _activate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if not self._environ_before:
            self._environ_before = os.environ.copy()

        if not self._shell_environ_before:
            self._shell_environ_before = dict(self._shell.environ.items())
        self._shell.environ.update(**self.get_env_vars())

        os.environ.update(**self.get_env_vars())

    def _deactivate(self) -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if self._environ_before:
            os.environ = self._environ_before.copy()

            if self._shell:
                tmp_environ = copy(self._shell.environ)
                for i, v in tmp_environ.items():
                    self._shell.environ.pop(i)
                self._shell.environ.update(**self._shell_environ_before)

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
    def _build_env(cls, env: Type[BaseEnv]) -> Type["Env"]:
        parents = cls._get_parents_env(env)

        class InheritedEnv(cls, env, *parents, *env.Meta.plugins):
            pass

        env = InheritedEnv
        env.__name__ = cls.__name__
        env._parents = parents
        return env

    @classmethod
    def _build_env_from_file(cls, file: Path) -> Type["Env"]:
        env = import_from_file(file).Env  # type: ignore
        return cls._build_env(env)

    @classmethod
    def _get_parents_env(cls, env: Type[BaseEnv]) -> List[BaseEnv]:
        parents = []
        for p in env.Meta.parents:
            parent = import_from_file(Path(str(env.Meta.root / p))).Env
            parents.append(parent)
            parents.extend(cls._get_parents_env(parent))
        return parents

    def _get_context(self) -> Dict[str, Any]:
        context = {}
        functions = self._magic_functions["context"]

        for c in functions.values():
            context.update(c())

        return context

    def _collect_magic_functions(self) -> None:
        """
        Go through fields and transform decorated functions to commands.
        """
        for f in dir(self):
            if hasattr(self.__class__, f) and inspect.isdatadescriptor(getattr(self.__class__, f)):
                continue

            attr = getattr(self, f)

            if isinstance(attr, Command):
                name = attr.name
                name = name.lstrip("_")

                attr.env = self
                namespace = f"{attr.namespace}." if attr.namespace else ""
                self._magic_functions[attr.type][f"{namespace}{name}"] = attr
            elif isinstance(attr, MagicFunction):
                name = f

                attr.env = self
                self._magic_functions[attr.type][name] = attr

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
            cmd_name = command.split()[0]
            return f'__envo__execute_with_fire__({cmd_name}, "{command}")'

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
                self._shell.run_code(c)
            except Exception as e:
                # TODO: make nice traceback?
                raise e from None

        self.genstub()

    def _on_precmd(self, command: str) -> Optional[str]:
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

    def _on_postcmd(self, command: str, stdout: List[bytes], stderr: List[bytes]) -> None:
        functions = self._magic_functions["postcmd"]
        for f in functions.values():
            if re.match(f.kwargs["cmd_regex"], command):
                f(command=command, stdout=stdout, stderr=stderr)  # type: ignore

    def _unload(self) -> None:
        self._deactivate()
        functions = self._magic_functions["onunload"]
        for f in functions.values():
            f()
        self._shell.calls.reset()
