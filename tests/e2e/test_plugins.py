import os
from pathlib import Path

import pytest

from tests.e2e import utils


class TestVenv(utils.TestBase):
    def assert_activated(self, shell, prompt_name="sandbox") -> None:
        e = shell.expecter
        shell.sendline("import url_regex")
        e.prompt(name=prompt_name)
        shell.sendline("print(url_regex.UrlRegex)")
        e.output(r"<class 'url_regex\.url_regex\.UrlRegex'>\n")
        e.prompt(name=prompt_name).eval()

    @pytest.mark.parametrize(
        "file",
        ["env_comm.py", "env_test.py"],
    )
    def test_venv_addon(self, file, shell):
        utils.run("poetry run python -m venv .venv")
        utils.run("./.venv/bin/pip install url-regex")
        utils.add_plugins("VirtualEnv", file=Path(file))

        e = shell.start()
        e.prompt().eval()

        self.assert_activated(shell)

        path = shell.envo.get_env_field("path")
        assert "sandbox/.venv/bin" in path
        assert path.count("sandbox/.venv/bin") == 1

        sys_path = shell.envo.get_sys_path()
        assert len([p for p in sys_path if 'sandbox/.venv/lib/python3.6/site-packages' in p]) == 1

        shell.exit()
        e.exit().eval()

    def test_venv_addon_no_venv(self, shell):
        utils.add_plugins("VirtualEnv")
        utils.replace_in_code("pass", "VirtualEnv.init(self, venv_path=self.root)")

        e = shell.start()
        e.prompt().eval()

        path = shell.envo.get_env_field("path")
        assert "sandbox/.venv/bin" in path
        assert path.count("sandbox/.venv/bin") == 1

        sys_path = shell.envo.get_sys_path()
        assert len([p for p in sys_path if 'sandbox/.venv/lib/python3.6/site-packages' in p]) == 1

        shell.exit()
        e.exit().eval()

    def test_autodiscovery(self, shell, init_child_env):
        utils.run("poetry run python -m venv .venv")
        utils.run("./.venv/bin/pip install url-regex")

        os.chdir("child")

        utils.add_plugins("VirtualEnv")

        e = shell.start()
        e.prompt(name="child").eval()

        self.assert_activated(shell, prompt_name="child")

        shell.exit()
        e.exit().eval()

    def test_custom_venv_name(self, shell, init_child_env):
        utils.run("poetry run python -m venv .custom_venv")
        utils.run("./.custom_venv/bin/pip install url-regex")

        os.chdir("child")

        utils.add_plugins("VirtualEnv")
        utils.replace_in_code("pass", "VirtualEnv.init(self, venv_dir_name='.custom_venv')")

        e = shell.start()
        e.prompt(name="child").eval()

        self.assert_activated(shell, prompt_name="child")

        shell.exit()
        e.exit().eval()

