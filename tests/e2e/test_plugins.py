import os
from pathlib import Path

from tests import facade
from tests.e2e import utils
from tests.e2e.utils import PromptState, flaky


def add_venv_plugin(parent_env: str = "Env"):
    utils.replace_in_code(f"({parent_env})", f"({parent_env}, VirtualEnv)", file="env_comm.py")
    utils.replace_in_code(
        f"class Ctx({parent_env}.Ctx)", f"class Ctx({parent_env}.Ctx, VirtualEnv.Ctx)", file="env_comm.py"
    )
    utils.replace_in_code(
        f"class Environ({parent_env}.Environ)",
        f"class Environ({parent_env}.Environ, VirtualEnv.Environ)",
        file="env_comm.py",
    )


class TestVenv(utils.TestBase):
    def assert_activated(
        self,
        shell,
        venv_dir: Path,
        activated_from="sandbox",
        venv_name=".venv",
    ) -> None:
        e = shell.expecter
        shell.sendline("import url_regex;print(url_regex.UrlRegex)")
        e.output(r"<class 'url_regex\.url_regex\.UrlRegex'>\n")
        e.prompt(name=activated_from).eval()

        path = [str(p) for p in shell.envo.get_env_field("path")]

        venv_path = facade.VenvPath(root_path=venv_dir, venv_name=venv_name)

        assert path.count(str(venv_path.bin_path)) == 1

        site_packages_path = venv_path.site_packages_path

        sys_path = shell.envo.get_sys_path()
        assert sys_path.count(str(site_packages_path)) == 1

    def assert_predicted(self, shell, venv_dir: Path, venv_name=".venv") -> None:
        venv_path = facade.VenvPath(root_path=venv_dir, venv_name=venv_name)
        path = shell.envo.get_env_field("path")
        assert path.count(str(venv_path.bin_path)) == 1

        sys_path = shell.envo.get_sys_path()
        assert set(str(p) for p in venv_path.possible_site_packages).issubset(set(sys_path))

    @flaky
    def test_venv_addon(self, shell, sandbox):
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".venv")
        utils.run("python -m venv .venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        add_venv_plugin()

        e = shell.start()
        e.prompt().eval()

        self.assert_activated(shell, venv_dir=sandbox)

        shell.exit()
        e.exit().eval()

    def test_venv_addon_no_venv(self, sandbox, shell):
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".venv")

        add_venv_plugin()
        utils.add_definition("self.ctx.venv.dir = self.meta.root")

        e = shell.start()
        e.prompt(PromptState.MAYBE_LOADING).eval()

        self.assert_predicted(shell, venv_dir=sandbox)

        utils.run("python -m venv .venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        self.assert_activated(shell, venv_dir=sandbox)

        shell.exit()
        e.exit().eval()

    @flaky
    def test_discover(self, shell, init_child_env, sandbox):
        utils.add_imports_in_envs_in_dir()
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".venv")

        utils.run("python -m venv .venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        os.chdir("child")

        add_venv_plugin("ParentEnv")
        utils.add_definition("self.ctx.venv.discover = True")

        e = shell.start()
        e.prompt(name="child", state=utils.PromptState.MAYBE_LOADING).eval()

        self.assert_activated(shell, venv_dir=sandbox, activated_from="child")

        shell.exit()
        e.exit().eval()

    @flaky
    def test_binary(self, shell, sandbox):
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".venv")
        utils.run("python -m venv .venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install twine")

        add_venv_plugin()

        utils.add_command(
            """
        @command
        def run_bin(self):
            run("twine -h")
        """
        )

        e = shell.start()
        e.prompt().eval()

        shell.sendline("run_bin")
        e.output(r".*usage: twine.*").eval()

        shell.exit()
        e.exit().eval()

    @flaky
    def test_autodiscovery_cant_find(self, sandbox, shell):
        add_venv_plugin()

        utils.add_definition('self.ctx.venv.name=".some_venv"')
        utils.add_definition("self.ctx.venv.discover = True")

        e = shell.start()
        e.prompt().eval()

        self.assert_predicted(shell, venv_dir=sandbox, venv_name=".some_venv")

        shell.exit()
        e.exit().eval()

    @flaky
    def test_custom_venv_name(self, shell, sandbox, init_child_env):
        utils.add_imports_in_envs_in_dir()
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".custom_venv")

        utils.run("python -m venv .custom_venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        os.chdir("child")

        add_venv_plugin("ParentEnv")
        utils.add_definition('self.ctx.venv.name=".custom_venv"')
        utils.add_definition("self.ctx.venv.discover = True")

        e = shell.start()
        e.prompt(name="child").eval()

        self.assert_activated(shell, venv_dir=sandbox, venv_name=".custom_venv", activated_from="child")

        shell.exit()
        e.exit().eval()

    @flaky
    def test_at_load_time(self, shell, sandbox):
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".venv")
        utils.run("python -m venv .venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        utils.replace_in_code(
            "# Declare your command namespaces here", "venv_utils.Venv('.venv').activate()", file="env_comm.py"
        )

        e = shell.start()
        e.prompt().eval()

        self.assert_activated(shell, venv_dir=sandbox)

        shell.exit()
        e.exit().eval()
