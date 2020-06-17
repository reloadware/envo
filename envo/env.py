import inspect
import os
import re
import sys
from dataclasses import dataclass, field, fields
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
    Union,
)

from loguru import logger

from envo.misc import import_from_file, setup_logger

setup_logger()

__all__ = [
    "BaseEnv",
    "Env",
    "Raw",
    "VenvEnv",
    "command",
    "context",
    "precmd",
    "postcmd",
    "onstdout",
    "onstderr",
]


T = TypeVar("T")


if TYPE_CHECKING:
    Raw = Union[T]
else:

    class Raw(Generic[T]):
        pass


@dataclass
class Command:
    name: str
    func: Callable
    glob: bool
    prop: bool
    decl: str
    start_in: str
    env: "Env"

    def __call__(self, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
        if args:
            args = (self, *args)  # type: ignore
        else:
            kwargs["self"] = self  # type: ignore
        return self.func(*args, **kwargs)

    def __repr__(self) -> str:
        if not self.prop:
            return super().__repr__()

        assert self.env is not None
        cwd = Path(".").absolute()
        os.chdir(str(self.env.root / self.start_in))

        ret = self.func(self=self.env)

        os.chdir(str(cwd))
        if ret:
            return str(ret)
        else:
            return "\b"

    def __str__(self) -> str:
        return f"{self.decl}  # property={str(self.prop)}, global={str(self.glob)}"


class FunctionModifier:
    magic_attr_name: str
    kwargs: Dict[str, Any] = {"glob": True, "prop": True, "start_in": "."}

    @classmethod
    def __call__(cls, func: Callable) -> Callable:
        """
        Add kwargs to function object.
        Those kwargs will be later consumed by Env class to create Command objects.

        :param func:
        :return:
        """
        search = re.search(r"def ((.|\s)*?):\n", inspect.getsource(func))
        assert search is not None
        decl = search.group(1)
        decl = re.sub(r"self,?\s?", "", decl)

        # set magic attribute for the function so env get find it and collet
        setattr(
            func,
            f"__{cls.magic_attr_name}__",
            {"name": func.__name__, "func": func, "decl": decl, **cls.kwargs},
        )

        return func


# decorators
class command(FunctionModifier):  # noqa: N801
    """
    @command decorator class.
    """

    magic_attr_name = "command"

    def __new__(cls, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
        # handle case when command decorator is used without arguments and ()
        if not kwargs and args and callable(args[0]):
            cls.kwargs = {"glob": True, "prop": True, "start_in": "."}
            func: Callable = args[0]  # type: ignore
            return cls.__call__(func)
        else:
            return super().__new__(cls)

    def __init__(self, glob: bool = True, prop: bool = True, start_in: str = ".") -> None:
        FunctionModifier.kwargs = {"glob": glob, "prop": prop, "start_in": start_in}


@dataclass
class Hook:
    name: str
    cmd_regex: str
    func: Callable
    decl: str
    env: "Env"
    priority: int

    def __call__(self, *args: List[Any], **kwargs: Dict[str, Any]) -> Any:
        return self.func(self=self.env, *args, **kwargs)

    def __str__(self) -> str:
        return f"{self.decl}"


class hook(FunctionModifier):  # noqa: N801
    def __init__(self, cmd_regex: str, priority: int = 1):
        FunctionModifier.kwargs = {"cmd_regex": cmd_regex, "priority": priority}


class precmd(hook):  # noqa: N801
    magic_attr_name = "precmd"


class onstdout(hook):  # noqa: N801
    magic_attr_name = "onstdout"


class onstderr(hook):  # noqa: N801
    magic_attr_name = "onstderr"


class postcmd(hook):  # noqa: N801
    magic_attr_name = "postcmd"


@dataclass
class Context:
    name: str
    func: Callable
    decl: str
    env: "Env"

    def __call__(self, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
        return self.func(self=self.env)


class context(FunctionModifier):  # noqa: N801
    magic_attr_name = "ctx"

    def __new__(cls, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> Any:
        if not kwargs and args and callable(args[0]):
            func: Callable = args[0]  # type: ignore
            cls.kwargs = {}
            return cls.__call__(func)
        else:
            return super().__new__(cls)


class EnvMetaclass(type):
    def __new__(cls, name: str, bases: Tuple, attr: Dict[str, Any]) -> Any:
        cls = super().__new__(cls, name, bases, attr)
        cls = dataclass(cls, repr=False)  # type: ignore
        return cls


@dataclass
class Field:
    name: str
    type: Any
    value: Any


class BaseEnv(metaclass=EnvMetaclass):
    class EnvException(Exception):
        pass

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
        if not hasattr(self, "_name"):
            self._name = str(self.__class__.__name__)

    def validate(self) -> None:
        """
        Validate env
        """
        errors = self.get_errors(self.get_name())
        if errors:
            raise self.EnvException("Detected errors!\n" + "\n".join(errors))

    def get_errors(self, parent_name: str = "") -> List[str]:
        """
        Return list of detected errors (unset, undeclared)

        :param parent_name:
        :return: error messages
        """
        # look for undeclared variables
        field_names = set(self.fields.keys())

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
                or f == "meta"
                or isinstance(attr, Command)
            ):
                continue

            var_names.add(f)

        unset = field_names - var_names
        undeclr = var_names - field_names

        error_msgs: List[str] = []

        if unset:
            error_msgs += [f'Variable "{parent_name}.{v}" is unset!' for v in unset]

        if undeclr:
            error_msgs += [
                f'Variable "{parent_name}.{v}" is undeclared!' for v in undeclr
            ]

        fields_to_check = field_names - unset - undeclr

        for f in fields_to_check:
            attr2check: Any = getattr(self, f)
            if issubclass(type(attr2check), BaseEnv):
                error_msgs += attr2check.get_errors(parent_name=f"{parent_name}.{f}")

        return error_msgs

    def activate(self, owner_namespace: str = "") -> None:
        """
        Validate and activate environment (put env variables into os.environ)

        :param owner_namespace:
        """
        self.validate()
        os.environ.update(**self.get_env_vars(owner_namespace))

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

        return "\n".join(ret)


class Env(BaseEnv):
    """
    Defines environment.
    """

    class Meta(BaseEnv):
        """
        Environment metadata.
        """

        stage: str = field(default="comm", init=False)
        emoji: str = field(default="", init=False)
        name: str = field(init=False)
        root: Path = field(init=False)
        parent: Optional[str] = field(default=None, init=False)
        version: str = field(default="0.1.0", init=False)

    root: Path
    stage: str
    envo_stage: Raw[str]
    pythonpath: Raw[str]

    def __init__(self) -> None:
        self.meta = self.Meta()
        self.meta.validate()
        super().__init__(self.meta.name)

        self.root = self.meta.root
        self.stage = self.meta.stage
        self.envo_stage = self.stage

        if "PYTHONPATH" not in os.environ:
            self.pythonpath = ""
        else:
            self.pythonpath = os.environ["PYTHONPATH"]
        self.pythonpath = str(self.root) + ":" + self.pythonpath

        self._parent: Optional["Env"] = None

        self._commands: List[Command] = []
        self._contexts: List[Context] = []
        self._hooks: Dict[str, List[Hook]] = {
            "precmd": [],
            "onstdout": [],
            "onstderr": [],
            "postcmd": [],
        }
        self._collect_commands_and_hooks()

        if self.meta.parent:
            self._init_parent()

    def activate(self, owner_namespace: str = "") -> None:
        """
        Validate env and send vars to os.environ

        :param owner_namespace:
        """
        if self.meta.stage == "comm":
            raise RuntimeError('Cannot activate env with "comm" stage!')

        self.validate()
        os.environ.update(**self.get_env_vars())

    def dump_dot_env(self) -> None:
        """
        Dump .env file for the current environment.

        File name follows env_{env_name} format.
        """
        self.activate()
        path = Path(f".env_{self.meta.stage}")
        content = "\n".join(
            [f'{key}="{value}"' for key, value in self.get_env_vars().items()]
        )
        path.write_text(content)
        logger.info(f"Saved envs to {str(path)} 💾")

    def get_full_name(self) -> str:
        """
        Get full name.

        :return: Return a full name in the following format {parent_name}.{env_name}
        """
        if self._parent:
            return self._parent.get_full_name() + "." + self.get_name()
        else:
            return self.get_name()

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
    def get_env_by_stage(cls, stage: str) -> "Env":
        """
        Return env by stage
        :param stage:
        """
        env: "Env" = import_from_file(cls.Meta.root / f"env_{stage}.py").Env()  # type: ignore
        return env

    def _collect_commands_and_hooks(self) -> None:
        """
        Go through fields and transform decorated functions to commands.
        """
        for f in dir(self):
            if f.startswith("_"):
                continue

            if hasattr(self.__class__, f) and inspect.isdatadescriptor(
                getattr(self.__class__, f)
            ):
                continue

            attr = getattr(self, f)

            if hasattr(attr, "__command__"):
                cmd = Command(**attr.__command__, env=self)  # type: ignore
                setattr(self, f, cmd)
                self._commands.append(cmd)

            for n in self._hooks.keys():
                if hasattr(attr, f"__{n}__"):
                    hook_kwargs = getattr(attr, f"__{n}__")
                    hook = Hook(**hook_kwargs, env=self)  # type: ignore
                    self._hooks[n].append(hook)

            if hasattr(attr, "__ctx__"):
                ctx = Context(**attr.__ctx__, env=self)  # type: ignore
                self._contexts.append(ctx)

        for n in self._hooks.keys():
            self._hooks[n] = sorted(self._hooks[n], key=lambda h: h.priority)

    def get_commands(self) -> List[Command]:
        return self._commands

    def get_contexts(self) -> List[Context]:
        return self._contexts

    def get_hooks(self) -> Dict[str, List[Hook]]:
        return self._hooks

    def get_parent(self) -> Optional["Env"]:
        return self._parent

    def _init_parent(self) -> None:
        """
        Initialize parent if exists.
        """
        assert self.meta.parent
        # unload modules just in case env with the same name has been already loaded
        for m in list(sys.modules.keys())[:]:
            if m.startswith("env_"):
                sys.modules.pop(m)

        env_dir = self.root.parents[len(self.meta.parent) - 2].absolute()
        sys.path.insert(0, str(env_dir))
        self._parent = import_from_file(env_dir / f"env_{self.stage}.py").Env()
        sys.path.pop(0)
        assert self._parent
        self._parent.activate()

    def __repr__(self) -> str:
        ret = []
        ret.append("\n# Commands")
        for c in self._commands:
            ret.append(str(c))

        return super()._repr() + "\n".join(ret)


class VenvEnv(BaseEnv):
    """
    Env that activates virtual environment.
    """

    path: Raw[str]
    bin: Path

    def __init__(self, owner: Env) -> None:
        self._owner = owner
        super().__init__(_name="venv")

        self.bin = self._owner.root / ".venv/bin"
        self.path = f"""{str(self.bin)}:{os.environ['PATH']}"""
