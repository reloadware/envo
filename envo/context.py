import inspect
import os
from copy import copy, deepcopy
from dataclasses import dataclass
from getpass import getpass
from typing import Any, Callable, List, Optional, TypeVar, cast

import envium.environ
from envium.environ import Var, VarGroup

from envo import CommandError, inject, run, run_get

__all__ = ["secret_var", "ctx_var", "Ctx", "SecretsGroup", "CtxGroup"]


VarType = TypeVar("VarType")


class CtxVar(Var[TypeVar]):
    pass


def ctx_var(
    default: Optional[VarType] = None,
    default_factory: Optional[Callable] = None,
) -> Any:
    return CtxVar(default=default, default_factory=default_factory)


class SecretVar(CtxVar):
    def __init__(
        self,
        default: Optional[VarType] = None,
        default_factory: Optional[Callable] = None,
        value_from_input: bool = True,
    ) -> None:
        super().__init__(default=default, default_factory=default_factory)
        self._value_from_input = value_from_input


def secret_var(default: Optional[VarType] = None, default_factory: Optional[Callable] = None) -> Any:
    return SecretVar(default=default, default_factory=default_factory)


class WrongTypeError(envium.environ.WrongTypeError):
    pass


class NoTypeError(envium.environ.NoTypeError):
    pass


class NoValueError(envium.environ.NoValueError):
    pass


class ValidationErrors(envium.environ.ValidationErrors):
    pass


class CtxGroup(VarGroup):
    pass


class Ctx(CtxGroup):
    def __init__(self, name: str) -> None:
        super().__init__(load=False, name=name)
        self._root = self
        self._process()

    @property
    def _fullname(self) -> str:
        return self._name

    @property
    def _errors(self) -> List[envium.environ.EnviumError]:
        envium_errors = super()._errors

        ret = []
        for e in envium_errors:
            if isinstance(e, envium.environ.NoValueError):
                ret.append(NoValueError(var_name=e.var_name, type_=e.type_))

            if isinstance(e, envium.environ.NoTypeError):
                ret.append(NoTypeError(var_name=e.var_name))

            if isinstance(e, envium.environ.WrongTypeError):
                ret.append(WrongTypeError(var_name=e.var_name, type_=e.type_, got_type=e.got_type))

        return ret

    def _validate(self) -> None:
        try:
            super()._validate()
        except envium.environ.ValidationErrors:
            raise ValidationErrors(self._errors)


class SecretsGroup(VarGroup):
    pass


class Secrets(Ctx):
    def __init__(self, name: str) -> None:
        super().__init__(name)

        self._get_secrets_from_input()

    @property
    def _flat(self) -> List[SecretVar]:
        return cast(List[SecretVar], super()._flat)

    def _get_secrets_from_input(self) -> None:
        for s in self._flat:
            if s._value_from_input:
                value = getpass(f"{s._fullname}: ")
                s._value = value
