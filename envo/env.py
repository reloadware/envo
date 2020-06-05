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

from envo.comm import import_module_from_file, setup_logger

setup_logger()

__all__ = ["BaseEnv", "Env", "Raw", "VenvEnv", "command"]


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
    env: Optional["Env"] = None

    def __call__(self, *args: List[Any], **kwargs: Dict[str, Any]) -> Any:
        return self.func(self=self.env, *args, **kwargs)

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


# Decorator
class command:  # noqa: N801
    def __init__(self, glob: bool = False, prop: bool = True, start_in: str = "."):
        self.glob = glob
        self.prop = prop
        self.start_in = start_in

    def __call__(self, func: Callable) -> Any:
        search_result = re.search(r"def (.*):", inspect.getsource(func))
        assert search_result is not None
        decl = search_result.group(1)

        decl = re.sub(r"self,\s?", "", decl)
        cmd = Command(
            name=func.__name__,
            func=func,
            glob=self.glob,
            prop=self.prop,
            decl=decl,
            start_in=self.start_in,
        )

        func.__cmd__ = cmd  # type: ignore

        return func


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

    def __init__(self, name: Optional[str] = None) -> None:
        if name:
            self._name = name
        else:
            self._name = str(self.__class__.__name__)

    # Repeating this code to populate _name without calling super().__init__() in subclasses
    def __post_init__(self) -> None:
        if not hasattr(self, "_name"):
            self._name = str(self.__class__.__name__)

    def validate(self) -> None:
        errors = self.get_errors(self.get_name())
        if errors:
            raise self.EnvException("Detected errors!\n" + "\n".join(errors))

    def get_errors(self, parent_name: str = "") -> List[str]:
        """
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

    def get_namespace(self) -> str:
        return self._name.replace("_", "").upper()

    def activate(self, owner_namespace: str = "") -> None:
        self.validate()
        os.environ.update(**self.get_envs(owner_namespace))

    def get_name(self) -> str:
        return self._name

    @property
    def fields(self) -> Dict[str, Field]:
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

    def get_envs(self, owner_namespace: str = "") -> Dict[str, str]:
        envs = {}
        for f in self.fields.values():
            namespace = ""

            if f.type == Raw:
                var_name = f.name.upper()
            else:
                namespace = f"{owner_namespace}{self.get_namespace()}_"
                var_name = namespace + f.name.replace("_", "").upper()

            if isinstance(f.value, BaseEnv):
                envs.update(f.value.get_envs(owner_namespace=namespace))
            else:
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
            r = v._repr(level + 1) if isinstance(v, BaseEnv) else repr(v)
            ret.append(f"{intend * level}{n}: {type(v).__name__} = {r}")

        return "\n".join(ret)


class Env(BaseEnv):
    class Meta(BaseEnv):
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

        self._environ_before: Dict[str, Any] = os.environ.copy()  # type: ignore

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
        self._collect_commands()

        if self.meta.parent:
            self._init_parent()

    def as_string(self, add_export: bool = False) -> List[str]:
        lines: List[str] = []

        for key, value in self.get_envs().items():
            line = "export " if add_export else ""
            line += f'{key}="{value}"'
            lines.append(line)

        return lines

    def activate(self, owner_namespace: str = "") -> None:
        if self.meta.stage == "comm":
            raise RuntimeError('Cannot activate env with "comm" stage!')

        self.validate()
        os.environ.update(**self.get_envs())

    def print_envs(self) -> None:
        self.activate()
        content = "".join([f"export {line}\n" for line in self.as_string()])
        print(content)

    def dump_dot_env(self) -> None:
        self.activate()
        path = Path(f".env{'_' if self.meta.stage else ''}{self.meta.stage}")
        content = "\n".join(self.as_string())
        path.write_text(content)
        logger.info(f"Saved envs to {str(path)} 💾")

    def get_full_name(self) -> str:
        if self._parent:
            return self._parent.get_full_name() + "." + self.get_name()
        else:
            return self.get_name()

    @classmethod
    def get_current_stage(cls) -> "Env":
        stage = os.environ["ENVO_STAGE"]
        env: "Env" = cls.get_stage(stage)
        return env

    @classmethod
    def get_stage(cls, stage: str) -> "Env":
        env: "Env" = import_module_from_file(cls.Meta.root / f"env_{stage}.py").Env()  # type: ignore
        return env

    def _collect_commands(self) -> None:
        for f in dir(self):
            if f.startswith("_"):
                continue

            if hasattr(self.__class__, f) and inspect.isdatadescriptor(
                getattr(self.__class__, f)
            ):
                continue

            attr = getattr(self, f)

            if hasattr(attr, "__cmd__"):
                cmd = attr.__cmd__
                cmd.env = self
                setattr(self, f, cmd)
                self._commands.append(attr.__cmd__)

    def get_commands(self) -> List[Command]:
        return self._commands

    def get_parent(self) -> Optional["Env"]:
        return self._parent

    def _init_parent(self) -> None:
        assert self.meta.parent
        # unload modules
        for m in list(sys.modules.keys())[:]:
            if m.startswith("env_"):
                sys.modules.pop(m)

        env_dir = self.root.parents[len(self.meta.parent) - 2].absolute()
        sys.path.insert(0, str(env_dir))
        self._parent = import_module_from_file(env_dir / f"env_{self.stage}.py").Env()
        sys.path.pop(0)
        assert self._parent
        self._parent.activate()

    def __repr__(self) -> str:
        ret = []
        ret.append("\n# Commands")
        for c in self._commands:
            s = f"{c.decl}"

            if c.glob:
                s += " # Global"

            ret.append(s)

        return super()._repr() + "\n".join(ret)


class VenvEnv(BaseEnv):
    path: Raw[str]
    bin: Path

    def __init__(self, owner: Env) -> None:
        self._owner = owner
        super().__init__(name="venv")

        self.bin = self._owner.root / ".venv/bin"
        self.path = f"""{str(self.bin)}:{os.environ['PATH']}"""
