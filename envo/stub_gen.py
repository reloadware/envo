import inspect

from pathlib import Path
from typing import TYPE_CHECKING, Dict, Any, Optional, Type, List, GenericMeta

from dataclasses import dataclass, fields

from envo.misc import render

if TYPE_CHECKING:
    from envo import Env


template = """
from pathlib import PosixPath, Path
import typing
import envo.env


class {{ ctx.env_name }}:
    class Meta:
        {% for f in ctx.meta -%}
            {{ f.name }}: {{ f.type }}
        {% endfor %}
        
    {% for f in ctx.fields -%}
        {{ f.name }}: {{ f.type }}
    {% endfor %}

"""


@dataclass
class Field:
    name: str
    type: str


@dataclass
class Ctx:
    env_name: str
    fields: List[Field]
    meta: List[Field]


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

        for p in env._parents:
            p_fields = self._annotations_for_obj(p)

            fields.extend(p_fields)

        ctx = Ctx(env_name=env.__class__.__name__,
                  fields=fields,
                  meta=meta)

        return ctx

    def _generate_env(self) -> None:
        ctx = self._ctx_from_env(self.env)

        file = Path(f"{str(self.env.root.absolute())}/env_{self.env.stage}.pyi")
        render(template, file, {"ctx": ctx})

    def _generate_parent(self, parent: Type["Env"]) -> None:
        ctx = self._ctx_from_env(parent)

        file = Path(f"{str(parent.Meta.root.absolute())}/env_{parent.Meta.stage}.pyi")
        render(template, file, {"ctx": ctx})

