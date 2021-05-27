import os
import re
import subprocess
import sys
from subprocess import Popen

__all__ = ["CommandError", "run"]

from textwrap import dedent

from typing import Optional, List, Union

from envo.misc import is_linux, is_windows
from envo import console


class CommandError(RuntimeError):
    pass


def _run(command: str,
         ignore_errors=False,
         print_output=True,
         verbose=False,
         background=False) -> Optional[str]:
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

    if verbose and print_output:
        dedent_cmd = dedent(command.strip())
        console.rule(f"[bold rgb(225,221,0)]{dedent_cmd}", align="center", style="rgb(255,0,255)")

    proc = Popen(popen_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    if background:
        return None

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


def run(
        command: Union[str, List[str]],
        ignore_errors=False,
        print_output=True,
        verbose=False,
        background=False,
        progress_bar: Optional[str] = None
) -> List[Optional[str]]:
    # join multilines
    ret = []
    if not isinstance(command, list):
        command = [command]

    if progress_bar is not None:
        from rich.progress import track
        for c in track(command, description=progress_bar):
            ret.append(_run(c, ignore_errors, print_output, verbose, background))
    else:
        for c in command:
            ret.append(_run(c, ignore_errors, print_output, verbose, background))

    return ret
