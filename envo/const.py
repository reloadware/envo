import inspect
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Optional

__all__ = ["STAGES", "emojis"]

DEFAULT_EMOJI = "🙂"


@dataclass
class Stage:
    name: str
    priority: int  # higher - activated first when no stage is provided
    emoji: str


class STAGES:
    COMM = Stage("comm", 90, "👌")
    LOCAL = Stage("local", 100, "🐣")
    TEST = Stage("test", 80, "🛠")
    CI = Stage("ci", 70, "🧪")
    STAGE = Stage("stage", 60, "🤖")
    PROD = Stage("prod", 50, "🔥")

    @classmethod
    def get_all_stages(cls) -> Dict[str, Stage]:
        ret = {}
        for _, obj in inspect.getmembers(cls):
            if isinstance(obj, Stage):
                ret[obj.name] = obj

        return ret

    @classmethod
    def get_stage_name_to_emoji(cls) -> Dict[str, str]:
        stages = cls.get_all_stages()

        ret = defaultdict(lambda: DEFAULT_EMOJI)
        for s in stages.values():
            ret[s.name] = s.emoji

        return ret

    @classmethod
    def filename_to_stage(cls, filename: str) -> Optional[Stage]:
        stages = cls.get_all_stages()
        matches_groups = re.search(r"env_(.*)\.py", filename)
        if not matches_groups:
            raise RuntimeError(f"Not an envo file ({filename})")

        matches = matches_groups.groups()
        stage_name = matches[0]

        stage = stages.get(stage_name, None)

        if not stage:
            stage = Stage(stage_name, priority=10, emoji=DEFAULT_EMOJI)

        return stage


emojis: Dict[str, str] = {"loading": "⏳", "emergency": "❌"}
