import shutil

from pytest import fixture

from tests.e2e import utils


class TestBase:
    @fixture(autouse=True)
    def setup(self, sandbox, init):
        self.sample_project = sandbox / "sample_project"
        shutil.copytree(sandbox / "../sample_project", self.sample_project)


class TestSourceReload(TestBase):
    def test_importing(self, shell):
        utils.replace_in_code("sources: List[Source] = []", "sources: List[Source] = [Source(root / 'sample_project')]")
        utils.add_boot(["import carwash"])

        e = shell.start()
        e.prompt().eval()

        shell.sendline("print(carwash.sprayers.number_of_sprayers)")
        e.output("10\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_change_variable(self, shell):
        utils.replace_in_code("sources: List[Source] = []", "sources: List[Source] = [Source(root / 'sample_project')]")
        utils.add_boot(["import carwash"])

        e = shell.start()
        e.prompt().eval()

        shell.sendline("print(carwash.sprayers.number_of_sprayers)")
        e.output("10\n")
        e.prompt().eval()

        utils.replace_in_code("number_of_sprayers = 10", "number_of_sprayers = 15",
                              self.sample_project / "carwash/sprayers.py")

        shell.envo.wait_until_ready()
        shell.envo.assert_partially_reloaded(1)

        shell.sendline("print(carwash.sprayers.number_of_sprayers)")
        e.output("15\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_change_variable_not_imported(self, shell):
        utils.replace_in_code("sources: List[Source] = []", "sources: List[Source] = [Source(root / 'sample_project')]")

        e = shell.start()
        e.prompt().eval()

        utils.replace_in_code("number_of_sprayers = 10", "number_of_sprayers = 15",
                              self.sample_project / "carwash/sprayers.py")

        shell.envo.wait_until_ready()
        shell.envo.assert_partially_reloaded(0)

        shell.exit()
        e.exit().eval()

    def test_on_partial_reload(self, shell):
        utils.replace_in_code("sources: List[Source] = []", "sources: List[Source] = [Source(root / 'sample_project')]")
        utils.add_boot(["import carwash"])
        utils.add_on_partial_reload(
            """
            @on_partial_reload
            def _on_partial_reload(self, file: Path, actions):
                print("Reloaded!")
                self.redraw_prompt()
            """)

        e = shell.start()
        e.prompt(utils.PromptState.MAYBE_LOADING).eval()

        utils.replace_in_code("number_of_sprayers = 10", "number_of_sprayers = 15",
                              self.sample_project / "carwash/sprayers.py")

        shell.envo.wait_until_ready()
        shell.envo.assert_partially_reloaded(1)

        e.output("Reloaded!\n")
        e.prompt(utils.PromptState.MAYBE_LOADING).eval()

        shell.exit()
        e.exit().eval()
