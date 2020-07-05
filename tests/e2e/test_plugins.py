from tests.e2e import utils


class TestPlugins(utils.TestBase):
    def test_venv_addon(self):
        utils.run("poetry run python -m venv .venv")
        utils.run("./.venv/bin/pip install rhei==0.5.2")
        utils.run("envo test --init=venv")
        utils.add_plugin("VirtualEnv")

        s = utils.shell()
        e = s.expecter
        e.prompt().eval()

        s.sendline("import rhei")
        e.prompt()
        s.sendline("print(rhei.stopwatch)")
        e.output(r"<module 'rhei\.stopwatch' from .*\n")
        e.prompt()

        s.exit()
        e.exit().eval()

    def test_venv_addon_no_venv(self):
        utils.add_plugin("VirtualEnv")

        s = utils.shell()
        e = s.expecter
        e.prompt().eval()

        s.exit()
        e.exit().eval()
