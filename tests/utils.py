import inspect
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

    command_code = inspect.cleandoc(to_what)
    if indent:
        command_code = textwrap.indent(command_code, indent * " ")
    content = content.replace(what, command_code)
    file.write_text(content)
