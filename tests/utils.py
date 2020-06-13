import os
import textwrap
import time
from pathlib import Path
from threading import Thread

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


def change_file(file: Path, delay_s: float, new_content: str) -> None:
    def fun(file: Path, delay_s: float, new_content: str) -> None:
        time.sleep(delay_s)
        file.write_text(new_content)

    thread = Thread(target=fun, args=(file, delay_s, new_content))
    thread.start()


def replace_in_code(what: str, to_what: str, file=Path("env_comm.py"), indent: int = 0):
    content = file.read_text()

    if what not in content:
        raise RuntimeError('"what" string not found in file')

    command_code = textwrap.dedent(to_what)
    if indent:
        command_code = textwrap.indent(command_code, indent * " ")
    content = content.replace(what, command_code)
    file.write_text(content)


def add_declaration(code: str, file=Path("env_comm.py")) -> None:
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


def add_definition(code: str, file=Path("env_comm.py")) -> None:
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


def add_command(code: str, file=Path("env_comm.py")) -> None:
    spaces = 4 * " "
    code = textwrap.dedent(code)
    replace_in_code(
        f"{spaces}# Define your commands, handles and properties here",
        f"""
        {code}
        # Define your commands, handles and properties here
        """,
        file=file,
        indent=4,
    )


def mypy_cmd(prop: bool = False, glob: bool = False) -> None:
    add_command(
        f"""
        @command(prop={prop}, glob={glob})
        def mypy(self, test_arg: str = "") -> None:
            print("Mypy all good" + test_arg)
        """
    )


def flake_cmd(prop: bool = False, glob: bool = False) -> None:
    add_command(
        f"""
        @command(prop={prop}, glob={glob})
        def flake(self, test_arg: str = "") -> None:
            print("Flake all good" + test_arg)
        """
    )
