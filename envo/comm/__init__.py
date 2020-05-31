import importlib.machinery
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Dict

__all__ = ["dir_name_to_class_name", "setup_logger", "render_py_file", "render_file"]


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


def setup_logger() -> None:
    from loguru import logger

    logger.remove()

    logger.add(
        sys.stdout,
        format="<blue>{message}</blue>",
        level="DEBUG",
        filter=lambda x: x["level"].name == "DEBUG",
    )
    logger.add(
        sys.stdout,
        format="<bold>{message}</bold>",
        level="INFO",
        filter=lambda x: x["level"].name == "INFO",
    )
    logger.add(
        sys.stderr,
        format="<bold><yellow>{message}</yellow></bold>",
        level="WARNING",
        filter=lambda x: x["level"].name == "WARNING",
    )
    logger.add(
        sys.stderr,
        format="<bold><red>{message}</red></bold>",
        level="ERROR",
        filter=lambda x: x["level"].name == "ERROR",
    )


def render_file(template_path: Path, output: Path, context: Dict[str, Any]) -> None:
    from jinja2 import StrictUndefined, Template

    template = Template(template_path.read_text(), undefined=StrictUndefined)
    output.write_text(template.render(**context))


def render_py_file(template_path: Path, output: Path, context: Dict[str, Any]) -> None:
    import black

    render_file(template_path, output, context)
    try:
        black.main([str(output), "-q"])
    except SystemExit:
        pass


def import_module_from_file(path: Path) -> Any:
    if not path.is_absolute():
        frame = inspect.stack()[1]
        caller_path_dir = Path(frame[1]).parent
        path = caller_path_dir / path

    loader = importlib.machinery.SourceFileLoader(str(path), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    return module
