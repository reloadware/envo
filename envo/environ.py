import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    Union, ClassVar
)

# Python >= 3.8
import typing

from envo.misc import EnvoError

try:
    typing.get_args
    typing.get_origin
# Compatibility
except AttributeError:
    typing.get_args = lambda t: getattr(t, '__args__', ()) if t is not Generic else Generic
    typing.get_origin = lambda t: getattr(t, '__origin__', None)


if TYPE_CHECKING:
    from envo.env import BaseEnv



__all__ = [
    "var",
    "computed_var",
    "VarGroup"
]

class ValidationError(ABC, EnvoError):
    pass


class WrongTypeError(ValidationError):
    def __init__(self, type_: Type, var_name: str, got_type: Type) -> None:
        msg = f'Expected type "{type_.__name__}" for var "{var_name}" got "{got_type}"'
        super().__init__(msg)


class NoTypeError(ValidationError):
    def __init__(self, var_name: str) -> None:
        msg = f'Type annotation for var "{var_name}" is missing'
        super().__init__(msg)


class NoValueError(ValidationError):
    def __init__(self, type_: Type, var_name: str) -> None:
        msg = f'Expected value of type "{type_.__name__}" for var "{var_name}" not None'
        super().__init__(msg)


class ComputedVarError(ValidationError):
    def __init__(self, var_name: str, exception: Exception) -> None:
        msg = f'During computing "{var_name}" following error occured: \n{repr(exception)}'
        super().__init__(msg)



VarType = Type["VarType"]

class VarMixin:
    def __setattr__(self, key: str, value: Any) -> None:
        if key == "_attr_hooks_enabled":
            object.__setattr__(self, key, value)
            return

        if not hasattr(self, key):
            object.__setattr__(self, key, value)
            return

        attr = object.__getattribute__(self, key)

        if not isinstance(attr, BaseVar):
            object.__setattr__(self, key, value)
            return

        try:
            object.__getattribute__(attr, "_attr_hooks_enabled")
        except AttributeError:
            object.__setattr__(attr, "_attr_hooks_enabled", True)

        if not object.__getattribute__(attr, "_attr_hooks_enabled"):
            object.__setattr__(self, key, value)
            return

        if not object.__getattribute__(attr, "_final"):
            object.__setattr__(self, key, value)
            return

        # if not object.__getattribute__(attr, "_attr_hooks_enabled"):
        #     return attr

        object.__getattribute__(attr, "set_value")(value)

    def __getattribute__(self, item: str) -> Any:
        attr = object.__getattribute__(self, item)

        if item == "_attr_hooks_enabled":
            return attr

        if not isinstance(attr, BaseVar):
            return attr

        try:
            object.__getattribute__(attr, "_attr_hooks_enabled")
        except AttributeError:
            object.__setattr__(attr, "_attr_hooks_enabled", True)

        if not object.__getattribute__(attr, "_attr_hooks_enabled"):
            return attr

        if not object.__getattribute__(attr, "_final"):
            return attr

        return object.__getattribute__(attr, "get_value")()


@dataclass(repr=False)
class BaseVar(ABC, VarMixin):
    _raw: bool
    _name: str
    _type_: Type
    _env: "BaseEnv"
    _parent: Optional["BaseVar"]
    _root_name: str
    _optional: bool

    _vars: List["BaseVar"] = field(init=False, default_factory=list)
    _value: Optional[VarType] = field(init=False, default=None)

    _final: ClassVar[bool] = True

    @abstractmethod
    def get_errors(self) -> List[ValidationError]:
        return []

    def get_env_name(self) -> str:
        if self._raw:
            ret = self._name
        else:
            ret = self.fullname
            ret = ret.replace("_", "").replace(".", "_")

        ret = ret.upper()

        return ret

    @property
    def fullname(self) -> str:
        if self._raw:
            return self._name

        ret = f"{self._parent.fullname}.{self._name}" if self._parent else f"{self._root_name}.{self._name}"
        return ret

    def __repr__(self) -> str:
        return f"{self.fullname}"

    @abstractmethod
    def get_value(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def set_value(self, new_value) -> None:
        raise NotImplementedError


# Serves as a blueprint
@dataclass(repr=False)
class var:
    raw: bool = False
    default: VarType = None
    default_factory: Optional[Callable] = None

    _root_name: Optional[str] = field(init=False, default=None)

    def factory(self, type_: Type, optional: bool, name: str, env: "BaseEnv", parent: "BaseVar", root_name: str) -> "BaseVar":
        ret = Var(_raw=self.raw, _optional=optional, _default=self.default, _default_factory=self.default_factory,
                  _type_=type_, _name=name, _env=env, _parent=parent, _root_name=root_name)
        return ret

    def create_vars(self, obj: Any, env: "BaseEnv", parent: Optional["BaseVar"]) -> List["Var"]:
        annotations = [c.__annotations__ for c in obj.__class__.__mro__ if hasattr(c, "__annotations__")]
        flat_annotations = {}
        ret = []
        for a in annotations:
            flat_annotations.update(a)

        for n in dir(obj):
            v = inspect.getattr_static(obj, n)

            if not isinstance(v, var):
                continue

            type_ = flat_annotations.get(n, None)

            optional = typing.get_origin(type_) is Union and type(None) in typing.get_args(type_)
            concrete = v.factory(type_=type_, name=n,
                                 env=env, parent=parent, root_name=self._root_name,
                                 optional=optional)
            ret.append(concrete)
            vars = v.create_vars(v, env, parent=concrete)

            for v in vars:
                object.__setattr__(concrete, v._name, v)

            concrete._vars.extend(vars)
            object.__setattr__(obj, n, concrete)
            ret.extend(vars)

        return ret


@dataclass(repr=False)
class Var(BaseVar):
    _default: VarType
    _default_factory: Optional[Callable]

    def __post_init__(self) -> None:
        if self._default_factory:
            self._default = self._default_factory()

        self._value = self._default

    def get_value(self) -> Any:
        return self._value

    def set_value(self, new_value) -> None:
        self._value = new_value
        return self._value

    def get_errors(self) -> List[ValidationError]:
        ret = []

        # Try evaluating value first. There might be some issues with that
        if not self._type_:
            return [NoTypeError(var_name=self.fullname)]

        if not self._optional and self.get_value() is None:
            ret.append(NoValueError(type_=self._type_, var_name=self.fullname))
        elif self.get_value() is not None:
            try:
                if self._type_ and not isinstance(self.get_value(), self._type_):
                    ret.append(
                        WrongTypeError(type_=self._type_, var_name=self.fullname, got_type=type(self.get_value())))
            except TypeError:
                # isinstance will fail for types like Union[] etc
                pass

        return super().get_errors() + ret


@dataclass(repr=False)
class ComputedVar(BaseVar):
    _fget: Callable
    _fset: Callable

    def get_value(self) -> Any:
        object.__setattr__(self, "_attr_hooks_enabled", False)
        ret = self._fget(self._env)
        object.__setattr__(self, "_attr_hooks_enabled", True)
        return ret

    def set_value(self, new_value) -> None:
        object.__setattr__(self, "_attr_hooks_enabled", False)
        self._fset(self._env, new_value)
        object.__setattr__(self, "_attr_hooks_enabled", True)

    def get_errors(self) -> List[ValidationError]:
        try:
            self.get_value()
        except Exception as e:
            return [ComputedVarError(var_name=self.fullname, exception=e)]

        return super().get_errors()


@dataclass
class computed_var(var):
    fget: Callable = None
    fset: Callable = None

    def factory(self, type_: Type, optional: bool, name: str, env: "BaseEnv", parent: "BaseVar", root_name: str) -> "BaseVar":
        ret = ComputedVar(_raw=self.raw, _optional=optional, _type_=type_, _name=name, _env=env, _parent=parent, _root_name=root_name,
                          _fget=self.fget, _fset=self.fset)
        return ret


@dataclass(repr=False)
class _VarGroup(BaseVar):
    _final: ClassVar[bool] = False

    def get_errors(self) -> List[ValidationError]:
        return super().get_errors()

    def get_value(self) -> Any:
        return self

    def set_value(self, new_value) -> None:
        pass


@dataclass
class VarGroup(var):
    fget: Callable = None
    fset: Callable = None

    def factory(self, type_: Type, optional: bool, name: str, env: "BaseEnv", parent: "BaseVar", root_name: str) -> "BaseVar":
        ret = _VarGroup(_raw=self.raw, _optional=False, _type_=type_, _name=name, _env=env, _parent=parent, _root_name=root_name)
        return ret
