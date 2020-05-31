import inspect
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from loguru import logger

from envo.comm import import_module_from_file

__all__ = ["BaseEnv", "Env", "Raw", "VenvEnv"]


T = TypeVar("T")


if TYPE_CHECKING:
    Raw = Union[T]
else:

    class Raw(Generic[T]):
        pass


class EnvMetaclass(type):
    def __new__(cls, name: str, bases: Tuple, attr: Dict[str, Any]) -> Any:
        cls = super().__new__(cls, name, bases, attr)
        cls = dataclass(cls, repr=False)  # type: ignore
        return cls


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
        field_names = set([fie.name for fie in fields(self)])

        var_names = set()
        f: str
        for f in dir(self):
            attr: Any = getattr(self, f)

            if hasattr(self.__class__, f):
                class_attr: Any = getattr(self.__class__, f)
            else:
                class_attr = None

            if (
                inspect.ismethod(attr)
                or (class_attr is not None and inspect.isdatadescriptor(class_attr))
                or f.startswith("_")
                or inspect.isclass(attr)
                or f == "meta"
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

        for f in fields(self):
            var = getattr(self, f.name)

            namespace = ""
            var_name = ""
            var_type: Any = None
            if hasattr(f.type, "__origin__"):
                var_type = f.type.__origin__

            if var_type == Raw:
                var_name = f.name.upper()
            else:
                namespace = f"{owner_namespace}{self.get_namespace()}_"
                var_name = namespace + f.name.replace("_", "").upper()

            if isinstance(var, BaseEnv):
                var.activate(owner_namespace=namespace)
            else:
                os.environ[var_name] = str(var)

    def get_name(self) -> str:
        return self._name

    def __str__(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return self._repr()

    def _repr(self, level: int = 0) -> str:
        ret = []
        for f in fields(self):
            attr = getattr(self, f.name)
            intend = "    "
            r = attr._repr(level + 1) if isinstance(attr, BaseEnv) else repr(attr)
            ret.append(f"{intend * level}{f.name}: {type(attr).__name__} = {r}")

        return "\n" + "\n".join(ret)


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

    def __init__(self) -> None:
        self.meta = self.Meta()
        self.meta.validate()
        super().__init__(self.meta.name)

        self._environ_before: Dict[str, Any] = os.environ.copy()  # type: ignore

        self.root = self.meta.root
        self.stage = self.meta.stage
        self.envo_stage = self.stage

        self._parent: Optional["Env"] = None

        if self.meta.parent:
            self._init_parent()

    def as_string(self, add_export: bool = False) -> List[str]:
        lines: List[str] = []

        for key, value in os.environ.items():
            if key in self._environ_before and value == self._environ_before[key]:
                continue

            if "BASH_FUNC_" not in key:
                line = "export " if add_export else ""
                line += f'{key}="{value}"'
                lines.append(line)

        return lines

    def activate(self, owner_namespace: str = "") -> None:
        if self.meta.stage == "comm":
            raise RuntimeError('Cannot activate env with "comm" stage!')

        super().activate(owner_namespace)

        self._set_pythonpath()

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

    def get_parent(self) -> Optional["Env"]:
        return self._parent

    def _init_parent(self) -> None:
        assert self.meta.parent
        env_dir = self.root.parents[len(self.meta.parent) - 2].absolute()
        self._parent = import_module_from_file(env_dir / f"env_{self.stage}.py").Env()
        assert self._parent
        self._parent.activate()

    def _set_pythonpath(self) -> None:
        if "PYTHONPATH" not in os.environ:
            os.environ["PYTHONPATH"] = ""

        os.environ["PYTHONPATH"] = (
            str(self.root.parent) + ":" + os.environ["PYTHONPATH"]
        )

        if self._parent:
            self._parent._set_pythonpath()


class VenvEnv(BaseEnv):
    path: Raw[str]
    bin: Path

    def __init__(self, owner: Env) -> None:
        self._owner = owner
        super().__init__(name="venv")

        self.bin = self._owner.root / ".venv/bin"
        self.path = f"""{str(self.bin)}:{os.environ['PATH']}"""
