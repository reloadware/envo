from envo import misc

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

from collections import defaultdict
from typing import List, Optional, Any, Dict

import sys


__all__ = ('enable', 'disable', 'get_dependencies')

_baseimport = builtins.__import__
_blacklist = None
_dependencies = defaultdict(list)
_parent = None

# PEP 328 changed the default level to 0 in Python 3.3.
_default_level = -1 if sys.version_info < (3, 3) else 0


def enable(blacklist=None) -> None:
    """Enable global module dependency tracking.

    A blacklist can be specified to exclude specific modules (and their import
    hierachies) from the reloading process.  The blacklist can be any iterable
    listing the fully-qualified names of modules that should be ignored.  Note
    that blacklisted modules will still appear in the dependency graph; they
    will just not be reloaded.
    """
    global _blacklist
    builtins.__import__ = _import
    if blacklist is not None:
        _blacklist = frozenset(blacklist)

def disable():
    """Disable global module dependency tracking."""
    global _blacklist, _parent
    builtins.__import__ = _baseimport
    _blacklist = None
    _dependencies.clear()
    _parent = None


def flatten(m, visited: Optional[List[str]] = None):
    if not visited:
        visited = []

    ret = _dependencies.get(misc.get_module_from_full_name(m).__name__, [])
    for v in visited:
        while v in ret: ret.remove(v)

    for mr in ret:
        visited.append(mr)
        flat = flatten(mr, visited.copy())
        for fm in flat:
            if fm in ret:
                continue
            ret.append(fm)

    return ret

def get_dependencies(m) -> List[Any]:
    """Get the dependency list for the given imported module."""
    flat = flatten(m.__name__)

    fixed_flat = []

    for m in flat:
        fixed = misc.get_module_from_full_name(m).__name__
        if fixed:
            fixed_flat.append(fixed)

    return fixed_flat

def _import(name, globals=None, locals=None, fromlist=None, level=_default_level):
    """__import__() replacement function that tracks module dependencies."""
    # Track our current parent module.  This is used to find our current place
    # in the dependency graph.
    global _parent
    parent = _parent
    if globals and "__package__" in globals and globals["__package__"]:
        _parent = (globals["__package__"] + "." + name)
    else:
        _parent = name

    add info about imported objects and stuff

    # Perform the actual import work using the base import function.
    base = _baseimport(name, globals, locals, fromlist, level)

    if base is not None and parent is not None:
        m = base

        # We manually walk through the imported hierarchy because the import
        # function only returns the top-level package reference for a nested
        # import statement (e.g. 'package' for `import package.module`) when
        # no fromlist has been specified.  It's possible that the package
        # might not have all of its descendents as attributes, in which case
        # we fall back to using the immediate ancestor of the module instead.
        if fromlist is None:
            for component in name.split('.')[1:]:
                try:
                    m = getattr(m, component)
                except AttributeError:
                    m = sys.modules[m.__name__ + '.' + component]

        # If this is a nested import for a reloadable (source-based) module,
        # we append ourself to our parent's dependency list.
        if hasattr(m, '__file__'):
            _dependencies[m.__name__].append(parent)

    # Lastly, we always restore our global _parent pointer.
    _parent = parent

    return base
