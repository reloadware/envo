import os
import re
import subprocess
import sys
from subprocess import Popen

__all__ = ["CommandError", "run"]

from envo.misc import is_linux, is_windows
from envo import console


class CommandError(RuntimeError):
    pass


def run(
    command: str,
    ignore_errors = False,
    print_output = True,
    verbose = False
) -> str:
    # join multilines
    verbose = verbose or os.environ.get("ENVO_VERBOSE_RUN")

    command_extra = re.sub(r"\\(?:\t| )*\n(?:\t| )*", "", command)

    if is_windows():
        command_extra = command_extra.strip()
        command_extra = command_extra.replace("\r", "")
        command_extra = command_extra.replace("\n", " & ")
        popen_cmd = ["cmd.exe", "/c", command_extra]
    elif is_linux():
        options = ["set -uoe pipefail", "shopt -s globstar"]
        command_extra = "\n".join(options) + "\n" + command_extra
        popen_cmd = ["/bin/bash", "--rcfile", "/dev/null", "-c", command_extra]
    else:
        raise NotImplementedError()

    if verbose:
        console.rule(f"[bold rgb(225,221,0)]{command}", align="center", style="rgb(255,0,255)")

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
