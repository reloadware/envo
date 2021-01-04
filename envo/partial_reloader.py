import builtins
import gc
import inspect
import os
import re
import sys
from copy import copy
from pathlib import Path
from textwrap import dedent
from types import ModuleType, FunctionType
from typing import Any, List, Callable, Type, Dict, Optional, Set

from dataclasses import dataclass, field
from nose.pyversion import ClassType

from envo.misc import import_from_file

from importlab import graph
from importlab import environment

dataclass = dataclass(repr=False)


class LoadError(Exception):
    pass


@dataclass
class Object:
    python_obj: Any
    reloader: "PartialReloader"
    name: str = ""
    module: Optional["Module"] = None
    parent: Optional["ContainerObj"] = None

    def get_actions_for_update(self, new_object: "Object", ignore_objects: Optional[List["Object"]] = None) -> List["Action"]:
        raise NotImplementedError()

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "Object", obj: "Object") -> List["Action"]:
        raise NotImplementedError()

    def get_actions_for_delete(self) -> List["Action"]:
        raise NotImplementedError()

    @property
    def full_name(self) -> str:
        return f"{self.parent.full_name}.{self.name}" if self.parent and self.parent.name else self.name

    @property
    def flat(self) -> Dict[str, Any]:
        return {self.full_name: self}

    def _is_ignored(self, name: str) -> bool:
        return name in ["__module__", "__annotations__", "__doc__", "__weakref__", "__dict__"]

    @property
    def source(self) -> str:
        try:
            ret = inspect.getsource(self.python_obj)
            ret = dedent(ret)
            return ret
        except (TypeError, OSError):
            return ""

    def __eq__(self, other: "Object") -> bool:
        return self.python_obj == other.python_obj

    def __ne__(self, other: "Object") -> bool:
        return self.python_obj != other.python_obj

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: {self.full_name}"


def compare_codes(left, right) -> bool:
    compare_fields = ["co_argcount", "co_cellvars", "co_code", "co_consts", "co_flags", "co_freevars",
                      "co_Kwanlyargcount", "co_lnotab", "co_name", "co_names", "co_nlocals", "co_stacksize", "co_varnames"]
    
    for f in compare_fields:
        if getattr(left, f) != getattr(right, f):
            return False

    return True


@dataclass
class Action:
    reloader: "PartialReloader"

    def execute(self) -> None:
        pass

    def __eq__(self, other: "Action") -> bool:
        raise NotImplementedError()


@dataclass
class Add(Action):
    parent: Object
    object: Object

    priority: int = 50

    def __eq__(self, other: "Add") -> bool:
        return id(self.parent) == id(other.parent) and id(self.object) == id(other.object) and self.priority == other.priority

    def __repr__(self) -> str:
        return f"Add: {repr(self.object)}"


@dataclass
class Update(Action):
    parent: Optional[Object]
    old_object: Object
    new_object: Optional[Object]

    priority: int = 50

    def __eq__(self, other: "Update") -> bool:
        return (id(self.parent) == id(other.parent) and
                id(self.old_object) == id(other.old_object) and
                id(self.new_object) == id(other.new_object) and
                self.priority == other.priority)

    def __repr__(self) -> str:
        return f"Update: {repr(self.old_object)}"


@dataclass
class Delete(Action):
    object: Object
    priority: int = 50


@dataclass
class FinalObj(Object):
    pass


@dataclass
class Function(FinalObj):
    class Add(Add):
        def execute(self) -> None:
            setattr(self.parent.python_obj, self.object.name, self.object.python_obj)

    class Update(Update):
        old_object: "Function"
        new_object: Optional["Function"]

        def execute(self) -> None:
            self.old_object.get_func(self.old_object.python_obj).__code__ = self.new_object.get_func(self.new_object.python_obj).__code__

    def get_actions_for_update(self, new_object: "Function", ignore_objects: Optional[List[Object]] = None) -> List["Action"]:
        if self != new_object:
            return [self.Update(reloader=self.reloader, parent=self.parent, old_object=self, new_object=new_object)]
        else:
            return []

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "Object", obj: "Object") -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]

    def get_actions_for_delete(self) -> List["Action"]:
        raise NotImplementedError()

    def __eq__(self, other: "ContainerObj") -> bool:
        if self.python_obj.__class__ is not other.python_obj.__class__:
            return False

        ret = self.get_func(self.python_obj).__code__ == self.get_func(other.python_obj).__code__
        return ret

    def __ne__(self, other: "Object") -> bool:
        if self.python_obj.__class__ is not other.python_obj.__class__:
            return True

        ret = self.get_func(self.python_obj).__code__ != self.get_func(other.python_obj).__code__
        return ret

    @property
    def source(self) -> str:
        try:
            ret = inspect.getsource(self.get_func(self.python_obj))
            ret = dedent(ret)
        except (TypeError, OSError):
            return ""

        if isinstance(self.parent, Dictionary) and self.python_obj.__name__ == "<lambda>":
            ret = ret[ret.find(":")+1:]
            ret = dedent(ret)

        return ret

    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj


@dataclass
class Method(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.__func__


@dataclass
class ContainerObj(Object):
    children: Dict[str, "Object"] = field(init=False, default_factory=dict)

    # def get_actions_for_update(self, new_object: "Function", ignore_objects: Optional[List[Object]] = None) -> List["Action"]:
    #     if not ignore_objects:
    #         ignore_objects = []
    #
    #     ret = []
    #
    #     for c in self.children.values():
    #         if ignore_objects and c.full_name in [o.full_name for o in ignore_objects]:
    #             continue
    #
    #         if isinstance(c, Import):
    #             continue
    #
    #         actions = c.get_actions_for_update(c, ignore_objects=[self] + ignore_objects)
    #         ret.extend(actions)
    #
    #     return ret

    def __post_init__(self) -> None:
        self._collect_objs()

    def get_dict(self) -> Dict[str, Any]:
        raise NotImplementedError()

    def _collect_objs(self) -> None:
        for n, o in self.get_dict().items():
            if self._is_ignored(n):
                continue

            if hasattr(o, "__module__") and o.__module__:
                if self.module.name not in o.__module__.replace(".py", "").replace("/", ".").replace("\\", "."):
                    continue

            Cls: Type[Object]
            if inspect.ismethod(o) or inspect.ismethoddescriptor(o):
                Cls = Method
            elif inspect.isfunction(o):
                Cls = Function
            elif inspect.isclass(o):
                Cls = Class
            elif isinstance(o, dict) or inspect.isgetsetdescriptor(o):
                Cls = Dictionary
            elif inspect.ismodule(o):
                Cls = Import
            elif isinstance(self, Dictionary):
                Cls = DictionaryItem
            else:
                Cls = GlobalVariable

            self.children[n] = Cls(o,parent=self, name=n, reloader=self.reloader, module=self.module)

    @property
    def flat(self) -> Dict[str, Object]:
        ret = {}
        for o in self.children.values():
            ret.update(o.flat)

        ret.update({self.full_name: self})

        return ret

    def get_functions(self) -> List[Function]:
        ret = [o for o in self.children if isinstance(o, Function)]
        return ret

    @property
    def source(self) -> str:
        ret = inspect.getsource(self.python_obj)
        for c in self.children.values():
            ret = ret.replace(c.source, "")

        return ret


@dataclass
class Class(ContainerObj):
    def get_actions_for_update(self, new_object: "Class", ignore_objects: Optional[List["Object"]] = None) -> List["Action"]:
        return []

    def get_dict(self) -> Dict[str, Any]:
        ret = dict(self.python_obj.__dict__)
        return ret


@dataclass
class Dictionary(ContainerObj):
    class Add(Add):
        def execute(self) -> None:
            setattr(self.parent.python_obj, self.object.name, self.object)

    def get_actions_for_update(self, new_object: "Class", ignore_objects: Optional[List["Object"]] = None) -> List["Action"]:
        return []

    def get_dict(self) -> Dict[str, Any]:
        return self.python_obj


@dataclass
class GlobalVariable(FinalObj):
    class Add(Add):
        def execute(self) -> None:
            self.parent.python_obj.__dict__[self.object.name] = copy(self.object.python_obj)

    class Update(Update):
        def execute(self) -> None:
            setattr(self.old_object.parent.python_obj, self.old_object.name, self.new_object.python_obj)

    def get_actions_for_update(self, new_object: "GlobalVariable", ignore_objects: Optional[List["Object"]] = None) -> List["Action"]:
        ret = [self.Update(reloader=self.reloader, parent=self.parent, old_object=self, new_object=new_object)]
        return ret

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "Object", obj: "Object") -> List["Action"]:
        return [GlobalVariable.Add(reloader=reloader, parent=parent, object=obj)]

    def get_actions_for_delete(self) -> List["Action"]:
        raise NotImplementedError()


@dataclass
class DictionaryItem(FinalObj):
    class Add(Add):
        def execute(self) -> None:
            self.parent.python_obj[self.object.name] = copy(self.object.python_obj)

    class Update(Update):
        def execute(self) -> None:
            self.old_object.parent.python_obj[self.new_object.name] = self.new_object.python_obj

    def get_actions_for_update(self, new_object: "GlobalVariable", ignore_objects: Optional[List["Object"]] = None) -> List["Action"]:
        return [DictionaryItem.Update(reloader=self.reloader, parent=self.parent, old_object=self, new_object=new_object)]

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "Object", obj: "Object") -> List["Action"]:
        return [GlobalVariable.Add(reloader=reloader, parent=parent, object=obj)]


@dataclass
class Import(FinalObj):
    class Add(Add):
        def execute(self) -> None:
            self.parent.python_obj[self.object.name] = copy(self.object.python_obj)

    def get_actions_for_update(self, new_object: "GlobalVariable", ignore_objects: Optional[List["Object"]] = None) -> List["Action"]:
        return []

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "Object", obj: "Object") -> List["Action"]:
        return [Import.Add(reloader=reloader, parent=parent, object=obj)]


@dataclass
class Module(ContainerObj):
    class Update(Update):
        def execute(self) -> None:
            pass

    def __post_init__(self) -> None:
        self.module = self
        super().__post_init__()

    def get_dict(self) -> Dict[str, Any]:
        return self.python_obj.__dict__

    def get_actions_for_update(self, new_object: "GlobalVariable", ignore_objects: Optional[List["Object"]] = None) -> List["Action"]:
        ret = []
        return ret

    def _is_ignored(self, name: str) -> bool:
        return name.startswith("__") and name.endswith("__")

    @property
    def final_objs(self) -> List[FinalObj]:
        """
        Return non container objects
        """
        ret = []
        for o in self.children:
            if not isinstance(o, FinalObj):
                continue
            ret.append(o)
        return ret

    @property
    def flat(self) -> Dict[str, Object]:
        ret = {self.name: self}
        for o in self.children.values():
            ret.update(o.flat)

        return ret

    def get_actions(self, obj: Object) -> List[Action]:
        ret = []

        a = self.flat
        b = obj.flat
        new_objects_names = b.keys() - a.keys()
        new_objects = {n: b[n] for n in new_objects_names}
        for o in new_objects.values():
            parent = a[o.parent.full_name]
            ret.extend(o.get_actions_for_add(reloader=self.reloader, parent=parent, obj=o))

        # deleted_objects_names = a.keys() - b.keys()
        # deleted_objects = {n: a[n] for n in deleted_objects_names}
        # ret.extend([Deleted(reloader=self.reloader) for o in deleted_objects.values()])

        for n, o in a.items():
            ret.extend(o.get_actions_for_update(new_object=b[n]))

        ret = sorted(ret, key=lambda x: x.priority, reverse=True)

        return ret

    def apply_actions(self, obj: Object) -> List[Action]:
        actions = self.get_actions(obj)
        for a in actions:
            a.execute()

        return actions

    def __repr__(self) -> str:
        return f"Module: {self.python_obj.__name__}"


class PartialReloader:
    module_obj: Any

    def __init__(self, module_obj: Any) -> None:
        self.module_obj = module_obj

    @property
    def old_module(self) -> Module:
        ret = Module(self.module_obj, reloader=self, name=f"{self.module_obj.__name__}")
        return ret

    @property
    def new_module(self) -> Module:
        ret = Module(import_from_file(self.module_obj.__file__), reloader=self, name=f"{self.module_obj.__name__}")
        return ret

    def run(self) -> List[Action]:
        """
        :return: True if succeded False i unable to reload
        """

        old_module = self.old_module
        new_module = self.new_module

        actions = old_module.apply_actions(new_module)
        return actions
