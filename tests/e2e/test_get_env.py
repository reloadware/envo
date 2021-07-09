import os
from pathlib import Path
from tests.e2e import utils

from tests.utils import add_imports_in_envs_in_dir


class TestGetEnv(utils.TestBase):
    def test_simple(self, init_other_env, shell, sandbox, envo_imports):
        add_imports_in_envs_in_dir()
        e = shell.start()
        e.prompt().eval()

        shell.sendline("flake_all")
        e.output(r"Flake root ok\nFlake other ok\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_reloads_after_get_env(self, init_other_env, shell, sandbox, envo_imports):
        add_imports_in_envs_in_dir()
        e = shell.start()
        e.prompt().eval()

        shell.sendline("flake_all")
        e.output(r"Flake root ok\nFlake other ok\n").prompt().eval()

        shell.trigger_reload()

        shell.envo.assert_reloaded()

        shell.exit()
        e.exit().eval()
