import os
from pathlib import Path
from subprocess import CalledProcessError

from pytest import raises

from envo.misc import is_linux, is_windows
from tests.e2e import utils


class TestGetEnv(utils.TestBase):
    def test_simple(self, shell, sandbox):
        other_dir = Path("other")
        other_dir.mkdir()

        os.chdir(other_dir)
        utils.run("envo test init")
        utils.add_command("""
        @command()
        def flake(self) -> str:
            print("Flake other ok")
        """)
        os.chdir(sandbox)

        utils.add_command("""
        @command()
        def flake_all(self) -> str:
            print("Flake root ok")
            other_env = self.get_env("other")
            other_env.flake()
        """)

        e = shell.start()
        e.prompt().eval()

        shell.sendline("flake_all")
        e.output(r"Flake root ok\nFlake other ok\n").prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_reloads_after_get_env(self, shell, sandbox):
        other_dir = Path("other")
        other_dir.mkdir()

        os.chdir(other_dir)
        utils.run("envo test init")
        utils.add_command("""
        @command()
        def flake(self) -> str:
            print("Flake other ok")
        """)
        os.chdir(sandbox)

        utils.add_command("""
        @command()
        def flake_all(self) -> str:
            print("Flake root ok")
            other_env = self.get_env("other")
            other_env.flake()
        """)

        e = shell.start()
        e.prompt().eval()

        shell.sendline("flake_all")
        e.output(r"Flake root ok\nFlake other ok\n").prompt().eval()

        shell.trigger_reload()

        shell.envo.assert_reloaded()

        shell.exit()
        e.exit().eval()
