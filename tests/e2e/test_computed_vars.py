from envo.env import ComputedVarError
from tests.e2e import utils
from tests.e2e.utils import PromptState


class TestComputedVars(utils.TestBase):
    def test_basic_with_declaration(self, shell):
        utils.add_declaration(
        """
        def compute(self) -> int:
            return 10
        computed: int = computed_var(fget=compute)
        """)

        e = shell.start()
        e.prompt().eval()

        shell.sendline("$SANDBOX_COMPUTED")
        e.output(r"'10'\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_basic_setter(self, shell):
        utils.add_declaration(
        """
        def compute(self) -> int:
            return 10
        def compute_set(self, value) -> int:
            self.computed = value * 2
        computed: int = computed_var(fget=compute, fset=compute_set)
        """)

        e = shell.start()
        e.prompt().eval()

        shell.sendline("$SANDBOX_COMPUTED")
        e.output(r"'10'\n")
        e.prompt().eval()

        shell.exit()
        e.exit().eval()

    def test_error_in_property(self, shell):
        utils.add_declaration("computed: int")
        utils.add_method("""
        def compute(self) -> int:
            return 1 / 0 
        computed: int = computed_var(fget=compute)
        """)

        e = shell.start()
        e.output(r".*ZeroDivisionError.*")
        e.prompt(state=PromptState.EMERGENCY_MAYBE_LOADING).eval()

        shell.exit()
        e.exit().eval()
