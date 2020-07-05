import os
import re
import shutil
import subprocess
import sys
from collections import Callable
from enum import Enum
from pathlib import Path
from subprocess import Popen
from time import sleep
from typing import List

import pexpect
import pyte
import pyte.modes

import fcntl

import pytest
from rhei import Stopwatch

from envo import const
from envo.shell import PromptBase
from tests.utils import add_command  # noqa F401
from tests.utils import add_declaration  # noqa F401
from tests.utils import add_definition  # noqa F401
from tests.utils import add_hook  # noqa F401
from tests.utils import change_file  # noqa F401
from tests.utils import flake_cmd  # noqa F401
from tests.utils import mypy_cmd  # noqa F401
from tests.utils import replace_in_code  # noqa F401
from tests.utils import add_context  # noqa F401
from tests.utils import add_plugin  # noqa F401

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


class PromptState(Enum):
    LOADING = 0
    NORMAL = 1
    EMERGENCY = 2
    MAYBE_LOADING = 3
    EMERGENCY_MAYBE_LOADING = 4


class PromptRe(PromptBase):
    default = r"[\(.*\)]*.*?\$ ?"

    def __init__(self, state: PromptState, name: str) -> None:
        super().__init__()

        self.state = state
        self.name = name
        self.emoji = const.stage_emojis["test"]

        self.state_prefix_map = {
            PromptState.LOADING: lambda: rf"{const.emojis['loading']}\({self.name}\){self.default}",
            PromptState.NORMAL: lambda: rf"{self.emoji}\({self.name}\){self.default}",
            PromptState.EMERGENCY: lambda: rf"{const.emojis['emergency']}{self.default}",
            PromptState.EMERGENCY_MAYBE_LOADING: lambda: rf"({const.emojis['emergency']}|{const.emojis['loading']}){self.default}",  # noqa: E501
            PromptState.MAYBE_LOADING: lambda: rf"({self.emoji}|{const.emojis['loading']})\({self.name}\){self.default}",  # noqa: E501
        }


class TestBase:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox, init):
        pass


def pexpect_spaw(command: str) -> pexpect.spawn:
    s = pexpect.spawn(command, echo=False, timeout=4)
    s.logfile = sys.stdout.buffer
    return s


class AssertInTime:
    class TIMEOUT(Exception):
        pass

    def __init__(self, condition: Callable, timeout=2):
        self.condition = condition
        self.sw = Stopwatch()
        self.sw.start()

        while True:
            if condition():
                break

            if self.sw.value >= timeout:
                raise self.TIMEOUT(self)
            sleep(0.05)


class Expecter:
    def __init__(self, spawn: "Spawn") -> None:
        self._spawn = spawn
        self.expected: List[str] = []
        self.prompt_re = PromptRe(state=PromptState.NORMAL, name="sandbox")
        self._return_code = 0
        self._expect_exit = False

    def output(self, regex: str) -> "Expecter":
        self.expected.append(regex)
        return self

    def cmd(self, cmd: str) -> "Expecter":
        self.expected.append(re.escape(cmd) + r"\n")
        return self

    def raw(self, raw: str) -> "Expecter":
        self.expected.append(re.escape(raw))
        return self

    def prompt(self, state=PromptState.NORMAL, name="sandbox") -> "Expecter":
        self.expected.append(str(PromptRe(state=state, name=name)))
        return self

    def reloaded(self, file="env_comm.py", times: int = 1) -> "Expecter":
        sleep(0.2)
        self._spawn.log()
        for i in range(times):
            self.output(rf'\[INFO\] Detected changes in "{re.escape(file)}"\n')
            self.output(r"\[INFO\] Reloading\.\.\.\n")
        return self

    def exit(self, return_code=0) -> "Expecter":
        self.expected.append(r"exit\n?")
        self._expect_exit = True
        self._return_code = return_code
        return self

    @property
    def expected_regex(self):
        return "".join(self.expected)

    def eval(self, timeout: int = 3) -> None:
        def condition():
            return re.fullmatch(self.expected_regex, self._spawn.cleaned_display, re.DOTALL)

        try:
            AssertInTime(condition, timeout)
        except AssertInTime.TIMEOUT:
            self.print_info()
            raise

        if self._expect_exit:
            self._spawn.stop_collecting = True

            # check if has exited
            def condition():
                return self._spawn.process.poll() == 0

            AssertInTime(condition, timeout)
            assert self._spawn.process.returncode == self._return_code
            self.print_info()

    def print_info(self):
        print("\nDisplay:")
        print(self._spawn.cleaned_display)
        expected_multiline = self.expected_regex.replace(r"\n", "\n")
        print(f"\nExpected (multiline):\n{expected_multiline}")
        print(f"\nExpected (raw):\n{self.expected}")


class Spawn:
    def __init__(self, command: str):
        self.screen = pyte.Screen(200, 50)
        self.stream = pyte.ByteStream(self.screen)

        environ = os.environ.copy()
        environ["ENVO_E2E_TEST"] = "True"
        environ["PYTHONUNBUFFERED"] = "True"
        environ["ENVO_SHELL_NOHISTORY"] = "True"
        self.process = Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, env=environ,
        )
        fcntl.fcntl(
            self.process.stdout, fcntl.F_SETFL, fcntl.fcntl(self.process.stdout, fcntl.F_GETFL) | os.O_NONBLOCK,
        )
        self.stop_collecting = False
        self._buffer = []
        # self._collector_thread = Thread(target=self._collector_thread)
        # self._collector_thread.start()

        self.expecter = Expecter(self)

        # wait a bit for things to start
        sleep(0.5)

    def exit(self) -> None:
        self.send("exit", expect=False)
        sleep(0.5)
        self.send("\n", expect=False)
        sleep(0.5)

    def log(self) -> None:
        sleep(0.2)
        self.sendline("logger.print_all(add_time=False);logger.clean()")

    def send(self, text: str, expect=True) -> None:
        if expect:
            self.expecter.raw(text)
        self.process.stdin.write(text.encode("utf-8"))
        self.process.stdin.flush()

    def sendline(self, line: str, expect=True) -> None:
        if expect:
            self.expecter.cmd(line)
        self.process.stdin.writelines([f"{line}\n".encode("utf-8")])
        self.process.stdin.flush()

    def _collect_output(self):
        try:
            while not self.stop_collecting:
                c: bytes = self.process.stdout.read(1)
                if not c:
                    return
                self._buffer.append(c)
                if c == b"\n":
                    c = b"\r\n"
                self.stream.feed(c)
        except OSError:
            pass

    @property
    def display(self):
        # Remove "Warning: Output is not a terminal"
        def ignore(s: str) -> bool:
            if "Warning: Output is not a terminal" in s:
                return True
            if "Warning: Input is not a terminal" in s:
                return True
            return False

        self._collect_output()
        display_raw = self.screen.display
        display = [s for s in display_raw if not ignore(s)]
        return display

    @property
    def cleaned_display(self):
        return "\n".join([s.rstrip() for s in self.display if s.rstrip()])


def shell() -> Spawn:
    s = Spawn("envo test")
    return s


def bash() -> Spawn:
    s = Spawn("bash")
    return s


def run(cmd: str):
    return pexpect.run(cmd).decode("utf-8")


def single_command(command: str) -> str:
    return run(f'envo test -c "{command}"')


def init_child_env(child_dir: Path) -> None:
    cwd = Path(".").absolute()
    if child_dir.exists():
        shutil.rmtree(child_dir, ignore_errors=True)

    child_dir.mkdir()
    os.chdir(str(child_dir))
    result = run("envo test --init")
    assert "Created test environment" in result

    comm_file = Path("env_comm.py")
    content = comm_file.read_text()
    content = content.replace("parent: Optional[str] = None", 'parent = ".."')
    comm_file.write_text(content)

    os.chdir(str(cwd))


def trigger_reload(file: Path = Path("env_comm.py")) -> None:
    file.write_text(file.read_text() + "\n")
    sleep(0.5)


def replace_last_occurence(string: str, what: str, to_what: str) -> str:
    if what not in string:
        raise RuntimeError('"what" string not found in input string')

    # ugh, ugly...
    ret = string[::-1].replace(what[::-1], to_what[::-1], 1)[::-1]
    return ret
