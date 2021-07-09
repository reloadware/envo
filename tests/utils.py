import json
import os
import re
import subprocess
import textwrap
import time
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List, Optional, Union

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent

__all__ = [
    "add_command",
    "add_imports_in_envs_in_dir",
    "add_env_declaration",
    "add_definition",
    "add_method",
    "add_hook",
    "add_meta",
    "add_namespace",
    "change_file",
    "add_flake_cmd",
    "add_mypy_cmd",
    "replace_in_code",
    "add_context",
    "add_boot",
    "clean_output",
    "run",
    "RunError"
]

DECLARE_NAMESPACES = "# Declare your command namespaces here"
DECLARE_ENV_VARIABLES = "# Declare your env variables here"
DEFINE_VARIABLES = "# Define your variables here"
DEFINE_COMMANDS = "# Define your commands, hooks and properties here"


class RunError(Exception):
    def __init__(self, stderr: str, stdout: str, return_code: int) -> None:
        self.return_code = return_code
        self.stderr = stderr
        self.stdout = stdout

        super().__init__(stderr)


def clean_output(output: str) -> str:
    ret = output
    if isinstance(output, bytes):
        ret = output.decode("utf-8")

    ret = ret.replace("\r", "")
    ret = ret.replace("\x1b[0m", "")
    ret = ret.replace("\n\n", "\n")
    return ret


def run(command: str, env: Optional[Dict[str, Any]] = None) -> str:
    kwargs = {}
    if env:
        kwargs["env"] = env

    ret = subprocess.run(command, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, **kwargs)

    if ret.returncode != 0:
        raise RunError(stdout=ret.stdout.decode("utf-8"),
                       stderr=ret.stderr.decode("utf-8"),
                       return_code=ret.returncode)

    return ret.stdout.decode("utf-8")


def change_file(file: Path, delay_s: float, new_content: str) -> None:
    def fun(file: Path, delay_s: float, new_content: str) -> None:
        time.sleep(delay_s)
        file.write_text(new_content)

    thread = Thread(target=fun, args=(file, delay_s, new_content))
    thread.start()


def replace_in_code(what: str, to_what: str, file: Union[Path, str] = "env_test.py", indent: int = 0):
    file = Path(file)
    content = file.read_text()

    if what not in content:
        raise RuntimeError('"what" string not found in file')

    command_code = textwrap.dedent(to_what)
    if indent:
        command_code = textwrap.indent(command_code, indent * " ")
    content = content.replace(what, command_code)
    file.write_text(content)


def add_env_declaration(code: str, file=Path("env_test.py")) -> None:
    spaces = 4 * " "
    code = textwrap.dedent(code)
    replace_in_code(
        f"{spaces}{DECLARE_ENV_VARIABLES}",
        f"""
        {code}
        {DECLARE_ENV_VARIABLES}
        """,
        file=file,
        indent=8,
    )


def add_definition(code: str, file=Path("env_test.py")) -> None:
    spaces = 8 * " "
    code = textwrap.dedent(code)
    replace_in_code(
        f"{spaces}{DEFINE_VARIABLES}",
        f"""
        {code}
        {DEFINE_VARIABLES}
        """,
        file=file,
        indent=8,
    )


def add_command(code: str, file=Path("env_test.py")) -> None:
    spaces = 4 * " "
    code = textwrap.dedent(code)
    replace_in_code(
        f"{spaces}{DEFINE_COMMANDS}",
        f"""
        {code}
        {DEFINE_COMMANDS}
        """,
        file=file,
        indent=4,
    )


def add_method(code: str, file=Path("env_test.py")) -> None:
    add_command(code, file)


def add_hook(code: str, file=Path("env_test.py")) -> None:
    add_command(code, file)


def add_namespace(name: str, file=Path("env_test.py")) -> None:
    replace_in_code(
        "# Declare your command namespaces here",
        f'{name} = Namespace("{name}")',
        file=file,
    )


def add_flake_cmd(
    file=Path("env_test.py"), namespace=None, message="Flake all good"
) -> None:
    namespaced_command = f"{namespace}.command" if namespace else "command"

    add_command(
        f"""
        @{namespaced_command}
        def __my_flake(self, test_arg: str = "") -> str:
            print("{message}" + test_arg)
            return "Flake return value"
        """,
        file=file,
    )


def add_mypy_cmd(
    file=Path("env_test.py"), namespace=None, message="Mypy all good"
) -> None:
    namespaced_command = f"{namespace}.command" if namespace else "command"

    add_command(
        f"""
        @{namespaced_command}
        def __my_mypy(self, test_arg: str = "") -> None:
            print("{message}" + test_arg)
        """,
        file=file,
    )


def add_context(
    context: Dict[str, Any],
    name: str = "some_context",
    namespace=None,
    file=Path("env_test.py"),
) -> None:
    namespaced_context = f"{namespace}.context" if namespace else "context"
    context_str = json.dumps(context)
    add_command(
        f"""
        @{namespaced_context}
        def {name}(self) -> Dict[str, Any]:
            return {context_str}
        """,
        file=file,
    )


def add_boot(
    boot_codes: List[str], name: str = "some_boot", file=Path("env_test.py")
) -> None:
    lines = ",".join([f'"{c}"' for c in boot_codes])

    add_command(
        f"""
        @boot_code
        def {name}(self) -> List[str]:
            return [{lines}]
        """,
        file=file,
    )


def add_meta(meta: str, file=Path("env_test.py")) -> None:
    file.write_text(re.sub(fr"(class Meta\(.*\):)", fr"\1\n{' '*8 + meta}", file.read_text()))


def add_on_partial_reload(code: str, file=Path("env_test.py")) -> None:
    add_command(code, file)


def add_imports(code: str, file=Path("env_comm.py")) -> None:
    cleaned_code = textwrap.dedent(code)
    file.write_text(cleaned_code + file.read_text())


def add_imports_in_envs_in_dir(directory = Path(".")) -> None:
    for f in directory.glob("*"):
        if f.is_dir():
            add_imports_in_envs_in_dir(f)
        elif f.glob("env_*.py"):
            f.write_text("from envo import *\nimport os\n" + f.read_text())
