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

from envo.misc import import_from_file, setup_logger, EnvoError

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
    "oncreate",
    "onload",
    "onunload",
    "ondestroy",
]


T = TypeVar("T")


if TYPE_CHECKING:
    Raw = Union[T]
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
            raise EnvoError(
                f"Missing magic function args {list(missing_args)}:\n" f"{func_info}"
            )


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
        if ret:
            return str(ret)
        else:
            return "\b"

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
    def __init__(self, *args: Tuple[Any], **kwargs: Dict[str, Any]) -> None:
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
        super().__init__(kwargs={"cmd_regex": cmd_regex})


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
            raise EnvoError("\n".join(errors))

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
                or isinstance(attr, MagicFunction)
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

        return "\n".join(ret) + "\n"


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

        # self._commands: List[Command] = []
        # self._contexts: List[Context] = []
        # self._hooks: Dict[str, List[Hook]] = {
        # }

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

    def get_magic_functions(self) -> Dict[str, List[MagicFunction]]:
        return self._magic_functions

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

            if isinstance(attr, MagicFunction):
                attr.env = self
                self._magic_functions[attr.type].append(attr)

            # if hasattr(attr, "__command__"):
            #     cmd = Command(**attr.__command__, env=self)  # type: ignore
            #     setattr(self, f, cmd)
            #     self._commands.append(cmd)
            #
            # for n in self._hooks.keys():
            #     if hasattr(attr, f"__{n}__"):
            #         hook_kwargs = getattr(attr, f"__{n}__")
            #         hook = Hook(kwargs=hook_kwargs, env=self)  # type: ignore
            #         self._hooks[n].append(hook)
            #
            # if hasattr(attr, "__ctx__"):
            #     ctx = Context(**attr.__ctx__, env=self)  # type: ignore
            #     self._contexts.append(ctx)

        # for n in self._hooks.keys():
        #     self._hooks[n] = sorted(self._hooks[n], key=lambda h: h.priority)

    # def get_commands(self) -> List[Command]:
    #     return self._commands
    #
    # def get_contexts(self) -> List[Context]:
    #     return self._contexts
    #
    # def get_hooks(self) -> Dict[str, List[Hook]]:
    #     return self._hooks

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

        for type, functions in self._magic_functions.items():
            ret.append(f"# {type}")
            for f in functions:
                ret.append(str(f))

        return super()._repr() + "\n".join(ret)


class VenvEnv(BaseEnv):
    """
    Env that activates virtual environment.
    """

    # TODO: change it to a mixin?

    path: Raw[str]
    bin: Path

    def __init__(self, owner: Env) -> None:
        self._owner = owner
        super().__init__(_name="venv")

        self.bin = self._owner.root / ".venv/bin"
        self.path = f"""{str(self.bin)}:{os.environ['PATH']}"""
        site_packages = (
            next((self._owner.root / ".venv/lib").glob("*")) / "site-packages"
        )

        sys.path.insert(0, str(site_packages))
