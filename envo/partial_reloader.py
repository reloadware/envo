import inspect
import os
import sys
from copy import copy
from types import ModuleType

from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional, Type, Set

from envo import dependency_watcher
from envo.misc import import_from_file


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

        def __repr__(self) -> str:
            return f"Add: {repr(self.object)}"

    @dataclass
    class Update(Action):
        parent: Optional["ContainerObj"]
        old_object: "Object"
        new_object: Optional["Object"]

        def __repr__(self) -> str:
            return f"Update: {repr(self.old_object)}"

    @dataclass
    class Delete(Action):
        parent: Optional["ContainerObj"]
        object: "Object"

        def __repr__(self) -> str:
            return f"Delete: {repr(self.object)}"

        def execute(self) -> None:
            delattr(self.parent.python_obj, self.object.name)

    python_obj: Any
    reloader: "PartialReloader"
    name: str = ""
    module: Optional["Module"] = None
    parent: Optional["ContainerObj"] = None

    def get_actions_for_update(
        self, new_object: "Object"
    ) -> List["Action"]:
        raise NotImplementedError()

    @classmethod
    def get_actions_for_add(
        cls, reloader: "PartialReloader", parent: "Object", obj: "Object"
    ) -> List["Action"]:
        raise NotImplementedError()

    def get_actions_for_delete(
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        return [self.Delete(reloader=reloader, parent=parent, object=obj)]

    @property
    def full_name(self) -> str:
        return (
            f"{self.parent.full_name}.{self.name}"
            if self.parent and self.parent.name
            else self.name
        )

    @property
    def flat(self) -> Dict[str, Any]:
        return {self.full_name: self}

    def _is_ignored(self, name: str) -> bool:
        return name in [
            "__module__",
            "__file__",
            "__annotations__",
            "__doc__",
            "__weakref__",
            "__dict__",
            "__origin__",
            "None",
            "__dataclass_fields__",
        ]

    @property
    def source(self) -> str:
        try:
            ret = inspect.getsource(self.python_obj)
            ret = dedent(ret)
            return ret
        except (TypeError, OSError):
            return ""

    def get_parents_flat(self) -> List["Object"]:
        ret = []

        obj = self
        while obj.parent:
            ret.append(obj.parent)
            obj = obj.parent

        return ret

    def get_parents_obj_flat(self) -> List["Object"]:
        ret = [o.python_obj for o in self.get_parents_flat()]
        return ret

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
            self.old_object.get_func(
                self.old_object.python_obj
            ).__code__ = self.new_object.get_func(self.new_object.python_obj).__code__

    def get_actions_for_update(
        self, new_object: "Function", ignore_objects: Optional[List[Object]] = None
    ) -> List["Action"]:
        if self != new_object:
            return [
                self.Update(
                    reloader=self.reloader,
                    parent=self.parent,
                    old_object=self,
                    new_object=new_object,
                )
            ]
        else:
            return []

    @classmethod
    def get_actions_for_add(
        cls, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]

    def __eq__(self, other: "Function") -> bool:
        if self.python_obj.__class__ is not other.python_obj.__class__:
            return False

        compare_fields = [
            "co_argcount",
            "co_cellvars",
            "co_code",
            "co_consts",
            "co_flags",
            "co_freevars",
            "co_lnotab",
            "co_name",
            "co_names",
            "co_nlocals",
            "co_stacksize",
            "co_varnames",
        ]

        for f in compare_fields:
            if getattr(self.get_func(self.python_obj).__code__, f) != getattr(
                self.get_func(other.python_obj).__code__, f
            ):
                return False

        return True

    def __ne__(self, other: "Function") -> bool:
        return not (Function.__eq__(self, other))

    @property
    def source(self) -> str:
        try:
            ret = inspect.getsource(self.get_func(self.python_obj))
            ret = dedent(ret)
        except (TypeError, OSError):
            return ""

        if (
            isinstance(self.parent, Dictionary)
            and self.python_obj.__name__ == "<lambda>"
        ):
            ret = ret[ret.find(":") + 1 :]
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
        try:
            for n, o in self.get_dict().items():
                if self._is_ignored(n):
                    continue

                if any(o is p for p in self.get_parents_obj_flat() + [self.python_obj]):
                    continue

                if hasattr(o, "__module__") and o.__module__:
                    module_name = o.__module__.replace(".py", "").replace("/", ".").replace("\\", ".")
                    if not module_name.endswith(self.module.name):
                        continue

                obj_class: Type[Object]
                if inspect.ismethod(o) or inspect.ismethoddescriptor(o):
                    obj_class = Method
                elif inspect.isfunction(o):
                    obj_class = Function
                elif inspect.isclass(o):
                    obj_class = Class
                elif isinstance(o, dict):
                    obj_class = Dictionary
                elif inspect.ismodule(o):
                    obj_class = Import
                elif isinstance(self, Dictionary):
                    obj_class = DictionaryItem
                else:
                    obj_class = Variable

                self.children[n] = obj_class(
                    o, parent=self, name=n, reloader=self.reloader, module=self.module
                )
        except AttributeError as e :
            a =  1

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
    def get_actions_for_update(
        self, new_object: "Class"
    ) -> List["Action"]:
        return []

    def get_dict(self) -> Dict[str, Any]:
        ret = self.python_obj.__dict__
        return ret


@dataclass
class Dictionary(ContainerObj):
    class Add(ContainerObj.Add):
        def execute(self) -> None:
            setattr(self.parent.python_obj, self.object.name, self.object)

    def get_actions_for_update(
        self, new_object: "Class"
    ) -> List["Action"]:
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
            setattr(
                self.old_object.parent.python_obj,
                self.old_object.name,
                self.new_object.python_obj,
            )

    def get_actions_for_update(
        self, new_object: "Variable"
    ) -> List["Action"]:
        if self.python_obj == new_object.python_obj:
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                old_object=self,
                new_object=new_object,
            )
        ]

        for m in self.reloader.get_dependent_modules():
            module = Module(m, reloader=self.reloader)
            ret.extend(module.get_actions_for_update())

        return ret

    @classmethod
    def get_actions_for_add(
        cls, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]


@dataclass
class DictionaryItem(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            self.parent.python_obj[self.object.name] = copy(self.object.python_obj)

    class Update(FinalObj.Update):
        def execute(self) -> None:
            self.old_object.parent.python_obj[
                self.new_object.name
            ] = self.new_object.python_obj

    def get_actions_for_update(
        self, new_object: "Variable"
    ) -> List["Action"]:
        return [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                old_object=self,
                new_object=new_object,
            )
        ]

    @classmethod
    def get_actions_for_add(
        cls, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]


@dataclass
class Import(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            module = sys.modules.get(self.object.name, self.object.python_obj)
            setattr(self.parent.python_obj, self.object.name, module)

    def get_actions_for_update(
        self, new_object: "Variable"
    ) -> List["Action"]:
        return []

    @classmethod
    def get_actions_for_add(
        cls, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        return [cls.Add(reloader=reloader, parent=parent, object=obj)]


@dataclass
class Module(ContainerObj):
    @dataclass
    class Update(Action):
        module: "Module"

        def execute(self) -> None:
            reloader = PartialReloader(self.module.python_obj, self.reloader.root)
            reloader.run()

        def __repr__(self) -> str:
            return f"Update: {repr(self.module)}"

    def __post_init__(self) -> None:
        self.module = self
        super().__post_init__()

    def get_dict(self) -> Dict[str, Any]:
        return self.python_obj.__dict__

    def get_actions_for_update(self) -> List["Action"]:
        ret = [self.Update(self.reloader, self)]
        return ret

    def _is_ignored(self, name: str) -> bool:
        ignored = super()._is_ignored(name)
        if ignored:
            return True

        ret = name in ["__builtins__", "__name__", "__package__", "__cached__"]
        return ret

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
            ret.extend(
                o.get_actions_for_add(reloader=self.reloader, parent=parent, obj=o)
            )

        deleted_objects_names = a.keys() - b.keys()
        deleted_objects = {n: a[n] for n in deleted_objects_names}
        for o in deleted_objects.values():
            parent = a[o.parent.full_name]
            ret.extend(
                o.get_actions_for_delete(reloader=self.reloader, parent=parent, obj=o)
            )

        for n, o in a.items():
            # if deleted
            if n not in b:
                continue

            if o is self:
                continue

            ret.extend(o.get_actions_for_update(new_object=b[n]))

        return ret

    def __repr__(self) -> str:
        return f"Module: {self.python_obj.__name__}"


class PartialReloader:
    module_obj: Any

    def __init__(self, module_obj: Any, root: Path) -> None:
        self.root = root
        self.module_obj = module_obj

    def _is_user_module(self, module: Any):
        if not hasattr(module, "__file__"):
            return False

        ret = self.module_dir in Path(module.__file__).parents
        return ret

    @property
    def module_dir(self) -> Path:
        ret = Path(self.module_obj.__file__).parent
        return ret

    @property
    def source_files(self) -> List[str]:
        ret = [str(p) for p in self.module_dir.glob("**/*.py")]
        return ret

    def get_dependent_modules(self) -> List[ModuleType]:
        module_names = dependency_watcher.get_dependencies(self.module_obj)

        ret = []

        for n in module_names:
            module = sys.modules.get(n, None)
            if module:
                ret.append(module)

        return ret

    @property
    def old_module(self) -> Module:
        return Module(self.module_obj, reloader=self, name=f"{self.module_obj.__name__}")

    @property
    def new_module(self) -> Module:
        return Module(
            import_from_file(Path(self.module_obj.__file__), self.root),
            reloader=self,
            name=f"{self.module_obj.__name__}",
        )

    def get_actions(self) -> List[Action]:
        old_module = self.old_module
        new_module = self.new_module

        ret = old_module.get_actions(new_module)
        return ret

    def apply_actions(self, actions: List[Action]) -> None:
        for a in actions:
            a.execute()

    def run(self) -> List[Action]:
        """
        :return: True if succeded False i unable to reload
        """
        actions = self.get_actions()
        self.apply_actions(actions)
        return actions