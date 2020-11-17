import os
import re
import sys
from getpass import getpass
from typing import List

import pexpect
from tqdm import tqdm

from envo import logger

__all__ = ["CommandError", "run"]


class CommandError(RuntimeError):
    pass


class CustomPrint:
    def __init__(self, prompt: str, command: str) -> None:
        self.old_stdout = sys.stdout
        self.command = command
        self.prompt = prompt

    def write(self, text: bytes) -> None:
        text_str: str = text.decode("utf-8")

        for line in text_str.splitlines(keepends=True):
            if len(text_str) == 0:
                return

            if not any((s in line) for s in [self.command, self.prompt]):
                self.old_stdout.write(line)

    def flush(self) -> None:
        self.old_stdout.flush()


def run(command: str, ignore_errors: bool = False, print_output: bool = True, progress_bar: bool = False,) -> List[str]:
    # preprocess
    # join multilines
    command = re.sub(r"\\(?:\t| )*\n(?:\t| )*", "", command)

    commands: List[str] = [s.strip() for s in command.splitlines() if s.strip()]

    rets: List[str] = []

    prompt = r"##PG_PROMPT##"

    p = pexpect.spawn("bash --rcfile /dev/null", env=os.environ, echo=False)
    p.delaybeforesend = None

    p.expect(r"(\$|#)")
    p.sendline(f"export PS1={prompt}")
    p.expect(prompt)
    p.sendline(f"set -uo pipefail")
    p.expect(prompt)

    # Get sudo password if needed
    if "sudo " in command:
        tries = 3
        while True:
            sudo_password = getpass("Sudo password: ")
            p.sendline('sudo echo "granting sudo"')
            p.sendline(sudo_password)
            try:
                p.expect(prompt, timeout=1)
                print("Thank you.")
            except pexpect.exceptions.TIMEOUT:
                tries -= 1

                if tries == 0:
                    print("sudo: 3 incorrect password attempts")
                    exit(1)

                print("Sorry, try again.")
                continue
            break

    pbar: tqdm
    if progress_bar:
        pbar = tqdm(total=len(commands))

    for c in commands:
        if "PG_DEBUG" in os.environ:
            logger.debug(c)

        if print_output:
            p.logfile = CustomPrint(command=c, prompt=prompt)
        p.sendline(c)
        p.expect(prompt, timeout=60 * 15)
        if print_output:
            p.logfile = None

        raw_outputs: List[bytes] = p.before.splitlines()
        outputs: List[str] = [s.decode("utf-8").strip() for s in raw_outputs]
        # get exit code
        p.sendline('echo "$?"')
        p.expect(prompt)
        ret_code = int(p.before.splitlines()[0].strip())

        if outputs:
            ret = "\n".join(outputs)
            rets.append(ret)

        if not ignore_errors:
            if ret_code:
                sys.exit(ret_code)

        if progress_bar:
            pbar.update(1)

    if progress_bar:
        pbar.close()

    return rets
