import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from envo.misc import is_windows

STICKYBEAK_PORT = 5416


if TYPE_CHECKING:
    from envo.scripts import EnvoBase


__all__ = ["envo", "enabled", "stickybeak_enabled"]

envo: Optional["EnvoBase"] = None

enabled = "ENVO_E2E_TEST" in os.environ
stickybeak_enabled = "ENVO_E2E_STICKYBEAK" in os.environ

server = None


class ReloadTimeout(Exception):
    pass


class ReadyTimeout(Exception):
    pass


if enabled:
    import os

    import stickybeak

    if is_windows():
        import prompt_toolkit.output.windows10

        prompt_toolkit.output.windows10.is_win_vt100_enabled = lambda: True

        import prompt_toolkit.output.win32

        def flush(self):
            if not self._buffer:
                self.stdout.flush()
                return

            data = "".join(self._buffer)

            for b in data:
                self.stdout.write(b)

            self.stdout.flush()
            self._buffer = []

        prompt_toolkit.output.win32.Win32Output.flush = flush

        import prompt_toolkit.input
        import prompt_toolkit.input.defaults

        def create_input():
            from prompt_toolkit.input.win32_pipe import Win32PipeInput

            input = Win32PipeInput()

            def collector():
                while True:
                    char = sys.stdin.read(1)
                    input.send_text(char)
                    input.flush()
                    if "\x04" in char:
                        return

            from threading import Thread

            Thread(target=collector).start()

            return input

        prompt_toolkit.input.create_input = create_input
        prompt_toolkit.input.defaults.create_input = create_input

if stickybeak_enabled:
    project_root = Path(__file__).parent
    server = stickybeak.Server(project_root, int(os.environ["ENVO_E2E_STICKYBEAK_PORT"]), timeout=15.0)
    server.start()


def on_exit():
    if stickybeak_enabled:
        server.exit()
