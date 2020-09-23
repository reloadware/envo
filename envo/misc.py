import importlib.machinery
import importlib.util
import inspect
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
import inotify.adapters
import inotify.constants
from globmatch_temp import glob_match
from threading import Thread

__all__ = [
    "dir_name_to_class_name",
    "render_py_file",
    "render_file",
    "import_from_file",
    "EnvoError",
    "Callback",
    "Inotify"
]

from envo import logger


class EnvoError(Exception):
    pass


class Callback:
    def __init__(self, func: Optional[Callable[..., Any]]) -> None:
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


class Inotify:
    @dataclass
    class Event:
        path: InotifyPath
        type_names: Tuple[str]
        during_pause: bool
        during_commands: bool

    @dataclass
    class Sets:
        include: List[str]
        exclude: List[str]
        root: Path

    @dataclass
    class Callbacks:
        on_event: Callback

    device: inotify.adapters.Inotify
    stop: bool
    events: List[Event]
    ready: bool

    _pause: bool
    _collector_thread: Thread
    _producer_thread: Thread
    _on_event: Callback

    def __init__(self, se: Sets, calls: Callbacks):
        self.se = se
        self.calls = calls

        self.device = inotify.adapters.Inotify()
        self.remove_watches()

        self.ready = False

        self._pause = False
        self._stop = False
        self._collector_thread = Thread(target=self._collector_thread_fun)
        self._producer_thread = Thread(target=self._producer_thread_fun)
        self.events = []

        self.remove_watches()
        self.add_watch_recursive(self.se.root)

    def _collector_thread_fun(self) -> None:
        logger.debug("Starting collector thread")
        for raw_event in self.device.event_gen(yield_nones=False):
            if self._stop:
                return
            (_, type_names, path, filename) = raw_event
            raw_path = Path(path) / Path(filename)

            event = Inotify.Event(
                path=InotifyPath(raw_path=raw_path, root=self.se.root),
                type_names=type_names,
                during_pause=self._pause,
                during_commands=self._pause,
            )

            if event.path.match(self.se.include, self.se.exclude) or "IN_ISDIR" in event.type_names:
                if self._pause:
                    continue

                if "IN_CREATE" in event.type_names:
                    self.add_watch_recursive(event.path.absolute)

                if any([s in event.type_names for s in ["IN_DELETE", "IN_DELETE_SELF"]]):
                    self.remove_watch(event.path.absolute, recursive=True)

                self.events.append(event)

    def _producer_thread_fun(self) -> None:
        logger.debug("Starting producer thread")
        self.ready = True

        while not self._stop:
            while self.events:
                if self._pause:
                    break
                e = self.events.pop(0)
                self.calls.on_event(e)

            time.sleep(0.1)

    def flush(self) -> None:
        self.events = []

    def start(self) -> None:
        logger.debug("Starting Inotify")
        self._collector_thread.start()
        self._producer_thread.start()

    def remove_watches(self) -> None:
        self.device._Inotify__watches = {}
        self.device._Inotify__watches_r = {}

    def remove_watch(self, path: Path, recursive=False) -> None:
        if str(path) not in self.device._Inotify__watches:
            return

        self.device._Inotify__watches.pop(str(path))
        if recursive:
            watches = self.device._Inotify__watches.copy()
            for f in watches:
                if str(f).startswith(str(path)):
                    self.device._Inotify__watches.remove(f)

    def pause(self) -> None:
        self._pause = True

    def resume(self) -> None:
        self._pause = False

    def add_watch(self, raw_path: Path) -> None:
        path = InotifyPath(raw_path=raw_path, root=self.se.root)
        if str(path.absolute) not in self.device._Inotify__watches:
            self.device.add_watch(str(path.absolute))

    def add_watch_recursive(self, raw_path: Path) -> None:
        if self._stop:
            return

        path = InotifyPath(raw_path=raw_path, root=self.se.root)
        if path.relative == Path("."):
            self.device.add_watch(str(path.absolute))
        else:
            if not path.match(self.se.include, self.se.exclude):
                return

        if path.relative.is_dir():
            self.add_watch(path.absolute)
            for p in path.absolute.iterdir():
                self.add_watch_recursive(p)
        else:
            self.add_watch(path.absolute)

    def stop(self) -> None:
        self._stop = True
        self.flush()
        env_comm = self.se.root / "env_comm.py"
        # Save the same content to trigger inotify event
        env_comm.read_text()

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

    template = Template(template_path.read_text(), undefined=StrictUndefined)
    output.write_text(template.render(**context))


def render_py_file(template_path: Path, output: Path, context: Dict[str, Any]) -> None:
    render_file(template_path, output, context)


def import_from_file(path: Path) -> Any:
    if not path.is_absolute():
        frame = inspect.stack()[1]
        caller_path_dir = Path(frame[1]).parent
        path = caller_path_dir / path

    loader = importlib.machinery.SourceFileLoader(str(path), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    return module
