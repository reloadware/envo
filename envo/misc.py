import errno
import importlib.machinery
import importlib.util
import os
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional

from globmatch_temp import glob_match
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
]


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
        return not glob_match(self.relative_str, exclude) and glob_match(
            self.relative_str, include
        )

    def is_dir(self) -> bool:
        return self.absolute.is_dir()


class FilesWatcher(FileSystemEventHandler):
    @dataclass
    class Sets:
        include: List[str]
        exclude: List[str]
        root: Path
        name: str = "Anonymous"

    @dataclass
    class Callbacks:
        on_event: Callback

    def __init__(self, se: Sets, calls: Callbacks):
        from envo import logger

        self.include = [p.lstrip("./") for p in se.include]
        self.exclude = [p.lstrip("./") for p in se.exclude]
        self.root = se.root

        super().__init__()
        self.se = se
        self.calls = calls

        self.logger = logger.create_child(
            f"{self.se.name} Inotify", descriptor=f"{self.se.name} Inotify"
        )

        self.logger.debug("Starting Inotify")
        self.observer = Observer()

        self.observer.schedule(self, str(self.se.root), recursive=True)

    def on_any_event(self, event: FileSystemEvent):
        kwargs = event.__dict__

        for k in kwargs.keys():
            kwargs[k.lstrip("_")] = Path(kwargs.pop(k)).resolve()

        event = event.__class__(**kwargs)
        self.calls.on_event(event)

    def flush(self) -> None:
        self.observer.event_queue.queue.clear()

    def match(self, path: str, include: List[str], exclude: List[str]) -> bool:
        return not glob_match(path, exclude) and glob_match(path, include)

    def walk_dirs(self, on_match: Callable) -> None:
        def walk(path: Path):
            for p in path.iterdir():
                if glob_match(path, self.exclude):
                    continue
                on_match(str(p).encode("utf-8"))
                if p.is_dir():
                    walk(p)

        walk(self.root)

    def start(self) -> None:
        self.logger.debug("Starting observer")

        if is_linux():

            def _add_dir_watch(self2, path, recursive, mask):
                """
                Adds a watch (optionally recursively) for the given directory path
                to monitor events specified by the mask.

                :param path:
                    Path to monitor
                :param recursive:
                    ``True`` to monitor recursively.
                :param mask:
                    Event bit mask.
                """
                if not os.path.isdir(path):
                    raise OSError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), path)
                self2._add_watch(path, mask)
                if recursive:
                    self.walk_dirs(on_match=lambda p: self2._add_watch(p, mask))

            from watchdog.observers.inotify_c import Inotify

            Inotify._add_dir_watch = _add_dir_watch

        self.observer.start()
        self.logger.debug("Observer started")

    def clone(self) -> "FilesWatcher":
        return FilesWatcher(se=self.se, calls=self.calls)

    def stop(self) -> None:
        self.observer.stop()

    def dispatch(self, event: FileSystemEvent):
        """Dispatches events to the appropriate methods.

        :param event:
            The event object representing the file system event.
        :type event:
            :class:`FileSystemEvent`
        """
        paths = []
        if hasattr(event, "dest_path"):
            paths.append(str(event.dest_path))
        if event.src_path:
            paths.append(str(event.src_path))

        if any(
            self.match(
                str(Path(p).relative_to(self.root)),
                include=self.include,
                exclude=self.exclude,
            )
            for p in paths
        ):
            super().dispatch(event)


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
    from jinja2 import StrictUndefined, Template

    template = Template(template_path.read_text("utf-8"), undefined=StrictUndefined)
    output.write_text(template.render(**context), "utf-8")


def render(template: str, output: Path, context: Dict[str, Any]) -> None:
    from jinja2 import StrictUndefined, Template

    template = Template(template, undefined=StrictUndefined)
    output.write_text(template.render(**context), "utf-8")


def render_py_file(template_path: Path, output: Path, context: Dict[str, Any]) -> None:
    render_file(template_path, output, context)


def path_to_module_name(path: Path, package_root: Path) -> str:
    rel_path = path.resolve().absolute().relative_to(package_root.resolve())
    ret = str(rel_path).replace(".py", "").replace("/", ".").replace("\\", ".")
    ret = ret.replace(".__init__", "")
    return ret


def import_from_file(path: Path) -> Any:
    path = path.resolve()
    module_name = path_to_module_name(path, path.parent)
    loader = importlib.machinery.SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_loader(module_name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    return module


def get_module_from_full_name(full_name: str) -> Optional[str]:
    parts = full_name.split(".")

    while True:
        module_name = ".".join(parts)
        if module_name in sys.modules:
            return module_name
        parts.pop(0)
        if not parts:
            return None


def import_from_file_raw(path: Path) -> Any:
    loader = importlib.machinery.SourceFileLoader(str(path), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


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
        parents_paths_relative = (
            parents_str.replace("'", "").replace('"', "").split(",")
        )
        parents_paths_relative = [p.strip() for p in parents_paths_relative]

        parents_paths = [
            Path(self.path.parent / p).resolve() for p in parents_paths_relative
        ]
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
