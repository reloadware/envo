import os
import shutil
import time
from pathlib import Path
from threading import Thread

from pexpect import run

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


def change_file(file: Path, delay_s: float, new_content: str) -> None:
    def fun(file: Path, delay_s: float, new_content: str) -> None:
        time.sleep(delay_s)
        file.write_text(new_content)

    thread = Thread(target=fun, args=(file, delay_s, new_content))
    thread.start()


def init_child_env(child_dir: Path) -> None:
    cwd = Path(".").absolute()
    if child_dir.exists():
        shutil.rmtree(child_dir)

    child_dir.mkdir()
    os.chdir(str(child_dir))
    run("envo test --init")

    comm_file = Path("env_comm.py")
    content = comm_file.read_text()
    content = content.replace("parent = None", 'parent = ".."')
    comm_file.write_text(content)

    os.chdir(str(cwd))
