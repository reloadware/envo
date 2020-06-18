import os
import shutil
import sys
from pathlib import Path

import pexpect
import pytest
from pexpect import run

from tests.utils import add_command  # noqa F401
from tests.utils import add_declaration  # noqa F401
from tests.utils import add_definition  # noqa F401
from tests.utils import add_hook  # noqa F401
from tests.utils import change_file  # noqa F401
from tests.utils import flake_cmd  # noqa F401
from tests.utils import mypy_cmd  # noqa F401
from tests.utils import replace_in_code  # noqa F401
from tests.utils import add_context  # noqa F401

test_root = Path(os.path.realpath(__file__)).parent
envo_root = test_root.parent

prompt = r"[\(.*\)]*.*\$".encode()
envo_prompt = r"🛠\(sandbox\)".encode("utf-8") + prompt


class TestBase:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox, init):
        pass


def spawn(command: str) -> pexpect.spawn:
    s = pexpect.spawn(command, echo=False, timeout=4)
    s.logfile = sys.stdout.buffer
    return s


def shell(prompt: bytes = envo_prompt) -> pexpect.spawn:
    p = spawn("envo test --shell=simple")
    p.expect(prompt)
    return p


def init_child_env(child_dir: Path) -> None:
    cwd = Path(".").absolute()
    if child_dir.exists():
        shutil.rmtree(child_dir)

    child_dir.mkdir()
    os.chdir(str(child_dir))
    result = run("envo test --init")
    assert result == b"\x1b[1mCreated test environment \xf0\x9f\x8d\xb0!\x1b[0m\r\n"

    comm_file = Path("env_comm.py")
    content = comm_file.read_text()
    content = content.replace("parent = None", 'parent = ".."')
    comm_file.write_text(content)

    os.chdir(str(cwd))
