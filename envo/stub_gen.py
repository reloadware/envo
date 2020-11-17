import inspect
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, GenericMeta, List, Optional, Type

from envo.env import MagicFunction
from envo.misc import render

if TYPE_CHECKING:
    from envo import Env


template = """
from pathlib import PosixPath, Path
import typing
from typing import Dict, Any, List, Type, Optional
import envo.env

from envo import (  # noqa: F401
    logger,
    command,
    context,
    Raw,
    run,
    precmd,
    onstdout,
    onstderr,
    postcmd,
    onload,
    oncreate,
    onunload,
    ondestroy,
    dataclass,
    Plugin,
    VirtualEnv,
)

from envo.env import (
MagicFunction
)

from envo.misc import Inotify


class {{ ctx.env_name }}:
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


@dataclass
class Method:
    name: str
    header: str = field(init=False)
    source: str

    def __post_init__(self) -> None:
        self.header = re.findall(r"(?:@.+?)?def .*?\).*?:", self.source, re.DOTALL)[0]

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass
class Ctx:
    env_name: str
    fields: List[Field]
    meta: List[Field]
    methods: List[Method]


class StubGen:
    env: "Env"

    def __init__(self, env: "Env"):
        self.env = env

    def generate(self) -> None:
        self._generate_env()
        for p in self.env._parents:
            self._generate_parent(p)

    def _annotations_for_obj(self, obj: Any) -> List[Field]:
        fields = []
        if not hasattr(obj, "__annotations__"):
            return []

        for n, a in obj.__annotations__.items():
            if n.startswith("_"):
                continue

            type_ = a if isinstance(a, GenericMeta) else a.__name__

            f = Field(n, type_)
            fields.append(f)

        return fields

    def _ctx_from_env(self, env: "Env") -> Ctx:
        fields = self._annotations_for_obj(env)
        meta = self._annotations_for_obj(env.Meta)

        for p in self.env.__class__.mro():
            p_fields = self._annotations_for_obj(p)

            fields.extend(p_fields)

        fields = list(set(fields))
        fields.sort(key=lambda x: x.name)

        meta = list(set(meta))
        meta.sort(key=lambda x: x.name)

        # collect methods
        methods: List[Method] = []
        for n, o in inspect.getmembers(self.env):
            if not inspect.ismethod(o):
                continue

            if n.startswith("__"):
                continue

            methods.append(Method(name=n, source=inspect.getsource(o)))

        # collect magic functions
        for n, o in inspect.getmembers(self.env):
            if not isinstance(o, MagicFunction):
                continue

            if n.startswith("__"):
                continue

            methods.append(Method(name=n, source=inspect.getsource(o.func)))

        methods = list(set(methods))
        methods.sort(key=lambda x: x.name)

        ctx = Ctx(env_name=env.__class__.__name__,
                  fields=fields,
                  meta=meta,
                  methods=methods)

        return ctx

    def _generate_env(self) -> None:
        ctx = self._ctx_from_env(self.env)

        file = Path(f"{str(self.env.root.absolute())}/env_{self.env.stage}.pyi")
        render(template, file, {"ctx": ctx})

    def _generate_parent(self, parent: Type["Env"]) -> None:
        ctx = self._ctx_from_env(parent)

        file = Path(f"{str(parent.Meta.root.absolute())}/env_{parent.Meta.stage}.pyi")
        render(template, file, {"ctx": ctx})

