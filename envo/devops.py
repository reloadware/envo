import re
import subprocess
import sys
import time
from subprocess import Popen
from threading import Thread
from typing import List

__all__ = ["CommandError", "run"]

from envo.misc import is_linux, is_windows


class CommandError(RuntimeError):
    pass


def run(
    command: str,
    ignore_errors: bool = False,
    print_output: bool = True,
) -> str:
    # join multilines
    command = re.sub(r"\\(?:\t| )*\n(?:\t| )*", "", command)

    if is_windows():
        command = command.strip()
        command = command.replace("\r", "")
        command = command.replace("\n", " & ")
        popen_cmd = [f"cmd.exe", "/c", command]
    elif is_linux():
        command = "set -uoe pipefail\n" + command
        popen_cmd = [f"/bin/bash", "--rcfile", "/dev/null", "-c", command]
    else:
        raise NotImplementedError()

    proc = Popen(popen_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    buffer = []

    def std_out_reader():
        while True:
            c = proc.stdout.read(1)
            if not c or c == b"\xf0":
                break

            if print_output:
                try:
                    sys.stdout.buffer.write(c)
                    sys.stdout.flush()
                except ValueError:
                    return
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
            ret = b"".join(buffer)
            ret = ret.decode("utf-8")
            return ret
