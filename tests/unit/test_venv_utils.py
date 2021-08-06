import os
import re
from pathlib import Path

import pytest

from tests.facade import run, run_get, venv_utils
from tests.unit import utils


class TestVenvUtils(utils.TestBase):
    def test_ctx_manager(self, sandbox):
        run("python -m venv .venv")

        python_bin_path = run_get("which python").stdout
        activated_python_bin_path_re = r".*sandbox_.*/\.venv/bin/python"

        assert not re.match(activated_python_bin_path_re, python_bin_path)

        with venv_utils.Venv(path=".venv"):
            activated_python_bin_path = run_get("which python").stdout
            assert re.match(activated_python_bin_path_re, activated_python_bin_path)
