from textwrap import dedent

from tests.e2e import utils


class TestPythonpath(utils.TestBase):
    def test_basic(self, shell):
        utils.add_definition("self.e.pythonpath = 'test_path'")

        e = shell.start()
        e.prompt().eval()

        shell.sendline("$PYTHONPATH")
        e.output(dedent(r"""EnvPath\(\s*\['test_path'\]\s*\)\n"""))
        e.prompt().eval()

        sys_path = shell.envo.get_sys_path()

        assert "test_path" in sys_path

        shell.exit()
        e.exit().eval()
