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



@dataclass
class Action:
    reloader: "PartialReloader"

    def execute(self) -> None:
        pass

    def __eq__(self, other: "Action") -> bool:
        raise NotImplementedError()



@dataclass
class Object:
    @dataclass
    class Add(Action):
        parent: "ContainerObj"
        object: "Object"

        priority: int = 50

        def __repr__(self) -> str:
            return f"Add: {repr(self.object)}"

    @dataclass
    class Update(Action):
        parent: Optional["ContainerObj"]
        old_object: "Object"
        new_object: Optional["Object"]

        priority: int = 50

        def __repr__(self) -> str:
            return f"Update: {repr(self.old_object)}"

    @dataclass
    class Delete(Action):
        parent: Optional["ContainerObj"]
        object: "Object"

        priority: int = 50

        def __repr__(self) -> str:
            return f"Delete: {repr(self.object)}"

        def execute(self) -> None:
            delattr(self.parent.python_obj, self.object.name)

    python_obj: Any
    reloader: "PartialReloader"
    name: str = ""
    module: Optional["Module"] = None
    parent: Optional["ContainerObj"] = None

    def get_actions_for_update(self, new_object: "Object", ignore_objects: Optional[List["Object"]] = None) -> List[
        "Action"]:
        raise NotImplementedError()

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "Object", obj: "Object") -> List["Action"]:
        raise NotImplementedError()

    def get_actions_for_delete(self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object") -> List[
        "Action"]:
        return [self.Delete(reloader=reloader, parent=parent, object=obj)]

    @property
    def full_name(self) -> str:
        return f"{self.parent.full_name}.{self.name}" if self.parent and self.parent.name else self.name

    @property
    def flat(self) -> Dict[str, Any]:
        return {self.full_name: self}

    def _is_ignored(self, name: str) -> bool:
        return name in ["__module__", "__annotations__", "__doc__", "__weakref__", "__dict__", "__origin__", "None",
                        "__dataclass_fields__"]

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


@dataclass
class FinalObj(Object):
    pass


@dataclass
class Function(FinalObj):
    class Add(FinalObj.Add):
        object: "Function"

        def execute(self) -> None:
            setattr(self.parent.python_obj, self.object.name, self.object.python_obj)

    class Update(FinalObj.Update):
        old_object: "Function"
        new_object: Optional["Function"]

        def execute(self) -> None:
            self.old_object.get_func(self.old_object.python_obj).__code__ = self.new_object.get_func(
                self.new_object.python_obj).__code__

    def get_actions_for_update(self, new_object: "Function", ignore_objects: Optional[List[Object]] = None) -> List[
        "Action"]:
        if self != new_object:
            return [self.Update(reloader=self.reloader, parent=self.parent, old_object=self, new_object=new_object)]
        else:
            return []

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object") -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]

    def __eq__(self, other: "Function") -> bool:
        if self.python_obj.__class__ is not other.python_obj.__class__:
            return False

        compare_fields = ["co_argcount", "co_cellvars", "co_code", "co_consts", "co_flags", "co_freevars",
                          "co_lnotab", "co_name", "co_names", "co_nlocals", "co_stacksize",
                          "co_varnames"]

        for f in compare_fields:
            if getattr(self.python_obj.__code__, f) != getattr(other.python_obj.__code__, f):
                return False

        return True

    def __ne__(self, other: "Object") -> bool:
        return not (self == other)

    @property
    def source(self) -> str:
        try:
            ret = inspect.getsource(self.get_func(self.python_obj))
            ret = dedent(ret)
        except (TypeError, OSError):
            return ""

        if isinstance(self.parent, Dictionary) and self.python_obj.__name__ == "<lambda>":
            ret = ret[ret.find(":") + 1:]
            ret = dedent(ret)

        return ret

    def is_global(self) -> bool:
        ret = self.parent == self.module
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

    def __post_init__(self) -> None:
        self._collect_objs()

    def get_dict(self) -> Dict[str, Any]:
        raise NotImplementedError()

    def _collect_objs(self) -> None:
        for n, o in self.get_dict().items():
            if self._is_ignored(n):
                continue

            # break recursion (todo: check deeper)
            if self.parent and self.python_obj is self.parent.python_obj:
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
                Cls = Variable

            self.children[n] = Cls(o, parent=self, name=n, reloader=self.reloader, module=self.module)

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

    def get_functions_recursive(self) -> List[Function]:
        ret = [o for o in self.flat.values() if isinstance(o, Function)]
        return ret

    @property
    def source(self) -> str:
        ret = inspect.getsource(self.python_obj)
        for c in self.children.values():
            ret = ret.replace(c.source, "")

        return ret


@dataclass
class Class(ContainerObj):
    def get_actions_for_update(self, new_object: "Class", ignore_objects: Optional[List["Object"]] = None) -> List[
        "Action"]:
        return []

    def get_dict(self) -> Dict[str, Any]:
        ret = self.python_obj.__dict__
        return ret


@dataclass
class Dictionary(ContainerObj):
    class Add(ContainerObj.Add):
        def execute(self) -> None:
            setattr(self.parent.python_obj, self.object.name, self.object)

    def get_actions_for_update(self, new_object: "Class", ignore_objects: Optional[List["Object"]] = None) -> List[
        "Action"]:
        return []

    def get_dict(self) -> Dict[str, Any]:
        return self.python_obj


@dataclass
class Variable(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            setattr(self.parent.python_obj, self.object.name, self.object.python_obj)

    class Update(FinalObj.Update):
        def execute(self) -> None:
            setattr(self.old_object.parent.python_obj, self.old_object.name, self.new_object.python_obj)

    def get_actions_for_update(self, new_object: "Variable", ignore_objects: Optional[List["Object"]] = None) -> \
    List["Action"]:
        ret = [self.Update(reloader=self.reloader, parent=self.parent, old_object=self, new_object=new_object)]
        return ret

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object") -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]


@dataclass
class DictionaryItem(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            self.parent.python_obj[self.object.name] = copy(self.object.python_obj)

    class Update(FinalObj.Update):
        def execute(self) -> None:
            self.old_object.parent.python_obj[self.new_object.name] = self.new_object.python_obj

    def get_actions_for_update(self, new_object: "Variable", ignore_objects: Optional[List["Object"]] = None) -> \
    List["Action"]:
        return [
            self.Update(reloader=self.reloader, parent=self.parent, old_object=self, new_object=new_object)]

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object") -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]


@dataclass
class Import(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            self.parent.python_obj[self.object.name] = copy(self.object.python_obj)

    def get_actions_for_update(self, new_object: "Variable", ignore_objects: Optional[List["Object"]] = None) -> \
    List["Action"]:
        return []

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object") -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]


@dataclass
class Module(ContainerObj):
    def __post_init__(self) -> None:
        self.module = self
        super().__post_init__()

    def get_dict(self) -> Dict[str, Any]:
        return self.python_obj.__dict__

    def get_actions_for_update(self, new_object: "Variable", ignore_objects: Optional[List["Object"]] = None) -> \
    List["Action"]:
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

        deleted_objects_names = a.keys() - b.keys()
        deleted_objects = {n: a[n] for n in deleted_objects_names}
        for o in deleted_objects.values():
            parent = a[o.parent.full_name]
            ret.extend(o.get_actions_for_delete(reloader=self.reloader, parent=parent, obj=o))

        for n, o in a.items():
            # if deleted
            if not n in b:
                continue

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