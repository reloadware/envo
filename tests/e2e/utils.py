import atexit
import fcntl
import os
import re
import shutil
import signal
import subprocess
import sys
from collections import Callable
from enum import Enum
from pathlib import Path
from subprocess import Popen
from threading import Thread
from time import sleep
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Set

import pexpect
import pyte
import pyte.modes
import pytest
import requests
from rhei import Stopwatch
from stickybeak import Injector

from envo import Env, const
from envo.e2e import STICKYBEAK_PORT
from envo.logging import Logger
from envo.misc import Inotify
from envo.shell import PromptBase
from tests.utils import add_boot  # noqa F401
from tests.utils import add_command  # noqa F401
from tests.utils import add_context  # noqa F401
from tests.utils import add_declaration  # noqa F401
from tests.utils import add_definition  # noqa F401
from tests.utils import add_flake_cmd  # noqa F401
from tests.utils import add_hook  # noqa F401
from tests.utils import add_mypy_cmd  # noqa F401
from tests.utils import add_namespace  # noqa F401
from tests.utils import add_plugins  # noqa F401
from tests.utils import change_file  # noqa F401
from tests.utils import replace_in_code  # noqa F401

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent


injector = Injector(address=f"http://localhost:{STICKYBEAK_PORT}")


if TYPE_CHECKING:
    from envo.scripts import EnvoBase


class PromptState(Enum):
    LOADING = 0
    NORMAL = 1
    EMERGENCY = 2
    MAYBE_LOADING = 3
    EMERGENCY_MAYBE_LOADING = 4


class PromptRe(PromptBase):
    default = r"[\(.*\)]*.*?\$ ?"

    def __init__(
        self,
        state: PromptState,
        name: str,
        emoji=const.STAGES.get_stage_name_to_emoji()["test"],
    ) -> None:
        super().__init__()

        self.state = state
        self.name = name
        self.emoji = emoji

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
    def __init__(self, spawn: "SpawnEnvo", stage: str) -> None:
        self._spawn = spawn
        self.stage = stage
        self.expected: List[str] = []
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

    def prompt(
        self, state=PromptState.NORMAL, name="sandbox", emoji: Optional[str] = None
    ) -> "Expecter":
        if not emoji:
            emoji = const.STAGES.get_stage_name_to_emoji()[self.stage]
        self.expected.append(str(PromptRe(state=state, name=name, emoji=emoji)))
        return self

    def exit(self, return_code=0) -> "Expecter":
        self._expect_exit = True
        self._return_code = return_code
        return self

    @property
    def expected_regex(self):
        return "".join(self.expected)

    def pop(self) -> None:
        self.expected.pop()

    def eval(self, timeout: int = 4) -> None:
        def condition():
            return re.fullmatch(
                self.expected_regex, self._spawn.get_cleaned_display(), re.DOTALL
            )

        AssertInTime(condition, timeout)

        if self._expect_exit:
            self._spawn.stop_collecting = True

            # check if has exited
            def condition():
                return self._spawn.process.poll() == self._return_code

            try:
                AssertInTime(condition, timeout)
            except AssertInTime.TIMEOUT:
                raise AssertInTime.TIMEOUT(
                    f"Process has not exit on time with proper exit code (last exit code = {self._spawn.process.poll()})"
                )


class SpawnEnvo:
    process: Optional[Popen] = None

    @injector.klass
    class RemoteEnvo:
        @classmethod
        def get_logger(cls) -> "Logger":
            from envo.logging import logger

            return logger

        @classmethod
        def get_env_field(cls, field: str) -> Any:
            import envo.e2e

            return getattr(envo.e2e.envo.mode.env, field)

        @classmethod
        def get_sys_path(cls) -> List[str]:
            import sys

            return sys.path

        @classmethod
        def get_os_environ(cls) -> Dict[str, str]:
            import os

            return dict(os.environ)

        @classmethod
        def wait_until_ready(cls, timeout=2) -> None:
            from time import sleep

            import envo.e2e
            from envo.e2e import ReadyTimeout

            passed_time = 0.0
            sleep_time = 0.01
            while True:
                sleep(sleep_time)
                passed_time += sleep_time

                if not envo.e2e.envo.mode:
                    continue

                mode = envo.e2e.envo.mode
                if mode.status.ready:
                    break

                if passed_time >= timeout:
                    raise ReadyTimeout

            sleep(0.2)

        @classmethod
        def assert_reloaded(
            cls, number: int = 1, path="env_test.py", timeout=2
        ) -> None:
            from time import sleep

            from envo import logger, logging
            from envo.e2e import ReloadTimeout

            passed_time = 0.0
            sleep_time = 0.05
            while True:
                sleep(sleep_time)
                passed_time += sleep_time

                msgs = logger.get_msgs(
                    filter=logging.MsgFilter(metadata_re={"type": r"reload"})
                )
                if number == 0 and len(msgs) == 0:
                    break

                if len(msgs) == number and str(msgs[-1].metadata["path"]).endswith(
                    path
                ):
                    break

                if passed_time >= timeout:
                    raise ReloadTimeout

            cls.wait_until_ready()

    def __init__(self, stage: str = "", debug=True):
        self.screen = pyte.Screen(200, 50)
        self.stream = pyte.ByteStream(self.screen)
        self.stage = stage

        self.command = f"envo {stage}"

        self.expecter = None
        self._buffer = []

        self.stop_collecting = False
        self._printed_info = False
        self.debug = debug

    def start(self, wait_until_ready=True) -> Expecter:
        environ = os.environ.copy()
        if self.debug:
            environ["ENVO_E2E_TEST"] = "True"
        environ["PYTHONUNBUFFERED"] = "True"
        environ["ENVO_SHELL_NOHISTORY"] = "True"

        if self.process:
            self.on_exit()

        self.process = Popen(
            self.command.split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            env=environ,
        )
        fcntl.fcntl(
            self.process.stdout,
            fcntl.F_SETFL,
            fcntl.fcntl(self.process.stdout, fcntl.F_GETFL) | os.O_NONBLOCK,
        )

        self.expecter = Expecter(self, stage=self.stage)

        if self.debug:
            injector.connect()

        if wait_until_ready and self.debug:
            self.envo.wait_until_ready()

        return self.expecter

    def exit(self) -> None:
        if self.process.poll() is not None:
            return

        self.print_info()

        self.send("\x04", expect=False)

    def on_exit(self) -> None:
        self.print_info()
        if self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGINT)
        self.process.send_signal(signal.SIGINT)
        self.process.send_signal(signal.SIGKILL)

    @property
    def envo(self) -> Type["SpawnEnvo.RemoteEnvo"]:
        return SpawnEnvo.RemoteEnvo

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

    def trigger_reload(self, file: Path = Path("env_test.py")) -> None:
        file.write_text(file.read_text() + "\n")
        self.envo.wait_until_ready()

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

    def get_display(self):
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

    def get_cleaned_display(self):
        return "\n".join([s.rstrip() for s in self.get_display() if s.rstrip()])

    def print_info(self):
        if not self.debug:
            return

        if self._printed_info:
            return

        self._printed_info = True

        print("\nDisplay:")
        print(self.get_cleaned_display())
        expected_multiline = self.expecter.expected_regex.replace(r"\n", "\n")
        print(f"\nExpected (multiline):\n{expected_multiline}")
        print(f"\nExpected (raw):\n{self.expecter.expected_regex}")

        try:
            print("\nLog:")
            self.envo.get_logger().print_all()
        except requests.exceptions.ConnectionError:
            print("COuldn't retrieve log")


def shell() -> SpawnEnvo:
    s = SpawnEnvo("test")
    return s


def comm_shell() -> SpawnEnvo:
    s = SpawnEnvo("comm")
    return s


def default_shell() -> SpawnEnvo:
    s = SpawnEnvo()
    return s


def bash() -> SpawnEnvo:
    s = SpawnEnvo("bash")
    return s


def run(cmd: str):
    return pexpect.run(cmd).decode("utf-8")


def single_command(command: str) -> str:
    return run(f'envo test -c "{command}"')


def envo_run(command: str) -> str:
    return run(f"envo run {command}")


def init_child_env(child_dir: Path) -> None:
    cwd = Path(".").absolute()
    if child_dir.exists():
        shutil.rmtree(child_dir, ignore_errors=True)

    child_dir.mkdir()
    os.chdir(str(child_dir))
    result = run("envo init test")
    assert "Created test environment" in result

    comm_file = Path("env_comm.py")
    content = comm_file.read_text()
    content = content.replace("parents: List[str] = []", 'parents = ["../env_comm.py"]')
    comm_file.write_text(content)

    test_file = Path("env_test.py")
    content = test_file.read_text()
    content = content.replace(
        'parents: List[str] = ["env_comm.py"]',
        'parents = ["env_comm.py", "../env_test.py"]',
    )
    test_file.write_text(content)

    os.chdir(str(cwd))


def replace_last_occurence(string: str, what: str, to_what: str) -> str:
    if what not in string:
        raise RuntimeError('"what" string not found in input string')

    # ugh, ugly...
    ret = string[::-1].replace(what[::-1], to_what[::-1], 1)[::-1]
    return ret


def trigger_reload(file: Path = Path("env_test.py")) -> None:
    file.write_text(file.read_text() + "\n")
