from tests.e2e import utils
from tests.e2e.utils import PromptState


class TestComputedVars(utils.TestBase):
    def test_basic_with_declaration(self, shell):
        utils.add_declaration("computed: int")
        utils.add_method("""
        @property
        def computed(self) -> int:
            return 10
        """)

        e = shell.start()
        e.prompt().eval()

        shell.sendline("$SANDBOX_COMPUTED")
        e.output(r"'10'\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()
