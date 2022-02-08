import errno
import importlib.machinery
import importlib.util
import os
import re
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from types import FrameType
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

from globmatch import glob_match
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

__all__ = [
    "dir_name_to_class_name",
    "render_py_file",
    "render_file",
    "import_from_file",
    "EnvoError",
    "Callback",
    "FilesWatcher",
    "colored",
]

from envo import const
from envo.logs import logger


class EnvoError(Exception):
    pass


class Callback:
    def __init__(self, func: Optional[Callable[..., Any]] = None) -> None:
        self.func = func

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if not self.func:
            return
        return self.func(*args, **kwargs)

    def __bool__(self) -> bool:
        return self.func is not None


class InotifyPath:
    def __init__(self, raw_path: Path, root: Path) -> None:
        self.absolute = raw_path.absolute()
        self.relative = self.absolute.relative_to(root)
        self.relative_str = str(self.relative)

        if self.relative.is_dir():
            self.relative_str += "/"

    def match(self, include: List[str], exclude: List[str]) -> bool:
        return not glob_match(self.relative_str, exclude) and glob_match(self.relative_str, include)

    def is_dir(self) -> bool:
        return self.absolute.is_dir()


class EventDispatcher(FileSystemEventHandler):
    observer: Observer
    watchers: List["FilesWatcher"]
    paths: List[Path]

    def __init__(self) -> None:
        self.observer = Observer()
        self.observer.start()
        self.paths = []
        self.watchers = []

    def add(self, watcher: "FilesWatcher") -> None:
        self.watchers.append(watcher)

        for p in watcher.paths:
            if p not in self.paths:
                self.observer.schedule(self, str(p), recursive=False)
                self.paths.append(p)

    def flush(self) -> None:
        self.observer.event_queue.queue.clear()

    def remove(self, watcher: "FilesWatcher") -> None:
        for i, w in enumerate(self.watchers):
            if w is watcher:
                self.watchers.pop(i)
                return

    def on_any_event(self, event: FileSystemEvent):
        for w in self.watchers.copy():
            try:
                relative = Path(event.src_path).relative_to(w.root)
            except ValueError:
                continue
            if w.match(relative):
                w.on_any_event(event)


event_dispatcher = EventDispatcher()


class FilesWatcher:
    @dataclass
    class Sets:
        include: List[str]
        exclude: List[str]
        root: Path
        name: str = "Anonymous"

    @dataclass
    class Callbacks:
        on_event: Callback

    paths: List[Path]

    def __init__(self, se: Sets, calls: Callbacks):
        self.include = [p.lstrip("./") for p in se.include]
        self.exclude = [p.lstrip("./") for p in se.exclude]
        self.root = se.root

        super().__init__()
        self.se = se
        self.calls = calls

        self.paths = []
        self.enabled = True

        for p in self.se.include:
            path = (self.se.root / p).parent
            if not path.exists():
                continue

            if path not in self.paths:
                self.paths.append(path)

        if self.se.root not in self.paths:
            self.paths.append(self.se.root)

        event_dispatcher.add(self)

    def on_any_event(self, event: FileSystemEvent):
        if not self.enabled:
            return
        self.calls.on_event(event)

    def match(self, path: Path) -> bool:
        return not glob_match(str(path), self.exclude) and glob_match(str(path), self.include)

    def stop(self) -> None:
        self.enabled = False
        event_dispatcher.remove(self)


def dir_name_to_class_name(dir_name: str) -> str:
    class_name = dir_name.replace("_", " ")
    class_name = class_name.replace("-", " ")
    class_name = class_name.replace(".", " ")
    s: str
    class_name = "".join([s.strip().capitalize() for s in class_name.split()])

    return class_name


def dir_name_to_pkg_name(dir_name: str) -> str:
    pkg_name = dir_name.replace("_", " ")
    class_name = pkg_name.replace("-", " ")
    class_name = class_name.replace(".", " ")
    s: str
    class_name = "_".join([s.strip() for s in class_name.split()])

    return class_name


def is_valid_module_name(module: str) -> bool:
    from keyword import iskeyword

    return module.isidentifier() and not iskeyword(module)


def render_file(template_path: Path, output: Path, context: Dict[str, Any]) -> None:
    content = template_path.read_text()
    for n, v in context.items():
        content = content.replace(f"{{{{ {n} }}}}", v)

    output.write_text(content, encoding="utf-8")


def render_py_file(template_path: Path, output: Path, context: Dict[str, Any]) -> None:
    render_file(template_path, output, context)


def path_to_module_name(path: Path, package_root: Path) -> str:
    rel_path = path.resolve().absolute().relative_to(package_root.resolve())
    ret = str(rel_path).replace(".py", "").replace("/", ".").replace("\\", ".")
    ret = ret.replace(".__init__", "")
    return ret


def import_from_file(path: Union[Path, str]) -> Any:
    path = Path(path)
    loader = importlib.machinery.SourceFileLoader(str(path), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    return module


def import_env_from_file(path: Union[Path, str]) -> Any:
    # Ensure all env modules are reloaded
    for n, m in sys.modules.copy().items():
        if not hasattr(m, "__file__"):
            continue
        if not m.__file__:
            continue
        # Check if it's env file
        if not Path(m.__file__).name.startswith("env_"):
            continue

        del sys.modules[n]

    ret = import_from_file(path)

    return ret


def get_module_from_full_name(full_name: str) -> Optional[str]:
    parts = full_name.split(".")

    while True:
        module_name = ".".join(parts)
        if module_name in sys.modules:
            return module_name
        parts.pop(0)
        if not parts:
            return None


def get_envo_relevant_traceback(exc: BaseException) -> List[str]:
    if isinstance(exc, EnvoError):
        msg = str(exc).splitlines(keepends=True)
        return msg

    msg = []
    msg.extend(traceback.format_stack())
    msg.extend(traceback.format_exception(*sys.exc_info())[1:])
    msg_relevant = ["Traceback (Envo relevant):\n"]
    # TODO: Fix this
    relevant = True
    for m in msg:
        if re.search(r"env_.*\.py", m):
            relevant = True
        if relevant:
            msg_relevant.append(m)

    if relevant:
        msg = msg_relevant

    return msg


@dataclass
class EnvParser:
    path: Path

    def __post_init__(self):
        self.parents = self._get_parents()

    @property
    def source(self) -> str:
        return self.path.read_text("utf-8")

    @property
    def class_name(self) -> str:
        return re.search(r"\nclass (.*)\(UserEnv\):", self.source)[1]

    @property
    def plugins(self) -> List[str]:
        raw_search = re.search(r"plugins.*=.*\[(.*)]", self.source)[1]
        if not raw_search:
            return []

        ret = raw_search.split(",")
        return ret

    def _get_parents(self) -> List["EnvParser"]:
        parents_str = re.search(r"parents.*=.*\[(.*)]", self.source)[1]
        if not parents_str:
            return []
        parents_paths_relative = parents_str.replace("'", "").replace('"', "").split(",")
        parents_paths_relative = [p.strip() for p in parents_paths_relative]

        parents_paths = [Path(self.path.parent / p).resolve() for p in parents_paths_relative]
        ret = [EnvParser(p) for p in parents_paths]
        return ret

    def get_stub(self) -> str:
        # remove duplicates
        parents_src = ""
        for p in self.parents:
            parents_src += p.get_stub() + "\n"

        parents = [f"__{p.class_name}" for p in self.parents]

        class_name = f"__{self.class_name}"

        src = self.source.replace(self.class_name, class_name)
        # Remove method bodies
        src = re.sub(r"(def.*\(.*\).*?:)\n(?:(?:\n* {8,}.*?\n)+)", r"\1 ...", src)
        # Remove Env declaration
        src = re.sub(r"Env *?=.*?\n", r"", src)
        # Leave only variable declarations
        src = re.sub(r"((?:    )+\S*:.*)=.*\n", r"\1\n", src)

        melted = dedent(
            f"""\n
        class {self.class_name}(envo.env.Env, {class_name}, {",".join(parents)} {"," if parents else ""} {",".join(self.plugins)}):
            def __init__(self):
                pass
        """  # noqa: E501
        )

        ret = parents_src + src + melted

        return ret


PLATFORM_WINDOWS = "windows"
PLATFORM_LINUX = "linux"
PLATFORM_BSD = "bsd"
PLATFORM_DARWIN = "darwin"
PLATFORM_UNKNOWN = "unknown"


def get_platform_name():
    if sys.platform.startswith("win"):
        return PLATFORM_WINDOWS
    elif sys.platform.startswith("darwin"):
        return PLATFORM_DARWIN
    elif sys.platform.startswith("linux"):
        return PLATFORM_LINUX
    elif sys.platform.startswith(("dragonfly", "freebsd", "netbsd", "openbsd", "bsd")):
        return PLATFORM_BSD
    else:
        return PLATFORM_UNKNOWN


__platform__ = get_platform_name()


def is_linux():
    return __platform__ == PLATFORM_LINUX


def is_bsd():
    return __platform__ == PLATFORM_BSD


def is_darwin():
    return __platform__ == PLATFORM_DARWIN


def is_windows():
    return __platform__ == PLATFORM_WINDOWS


def add_source_roots(paths: List[Union[Path, str]]) -> None:
    logger.debug(f"Adding source roots {paths}")
    for p in paths:
        if not str(p).strip():
            continue

        if str(p) in sys.path:
            sys.path.remove(str(p))

        sys.path.insert(0, str(p))


def get_repo_root() -> Path:
    path = Path(".").absolute()

    while not list(path.glob("*.git")):
        if path == path.parent:
            raise RuntimeError("Can't find repo root (missing .git directory?)")
        path = path.parent

    return path


def iterate_frames(frame: FrameType) -> Generator[FrameType, None, None]:
    current_frame: Optional[FrameType] = frame
    while current_frame:
        yield current_frame
        current_frame = current_frame.f_back


def is_suspend_frame(frame: FrameType) -> bool:
    ret = "pydevd.py" in frame.f_code.co_filename and "do_wait_suspend" in frame.f_code.co_name
    return ret


def colored(inp: str, color: Tuple[int, int, int]) -> str:
    ret = f"\033[38;2;{color[0]};{color[1]};{color[2]}m{inp}\x1b[0m"
    return ret
