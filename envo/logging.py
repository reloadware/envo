import sys
from typing import List

from dataclasses import dataclass
from loguru import logger as loguru_logger
from rhei import Stopwatch


@dataclass
class Msg:
    level: str
    body: str
    time: float

    def __post_init__(self) -> None:
        self.body = str(self.body).lstrip()


Levels = {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 2,
    "ERROR": 3,
}


class Logger:
    messages: List[Msg]
    level: str

    def __init__(self) -> None:
        self.messages = []
        self.level = ""
        self.set_level("INFO")
        self.sw = Stopwatch()
        self.sw.start()

        loguru_logger.remove()
        loguru_logger.add(
            sys.stdout, format="<blue>{message}</blue>", level="DEBUG", filter=lambda x: x["level"].name == "DEBUG",
        )
        loguru_logger.add(
            sys.stdout, format="<bold>{message}</bold>", level="INFO", filter=lambda x: x["level"].name == "INFO",
        )
        loguru_logger.add(
            sys.stderr,
            format="<bold><yellow>{message}</yellow></bold>",
            level="WARNING",
            filter=lambda x: x["level"].name == "WARNING",
        )
        loguru_logger.add(
            sys.stderr,
            format="<bold><red>{message}</red></bold>",
            level="ERROR",
            filter=lambda x: x["level"].name == "ERROR",
        )

    def clean(self) -> None:
        self.messages = []

    def set_level(self, level: str) -> None:
        self.level = level

    def debug(self, message: str) -> None:
        msg = Msg("DEBUG", message, self.sw.value)
        self._add_msg(msg)

    def info(self, message: str) -> None:
        msg = Msg("INFO", message, self.sw.value)
        self._add_msg(msg)

    def warning(self, message: str) -> None:
        msg = Msg("WARNING", message, self.sw.value)
        self._add_msg(msg)

    def error(self, message: str) -> None:
        msg = Msg("ERROR", message, self.sw.value)
        self._add_msg(msg)

    def _add_msg(self, msg: Msg) -> None:
        self.messages.append(msg)
        if Levels[msg.level] >= Levels[self.level]:
            loguru_logger.log(msg.level, msg.body, self.sw.value)

    def print_all(self, add_time: bool = True) -> None:
        for m in self.messages:
            if add_time:
                time = ":" + f"{m.time:.2f}s"
            else:
                time = ""
            loguru_logger.log(m.level, f"[{m.level}{time}] " + m.body)


logger = Logger()
