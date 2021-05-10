import json
import os
import subprocess
import textwrap
import time
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List, Optional

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent

__all__ = [
    "add_command",
    "add_declaration",
    "add_definition",
    "add_hook",
    "change_file",
    "add_flake_cmd",
    "add_mypy_cmd",
    "replace_in_code",
    "add_context",
    "add_plugins",
    "add_boot",
    "clean_output",
    "run",
    "add_function",
]


def clean_output(output: str) -> str:
    ret = output
    if isinstance(output, bytes):
        ret = output.decode("utf-8")

    ret = ret.replace("\r", "")
    ret = ret.replace("\x1b[0m", "")
    ret = ret.replace("\n\n", "\n")
    return ret


def run(command: str, env: Optional[Dict[str, Any]] = None, pipe_stderr=True) -> str:
    kwargs = {}
    if env:
        kwargs["env"] = env

    if pipe_stderr:
        kwargs["stderr"] = subprocess.PIPE
    else:
        kwargs["stderr"] = subprocess.STDOUT

    ret = subprocess.check_output(command, shell=True, **kwargs).decode("utf-8")
    ret = clean_output(ret)
    return ret


def change_file(file: Path, delay_s: float, new_content: str) -> None:
    def fun(file: Path, delay_s: float, new_content: str) -> None:
        time.sleep(delay_s)
        file.write_text(new_content)

    thread = Thread(target=fun, args=(file, delay_s, new_content))
    thread.start()


def replace_in_code(what: str, to_what: str, file=Path("env_test.py"), indent: int = 0):
    content = file.read_text()

    if what not in content:
        raise RuntimeError('"what" string not found in file')

    command_code = textwrap.dedent(to_what)
    if indent:
        command_code = textwrap.indent(command_code, indent * " ")
    content = content.replace(what, command_code)
    file.write_text(content)


def add_declaration(code: str, file=Path("env_test.py")) -> None:
    spaces = 4 * " "
    code = textwrap.dedent(code)
    replace_in_code(
        f"{spaces}# Declare your variables here",
        f"""
        {code}
        # Declare your variables here
        """,
        file=file,
        indent=4,
    )


def add_definition(code: str, file=Path("env_test.py")) -> None:
    spaces = 8 * " "
    code = textwrap.dedent(code)
    replace_in_code(
        f"{spaces}# Define your variables here",
        f"""
        {code}
        # Define your variables here
        """,
        file=file,
        indent=8,
    )


def add_command(code: str, file=Path("env_test.py")) -> None:
    spaces = 4 * " "
    code = textwrap.dedent(code)
    replace_in_code(
        f"{spaces}# Define your commands, hooks and properties here",
        f"""
        {code}
        # Define your commands, hooks and properties here
        """,
        file=file,
        indent=4,
    )


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


def add_on_partial_reload(code: str, file=Path("env_test.py")) -> None:
    add_command(code, file)


def add_plugins(name: str, file=Path("env_test.py")) -> None:
    replace_in_code(
        "plugins: List[Plugin] = []", f"plugins: List[Plugin] = [{name}]", file=file
    )


def add_function(code: str, file=Path("env_comm.py")) -> None:
    cleaned_code = textwrap.dedent(code)
    file.write_text(file.read_text() + cleaned_code)


def add_imports(code: str, file=Path("env_comm.py")) -> None:
    cleaned_code = textwrap.dedent(code)
    file.write_text(cleaned_code + file.read_text())
