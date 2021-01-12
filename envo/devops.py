import re
import subprocess
import sys
from subprocess import Popen

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
        popen_cmd = ["cmd.exe", "/c", command]
    elif is_linux():
        command = "set -uoe pipefail\n" + command
        popen_cmd = ["/bin/bash", "--rcfile", "/dev/null", "-c", command]
    else:
        raise NotImplementedError()

    proc = Popen(popen_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    buffer = []

    while True:
        c = proc.stdout.read(1)
        if not c or c == b"\xf0":
            break

        if print_output:
            try:
                sys.stdout.buffer.write(c)
                sys.stdout.flush()
            except ValueError:
                break
        buffer.append(c)

    ret_code = proc.wait()

    if ret_code != 0 and not ignore_errors:
        sys.exit(ret_code)
    else:
        ret = b"".join(buffer)
        ret = ret.decode("utf-8")
        return ret
