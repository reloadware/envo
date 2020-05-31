import os
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
