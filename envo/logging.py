import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional

from dataclasses import dataclass, field
import loguru
from rhei import Stopwatch


class Level(Enum):
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3


@dataclass
class Msg:
    level: Level
    body: str
    time: float  # s
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.body = str(self.body).lstrip()

    def print(self) -> None:
        body = self.body
        time = ":" + f"{self.time:.2f}s"
        metadata = json.dumps(self.metadata)
        loguru.logger.log(self.level.name, f"[{self.level.name}{time}] {body}; {metadata}")

    def __repr__(self) -> str:
        return f"[{self.level.name}@{self.time:.4f}s] {self.body}; {self.metadata}"


@dataclass
class MsgFilter:
    level: Optional[Level] = None
    body_re: Optional[str] = None
    time_later: Optional[float] = None
    time_before: Optional[float] = None
    metadata_re: Optional[Dict[str, Any]] = None

    # matchers
    def matches_level(self, msg: Msg) -> bool:
        return self.level is None or msg.level == self.level

    def matches_body(self, msg: Msg) -> bool:
        return self.body_re is None or bool(re.match(self.body_re, msg.body, re.DOTALL))

    def matches_time_later(self, msg: Msg) -> bool:
        return self.body_re is None or msg.time >= self.time_later

    def matches_time_before(self, msg: Msg) -> bool:
        return self.body_re is None or msg.time < self.time_before

    def matches_metadata(self, msg: Msg) -> bool:
        if not self.metadata_re:
            return True

        for k, v in self.metadata_re.items():
            msg_value = msg.metadata.get(k)
            if msg_value is None:
                return False

            if not re.match(v, msg_value, re.DOTALL):
                return False

        return True

    def matches_all(self, msg: Msg) -> bool:
        return self.matches_level(msg) and self.matches_body(msg) and self.matches_time_later(msg) and self.matches_time_before(msg) and self.matches_metadata(msg)


class Logger:
    messages: List[Msg]
    level: Level

    def __init__(self) -> None:
        self.messages = []
        self.level = Level.INFO

        self.set_level(Level.INFO)

        self.sw = Stopwatch()
        self.sw.start()

        loguru.logger.remove()
        loguru.logger.add(
            sys.stdout, format="<blue>{message}</blue>", level="DEBUG", filter=lambda x: x["level"].name == "DEBUG",
        )
        loguru.logger.add(
            sys.stdout, format="<bold>{message}</bold>", level="INFO", filter=lambda x: x["level"].name == "INFO",
        )
        loguru.logger.add(
            sys.stderr,
            format="<bold><yellow>{message}</yellow></bold>",
            level="WARNING",
            filter=lambda x: x["level"].name == "WARNING",
        )
        loguru.logger.add(
            sys.stderr,
            format="<bold><red>{message}</red></bold>",
            level="ERROR",
            filter=lambda x: x["level"].name == "ERROR",
        )

    def clean(self) -> None:
        self.messages = []

    def set_level(self, level: Level) -> None:
        self.level = level

    def log(self, message: str, level: Level, metadata: Optional[Dict[str, Any]] = None, print_msg=False):
        msg = Msg(level, message, self.sw.value, metadata=metadata or {})
        if print_msg:
            loguru.logger.log(level.name, message)

        self.messages.append(msg)

    def debug(self, message: str, metadata: Optional[Dict[str, Any]] = None, print_msg=False) -> None:
        self.log(message, Level.DEBUG, metadata, print_msg)

    def info(self, message: str, metadata: Optional[Dict[str, Any]] = None, print_msg=False) -> None:
        self.log(message, Level.INFO, metadata, print_msg)

    def warning(self, message: str, metadata: Optional[Dict[str, Any]] = None, print_msg=False) -> None:
        self.log(message, Level.WARNING, metadata, print_msg)

    def error(self, message: str, metadata: Optional[Dict[str, Any]] = None, print_msg=False) -> None:
        self.log(message, Level.ERROR, metadata, print_msg)

    def get_msgs(self, filter: MsgFilter) -> List[Msg]:
        filtered: List[Msg] = []
        for m in self.messages:
            if filter.matches_all(m):
                filtered.append(m)

        return filtered

    def print_all(self) -> None:
        for m in self.messages:
            m.print()

    def save(self, file: Path) -> None:
        pass


logger = Logger()
