import os
from pathlib import Path

import pytest

from tests.e2e import utils


class TestVenv(utils.TestBase):
    def assert_activated(self, shell, dir_where_is_venv="sandbox", activated_from="sandbox", venv_name=".venv") -> None:
        e = shell.expecter
        shell.sendline("import url_regex")

        e.prompt(name=activated_from)
        shell.sendline("print(url_regex.UrlRegex)")
        e.output(r"<class 'url_regex\.url_regex\.UrlRegex'>\n")
        e.prompt(name=activated_from).eval()

        path = shell.envo.get_env_field("path")

        venv_path = f"{dir_where_is_venv}/{venv_name}"

        assert f"{venv_path}/bin" in path
        assert path.count(f"{venv_path}/bin") == 1

        sys_path = shell.envo.get_sys_path()
        assert len([p for p in sys_path if f'sandbox/{venv_name}/lib/python3.6/site-packages' in p]) == 1

    def assert_predicted(self, shell, venv_name=".venv") -> None:
        path = shell.envo.get_env_field("path")
        assert f"sandbox/{venv_name}/bin" in path
        assert path.count(f"sandbox/{venv_name}/bin") == 1

        sys_path = shell.envo.get_sys_path()
        assert len([p for p in sys_path if f'sandbox/{venv_name}/lib/python' in p]) > 10

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

        shell.exit()
        e.exit().eval()

    def test_venv_addon_no_venv(self, shell):
        utils.add_plugins("VirtualEnv")
        utils.replace_in_code("pass", "VirtualEnv.init(self, venv_path=self.root)")

        e = shell.start()
        e.prompt().eval()

        self.assert_predicted(shell)

        shell.exit()
        e.exit().eval()

    def test_autodiscovery(self, shell, init_child_env):
        utils.run("poetry run python -m venv .venv")
        utils.run("./.venv/bin/pip install url-regex")

        os.chdir("child")

        utils.add_plugins("VirtualEnv")

        e = shell.start()
        e.prompt(name="child", state=utils.PromptState.MAYBE_LOADING).eval()

        self.assert_activated(shell, activated_from="child")

        shell.exit()
        e.exit().eval()

    def test_autodiscovery_cant_find(self, shell):
        utils.add_plugins("VirtualEnv")
        utils.replace_in_code("pass", "VirtualEnv.init(self, venv_dir_name='.some_venv')")

        e = shell.start()
        e.prompt().eval()

        self.assert_predicted(shell, venv_name=".some_venv")

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

        self.assert_activated(shell, venv_name='.custom_venv', activated_from="child")

        shell.exit()
        e.exit().eval()

