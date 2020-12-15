import re
import subprocess
import sys
import time
from subprocess import Popen
from threading import Thread
from typing import List

__all__ = ["CommandError", "run"]


class CommandError(RuntimeError):
    pass


def run(
    command: str,
    ignore_errors: bool = False,
    print_output: bool = True,
) -> str:
    # join multilines
    command = re.sub(r"\\(?:\t| )*\n(?:\t| )*", "", command)
    command = "set -uoe pipefail\n" + command

    proc = Popen([f"/bin/bash", "--rcfile", "/dev/null", "-c", command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    buffer = []

    def std_out_reader():
        while True:
            c = proc.stdout.read(1)
            if not c or c == b"\xf0":
                break
            c = c.decode("utf-8")
            if print_output:
                sys.stdout.write(c)
            buffer.append(c)

    Thread(target=std_out_reader).start()

    while True:
        ret_code = proc.poll()
        if ret_code is None:
            time.sleep(0.05)
            continue

        if ret_code != 0 and not ignore_errors:
            sys.exit(ret_code)
        else:
            ret = "".join(buffer)
            return ret
