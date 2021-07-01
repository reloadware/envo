import re
import sys
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import loguru
from loguru._colorizer import Colorizer
from pygments.styles import get_style_by_name
from rhei import Stopwatch
from xonsh.pyghooks import XonshConsoleLexer


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
    descriptor: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.body = str(self.body).lstrip()

    def print(self) -> None:
        print(self.render_all(with_color=True))

    def _fix_formatting(self, text: str) -> str:
        from loguru._colorizer import AnsiParser

        parser = AnsiParser()

        for match in parser._regex_tag.finditer(text):
            markup, tag = match.group(0), match.group(1)

            if tag not in {"lvl", "level"}:
                ansi = parser._get_ansicode(tag)
                if ansi is None:
                    text = text.replace(
                        markup, markup.replace("<", "< ").replace(">", " >")
                    )

        return text

    def render_message(self, with_color: bool = True) -> str:
        def color(clr: str) -> str:
            if with_color:
                return clr
            else:
                return ""

        from pygments import highlight
        from pygments.formatters.terminal import TerminalFormatter

        metadata = ""
        if self.metadata:
            metadata = str(self.metadata)

        descriptor = ""
        if self.descriptor:
            descriptor = (
                f"{color('<green>')}({str(self.descriptor)}) {color('</green>')}"
            )
        msg = f"@{self.time:.4f}]{descriptor}{self.body}; {metadata}"

        if with_color:
            # fix escaping colors
            msg = self._fix_formatting(msg)
            msg = highlight(
                msg,
                XonshConsoleLexer(),
                TerminalFormatter(style=get_style_by_name("emacs")),
            )
            msg = Colorizer.ansify(msg)
        return msg

    def render_all(self, with_color: bool = True) -> str:
        return f"[{self.level.name:<5}{self.render_message(with_color=with_color)}"

    def __repr__(self) -> str:
        return self.render_all(with_color=False)


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
        return (
            self.matches_level(msg)
            and self.matches_body(msg)
            and self.matches_time_later(msg)
            and self.matches_time_before(msg)
            and self.matches_metadata(msg)
        )


class Messages(list):
    content = List[Msg]

    def print(self) -> None:
        ret = []

        for m in self:
            m.print()

        ret = "\n".join(ret)

        print(ret)


class Logger:
    messages: Messages
    level: Level
    parent: Optional["Logger"]
    descriptor: Optional[str]
    name: str

    def __init__(
        self,
        name: str,
        parent: Optional["Logger"] = None,
        descriptor: Optional[str] = None,
    ) -> None:
        self.name = name
        self.parent = parent
        self.descriptor = descriptor

        self.messages = Messages()
        self.level = Level.INFO

        self.set_level(Level.INFO)

        self.sw = Stopwatch()
        self.sw.start()

        loguru.logger.remove()
        loguru.logger.add(
            sys.stdout,
            format="<blue>{message}</blue>",
            level="DEBUG",
            filter=lambda x: x["level"].name == "DEBUG",
        )
        loguru.logger.add(
            sys.stdout,
            format="<bold>{message}</bold>",
            level="INFO",
            filter=lambda x: x["level"].name == "INFO",
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

    def create_child(self, name: str, descriptor: str) -> "Logger":
        logger = Logger(parent=self, name=name, descriptor=descriptor)
        logger.sw = self.sw
        return logger

    def clean(self) -> None:
        self.messages = Messages()

    def set_level(self, level: Level) -> None:
        self.level = level

    def _log(self, msg: Msg) -> None:
        self.messages.append(msg)

    def log(
        self,
        message: str,
        level: Level,
        metadata: Optional[Dict[str, Any]] = None,
        print_msg=False,
    ) -> None:
        msg = Msg(
            level,
            message,
            self.sw.value,
            metadata=metadata or {},
            descriptor=self.descriptor,
        )
        if print_msg:
            loguru.logger.log(level.name, message)

        self._log(msg)

        if self.parent:
            self.parent._log(msg)

    def debug(
        self, message: str, metadata: Optional[Dict[str, Any]] = None, print_msg=False
    ) -> None:
        self.log(message, Level.DEBUG, metadata, print_msg)

    def info(
        self, message: str, metadata: Optional[Dict[str, Any]] = None, print_msg=False
    ) -> None:
        self.log(message, Level.INFO, metadata, print_msg)

    def warning(
        self, message: str, metadata: Optional[Dict[str, Any]] = None, print_msg=False
    ) -> None:
        self.log(message, Level.WARNING, metadata, print_msg)

    def error(
        self, message: str, metadata: Optional[Dict[str, Any]] = None, print_msg=False
    ) -> None:
        self.log(message, Level.ERROR, metadata, print_msg)

    #
    # def get_user_code_exception(root: Path) -> str:
    #     lines = traceback.format_exception(*sys.exc_info())
    #     users_code = False
    #     ret = []
    #     for l in lines:
    #         if str(root) in l:
    #             users_code = True
    #         if not users_code:
    #             continue
    #
    #         if l.startswith("  "):
    #             l = l[2:]
    #
    #         ret.append(l)
    #
    #     return "".join(ret)

    def traceback(self) -> None:
        lines = traceback.format_exception(*sys.exc_info())
        text = "".join(lines).strip()
        self.log(text, level=Level.ERROR, print_msg=True)

    def get_msgs(self, filter: MsgFilter) -> List[Msg]:
        filtered: List[Msg] = []
        for m in self.messages:
            if filter.matches_all(m):
                filtered.append(m)

        return filtered

    def print_all(self) -> None:
        for m in self.messages:
            m.print()

    def tail(self, messages_n: int) -> None:
        for m in self.messages[-messages_n:]:
            m.print()

    def save(self, file: Path) -> None:
        pass


logger = Logger(name="root")
