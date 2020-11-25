import os
from pathlib import Path

from tests.e2e import utils


class TestVenv(utils.TestBase):
    def test_venv_addon(self, shell):
        utils.run("poetry run python -m venv .venv")
        utils.run("./.venv/bin/pip install url-regex")
        utils.add_plugins("VirtualEnv")

        shell.start()
        e = shell.expecter
        e.prompt().eval()

        shell.sendline("import url_regex")
        e.prompt()
        shell.sendline("print(url_regex.UrlRegex)")
        e.output(r"<class 'url_regex\.url_regex\.UrlRegex'>\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_venv_addon_no_venv(self, shell):
        utils.add_plugins("VirtualEnv")

        shell.start()
        e = shell.expecter
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_autodiscovery(self, shell, init_child_env):
        utils.run("poetry run python -m venv .venv")
        utils.run("./.venv/bin/pip install url-regex")

        os.chdir("child")

        utils.add_plugins("VirtualEnv")

        shell.start()
        e = shell.expecter
        e.prompt(name="child").eval()

        shell.sendline("import url_regex")
        e.prompt()
        shell.sendline("print(url_regex.UrlRegex)")
        e.output(r"<class 'url_regex\.url_regex\.UrlRegex'>\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()
