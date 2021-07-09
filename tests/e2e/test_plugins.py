import os
from pathlib import Path

from tests.e2e import utils
from tests import facade


def add_venv_plugin(parent_env: str = "Env"):
    utils.replace_in_code(f"({parent_env})", f"({parent_env}, VirtualEnv)", file="env_comm.py")


class TestVenv(utils.TestBase):
    def assert_activated(
        self,
        shell,
        venv_dir: Path,
        activated_from="sandbox",
        venv_name=".venv",
    ) -> None:
        e = shell.expecter
        shell.sendline("import url_regex")

        e.prompt(name=activated_from)
        shell.sendline("print(url_regex.UrlRegex)")
        e.output(r"<class 'url_regex\.url_regex\.UrlRegex'>\n")
        e.prompt(name=activated_from).eval()

        path = shell.envo.get_os_environ()["PATH"]

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
        assert set(str(p) for p in venv_path.possible_site_packages).issubset(
            set(sys_path)
        )

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
        utils.replace_in_code(
            "# Declare your command namespaces here",
            'VirtualEnv.customise(venv_path=root)',
        )

        e = shell.start()
        e.prompt().eval()

        self.assert_predicted(shell, venv_dir=sandbox)

        utils.run("python -m venv .venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        self.assert_activated(shell, venv_dir=sandbox)

        shell.exit()
        e.exit().eval()

    def test_autodiscovery(self, shell, init_child_env, sandbox):
        utils.add_imports_in_envs_in_dir()
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".venv")

        utils.run("python -m venv .venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        os.chdir("child")

        add_venv_plugin("ParentEnv")

        e = shell.start()
        e.prompt(name="child", state=utils.PromptState.MAYBE_LOADING).eval()

        self.assert_activated(shell, venv_dir=sandbox, activated_from="child")

        shell.exit()
        e.exit().eval()

    def test_autodiscovery_cant_find(self, sandbox, shell):
        add_venv_plugin()

        utils.replace_in_code(
            "# Declare your command namespaces here",
            'VirtualEnv.customise(venv_name=".some_venv")',
        )

        e = shell.start()
        e.prompt().eval()

        self.assert_predicted(shell, venv_dir=sandbox, venv_name=".some_venv")

        shell.exit()
        e.exit().eval()

    def test_custom_venv_name(self, shell, sandbox, init_child_env):
        utils.add_imports_in_envs_in_dir()
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".custom_venv")

        utils.run("python -m venv .custom_venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        os.chdir("child")

        add_venv_plugin("ParentEnv")
        utils.replace_in_code(
            "# Declare your command namespaces here",
            'VirtualEnv.customise(venv_name=".custom_venv")',
        )

        e = shell.start()
        e.prompt(name="child").eval()

        self.assert_activated(
            shell, venv_dir=sandbox, venv_name=".custom_venv", activated_from="child"
        )

        shell.exit()
        e.exit().eval()

    def test_at_load_time(self, shell, sandbox):
        venv_path = facade.VenvPath(root_path=sandbox, venv_name=".venv")
        utils.run("python -m venv .venv")
        utils.run(f"{str(venv_path.bin_path / 'pip')} install url-regex")

        utils.replace_in_code("# Declare your command namespaces here", "VirtualEnv().init()", file="env_comm.py")

        e = shell.start()
        e.prompt().eval()

        self.assert_activated(shell, venv_dir=sandbox)

        shell.exit()
        e.exit().eval()
