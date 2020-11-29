import inspect
import re

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, GenericMeta, List, Optional, Type

from envo.env import MagicFunction, magic_function, BaseEnv

from envo import misc

if TYPE_CHECKING:
    from envo import Env

template = """
import typing

from envo.env import (
MagicFunction,
Env
)
{{ ctx.prologue }}
class {{ ctx.env_name }}(Env):
    class Meta:
        {% for f in ctx.meta -%}
            {{ f.name }}: {{ f.type }}
        {% endfor %}
        
    {% for f in ctx.fields -%}
        {{ f.name }}: {{ f.type }}
    {% endfor %}
    {% for method in ctx.methods -%} 
    {{ method.header }} ... 
    {% endfor -%}

"""


@dataclass
class Field:
    name: str
    type: str

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other) -> bool:
        return self.name == other.name


@dataclass
class Method:
    name: str
    header: str = field(init=False)
    source: str

    def __post_init__(self) -> None:
        self.header = re.findall(r"(?:@.+?)?def .*?\).*?:", self.source, re.DOTALL)[0]

    def __hash__(self) -> int:
        return hash(self.header)

    def __eq__(self, other) -> bool:
        return self.header == other.header


@dataclass
class Ctx:
    env_name: str
    fields: List[Field]
    meta: List[Field]
    methods: List[Method]
    prologue: str


class StubGen:
    env: "Env"

    def __init__(self, env: "Env"):
        self.env = env

    def generate(self) -> None:
        self._generate_env()
        for p in self.env.get_user_envs():
            self._generate_parent(p)

    def _get_fields_for_obj(self, obj: Type["Env"]) -> List[Field]:
        fields = []
        if not hasattr(obj, "__annotations__"):
            return []

        annotations = obj.__annotations__.copy()

        for p in obj.__mro__:
            if not hasattr(p, "__annotations__"):
                continue

            p_a = p.__annotations__

            for k, v in p_a.items():
                if k.startswith("_"):
                    annotations.pop(k, None)
                    continue

                if k not in annotations:
                    annotations[k] = v

        for n, a in annotations.items():
            # Handle Raw and other types
            if isinstance(a, GenericMeta) or not hasattr(a, "__name__"):
                type_ = str(a)
            else:
                type_ = a.__name__

            f = Field(n, type_)
            fields.append(f)

        return fields

    def _is_envo_code(self, obj: Any):
        ret = "envo." in obj.__module__
        return ret

    def _ctx_from_env(self, env: Type["Env"]) -> Optional[Ctx]:
        user_env_class = next((c for c in env.__mro__ if issubclass(c, BaseEnv) and c.is_user_env()), None)
        if not user_env_class:
            return None

        fields = self._get_fields_for_obj(env)
        meta = self._get_fields_for_obj(env.Meta)
        methods: List[Method] = []

        imports_src = Path(user_env_class.__module__).read_text()
        prologue = re.search(r"(.*?)(?:\nclass)", imports_src, re.DOTALL)[1]

        for p in env.__mro__:
            if not issubclass(p, BaseEnv):
                continue

            if not p.is_user_env():
                continue

            # collect methods
            for n, o in inspect.getmembers(p):
                if not inspect.isfunction(o):
                    continue

                if (o.__module__ != env.__module__ or self._is_envo_code(o)) and n.startswith("_"):
                    continue

                if isinstance(o, magic_function):
                    continue

                methods.append(Method(name=n, source=inspect.getsource(o)))

            # collect magic functions
            for n, o in inspect.getmembers(p):
                if not isinstance(o, MagicFunction):
                    continue

                func = o.func

                if (func.__module__ != env.__module__ or self._is_envo_code(func)) and n.startswith("_"):
                    continue

                methods.append(Method(name=n, source=inspect.getsource(o.func)))

        fields = list(set(fields))
        fields.sort(key=lambda x: x.name)

        meta = list(set(meta))
        meta.sort(key=lambda x: x.name)

        methods = list(set(methods))
        methods.sort(key=lambda x: x.name)

        ctx = Ctx(env_name=env.__name__,
                  fields=fields,
                  meta=meta,
                  methods=methods,
                  prologue=prologue)

        return ctx

    def _generate_env(self) -> None:
        ctx = self._ctx_from_env(self.env.__class__)

        if not ctx:
            return

        file = Path(f"{str(self.env.root.absolute())}/env_{self.env.stage}.pyi")
        misc.render(template, file, {"ctx": ctx})

    def _generate_parent(self, parent: Type["BaseEnv"]) -> None:
        ctx = self._ctx_from_env(parent)

        file = Path(f"{str(parent.Meta.root.absolute())}/env_{parent.Meta.stage}.pyi")
        misc.render(template, file, {"ctx": ctx})
