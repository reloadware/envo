import builtins
import gc
import inspect
import os
import sys
from copy import copy
from pathlib import Path
from types import ModuleType, FunctionType
from typing import Any, List, Callable, Type, Dict, Optional, Set

from dataclasses import dataclass, field
from nose.pyversion import ClassType

from envo.misc import import_from_file

from importlab import graph
from importlab import environment

dataclass = dataclass(repr=False)


@dataclass
class Object:
    python_obj: Any
    reloader: "PartialReloader"
    name: str = ""
    parent: Optional["Object"] = None

    def get_actions_for_update(self, new_object: "Object") -> List["Action"]:
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
        return False

    @property
    def source(self) -> str:
        try:
            return inspect.getsource(self.python_obj)
        except (TypeError, OSError):
            return ""

    def __eq__(self, other: "Object") -> bool:
        return self.python_obj == other.python_obj

    def __ne__(self, other: "Object") -> bool:
        return self.python_obj != other.python_obj

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: {self.full_name}"


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
            exec(self.object.source, self.parent.python_obj.__dict__)

    class Update(Update):
        def execute(self) -> None:
            old_fun = self.old_object.python_obj
            exec(self.new_object.source, self.old_object.parent.python_obj.__dict__)

            old_fun.__code__ = self.old_object.parent.python_obj.__dict__[self.old_object.name].__code__
            self.old_object.parent.python_obj.__dict__[self.old_object.name] = old_fun

    def get_actions_for_update(self, new_object: "Function") -> List["Action"]:
        return [Function.Update(reloader=self.reloader, parent=self.parent, old_object=self, new_object=new_object)]

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "Object", obj: "Object") -> List["Action"]:
        return [Function.Add(reloader=reloader, parent=parent, object=obj)]

    def get_actions_for_delete(self) -> List["Action"]:
        raise NotImplementedError()

    def __eq__(self, other: "ContainerObj") -> bool:
        return self.python_obj.__code__ == other.python_obj.__code__

    def __ne__(self, other: "Object") -> bool:
        return self.python_obj.__code__ != other.python_obj.__code__


@dataclass
class ContainerObj(Object):
    children: Dict[str, "Object"] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._collect_objs()

    def _collect_objs(self) -> None:
        for n, o in self.python_obj.__dict__.items():
            if self._is_ignored(n):
                continue

            Cls: Type[Object]
            if inspect.isfunction(o):
                Cls = Function
            elif inspect.isclass(o):
                Cls = Class
            elif isinstance(o, dict):
                Cls = Dictionary
            elif inspect.ismodule(o):
                Cls = Import
            else:
                Cls = GlobalVariable

            self.children[n] = Cls(o,parent=self, name=n, reloader=self.reloader)

    def __eq__(self, other: "ContainerObj") -> bool:
        return self.source == other.source

    def __ne__(self, other: "Object") -> bool:
        return self.source != other.source

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


@dataclass
class Class(ContainerObj):
    pass


@dataclass
class Dictionary(FinalObj):
    pass


@dataclass
class GlobalVariable(FinalObj):
    class Add(Add):
        def execute(self) -> None:
            self.parent.python_obj.__dict__[self.object.name] = copy(self.object.python_obj)

    def get_actions_for_update(self, new_object: "Function") -> List["Action"]:
        assert isinstance(self.parent, Module)

        ret = []

        ret.extend(self.parent.get_actions_for_update(self.parent))

        for m in self.reloader.get_dependent_modules(self.parent):
            ret.extend(m.get_actions_for_update(m))
            for c in m.children.values():
                if c.full_name == self.full_name:
                    continue

                if isinstance(c, Import) or isinstance(c, Class):
                    continue

                actions = c.get_actions_for_update(c)
                ret.extend(actions)

        for a in ret:
            a.priority = 100

        # remove duplicates
        ret_tmp = []
        for a in reversed(ret):
            if a not in ret_tmp:
                ret_tmp.append(a)

        ret = list(reversed(ret_tmp))

        return ret

    @classmethod
    def get_actions_for_add(cls, reloader: "PartialReloader", parent: "Object", obj: "Object") -> List["Action"]:
        return [GlobalVariable.Add(reloader=reloader, parent=parent, object=obj)]

    def get_actions_for_delete(self) -> List["Action"]:
        raise NotImplementedError()


@dataclass
class Import(FinalObj):
    pass


@dataclass
class Module(ContainerObj):
    class Update(Update):
        def execute(self) -> None:
            exec(self.old_object.source, self.old_object.python_obj.__dict__)

    def get_actions_for_update(self, new_object: "Module") -> List["Action"]:
        return [Module.Update(reloader=self.reloader, parent=None, old_object=self, new_object=None)]

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
        ret = {}
        for o in self.children.values():
            ret.update(o.flat)

        return ret

    @property
    def source(self) -> str:
        ret = inspect.getsource(self.python_obj)
        for c in self.children.values():
            ret = ret.replace(c.source, "")

        return ret

    def get_actions(self, obj: Object) -> List[Action]:
        ret = []

        a = self.flat
        b = obj.flat
        new_objects_names = b.keys() - a.keys()
        new_objects = {n: b[n] for n in new_objects_names}
        for o in new_objects.values():
            ret.extend(o.get_actions_for_add(reloader=self.reloader, parent=self, obj=o))

        # deleted_objects_names = a.keys() - b.keys()
        # deleted_objects = {n: a[n] for n in deleted_objects_names}
        # ret.extend([Deleted(reloader=self.reloader) for o in deleted_objects.values()])

        for n, o in a.items():
            if o != b[n]:
                ret.extend(o.get_actions_for_update(new_object=b[n]))

        ret = sorted(ret, key=lambda x: x.priority, reverse=True)

        return ret

    def apply_actions(self, obj: Object) -> None:
        actions = self.get_actions(obj)
        for a in actions:
            a.execute()

    def __repr__(self) -> str:
        return f"Module: {self.python_obj.__name__}"


class Cache:
    non_user_modules: Set[str] = []

    def init(self, reloader: "PartialReloader") -> None:
        if self.non_user_modules:
            return

        user_modules = reloader.user_modules
        user_modules_objs = [m.python_obj for m in user_modules.values()]

        self.non_user_modules = set(n for n, m in sys.modules.items() if m not in user_modules_objs)


class PartialReloader:
    module_obj: Any
    cache = Cache()

    def __init__(self, module_obj: Any, source_dirs: List[Path]) -> None:
        self.source_dirs = source_dirs
        self.module_obj = module_obj

        self.user_modules = self._get_user_modules()

        self.cache.init(self)

    def _is_user_module(self, module: Any):
        if not hasattr(module, "__file__"):
            return False

        ret = any(p in Path(module.__file__).parents for p in self.source_dirs)
        return ret

    def _get_user_modules(self) -> Dict[str, Module]:
        ret = {}

        modules_to_search = sys.modules.keys() - self.cache.non_user_modules

        for n in modules_to_search:
            m = sys.modules[n]
            if not self._is_user_module(m):
                continue
            ret[m.__file__] = Module(m, reloader=self, name=n)

        return ret

    @property
    def source_files(self) -> List[str]:
        ret = []
        for d in self.source_dirs:
            ret.extend([str(p) for p in d.glob("*.py")])
        return ret

    def get_dependent_modules(self, module: Module) -> List[Module]:
        env = environment.Environment(path=environment.path_from_pythonpath(os.environ["PYTHONPATH"]),
                                      python_version=sys.version_info[0:2])
        g = graph.ImportGraph.create(env, self.source_files)
        all_pred = dict(g.graph.pred)
        pred = all_pred[module.python_obj.__file__]

        def flatten(graph_pred) -> List[str]:
            ret = []

            for p in graph_pred:
                ret.append(p)
                ret.extend(flatten(all_pred[p]))

            # remove duplicates
            for p in set(ret):
                while ret.count(p) > 1:
                    ret.remove(p)

            return ret

        flat_graph = flatten(pred)
        user_modules = self.user_modules

        modules = [user_modules[m] for m in flat_graph]
        return modules

    @property
    def old_module(self) -> Module:
        ret = Module(self.module_obj, reloader=self, name=f"{self.module_obj.__name__}")
        return ret

    @property
    def new_module(self) -> Module:
        ret = Module(import_from_file(self.module_obj.__file__), reloader=self, name=f"{self.module_obj.__name__}")
        return ret

    def run(self) -> bool:
        """
        :return: True if succeded False i unable to reload
        """

        old_module = self.old_module
        new_module = self.new_module

        old_module.apply_actions(new_module)
        pass
