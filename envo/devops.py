import os
import re
import subprocess
import sys
from subprocess import Popen

__all__ = ["CommandError", "run", "inject", "run_get"]

from dataclasses import dataclass
from textwrap import dedent
from typing import List, Optional, Union

from colorama import Fore, Style

from envo import console, logger
from envo.misc import is_linux, is_windows


class CommandError(RuntimeError):
    pass


def _get_popen_cmd(command: str) -> List[str]:
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

    return popen_cmd


@dataclass
class Output:
    stdout: str
    stderr: str


def run_get(command: str) -> Output:
    popen_cmds = _get_popen_cmd(command=command)

    proc = Popen(popen_cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ)
    outs, errs = proc.communicate()

    output = Output(stdout=outs.decode("utf-8"), stderr=errs.decode("utf-8"))
    return output


def _run(
    command: str,
    raise_on_error=True,
    print_output=True,
    print_errors=True,
    verbose: Optional[bool] = None,
    background=False,
) -> Optional[str]:

    debug = os.environ.get("ENVO_DEBUG", False)

    if verbose is None:
        verbose = os.environ.get("ENVO_VERBOSE_RUN", False)

    popen_cmd = _get_popen_cmd(command)

    dedent_cmd = dedent(command.strip())
    if verbose:
        console.rule(f"[bold rgb(225,221,0)]{dedent_cmd}", align="center", style="rgb(255,0,255)")

    if debug:
        print(f"Run: {Fore.BLUE}{Style.BRIGHT}{dedent_cmd}{Style.RESET_ALL}")

    kwargs = {}
    if not print_output:
        kwargs["stdout"] = subprocess.PIPE

    if not print_errors:
        kwargs["stderr"] = subprocess.PIPE

    proc = Popen(popen_cmd, env=os.environ, **kwargs)

    if background:
        return None

    ret_code = proc.wait()

    if ret_code != 0 and raise_on_error:
        sys.exit(ret_code)


def run(
    command: Union[str, List[str]],
    raise_on_error=True,
    print_output=True,
    print_errors=True,
    verbose: Optional[bool] = None,
    background=False,
    progress_bar: Optional[str] = None,
) -> None:
    # join multilines
    if not isinstance(command, list):
        command = [command]

    if progress_bar is not None:
        from rich.progress import track

        for c in track(command, description=progress_bar):
            _run(
                command=c,
                raise_on_error=raise_on_error,
                print_output=print_output,
                print_errors=print_errors,
                verbose=verbose,
                background=background,
            )
    else:
        for c in command:
            _run(
                command=c,
                raise_on_error=raise_on_error,
                print_output=print_output,
                print_errors=print_errors,
                verbose=verbose,
                background=background,
            )


def inject(command: str) -> None:
    __xonsh__.shell.run_code(command)
