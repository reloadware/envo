import os
from pathlib import Path

from tests.unit import utils


class TestParentChild(utils.TestBase):
    def test_parents_basic_functionality(self, init_child_env):
        sandbox_dir = Path(".").absolute()
        child_dir = sandbox_dir / "child"

        utils.replace_in_code('name = "sandbox"', 'name = "pa"')
        utils.add_declaration("test_parent_var: str")
        utils.add_definition('self.test_parent_var = "test_parent_value"')

        utils.replace_in_code(
            'name = "child"', 'name = "ch"', file=child_dir / "env_comm.py"
        )
        utils.add_declaration(
            "test_var: str", file=child_dir / "env_comm.py",
        )
        utils.add_definition(
            'self.test_var = "test_value"', file=child_dir / "env_comm.py",
        )

        child_env = utils.env(child_dir)

        assert child_env.get_parent() is not None
        assert child_env.test_var == "test_value"
        assert child_env.get_parent().test_parent_var == "test_parent_value"
        assert child_env.get_parent().get_name() == "pa"

        child_env.activate()
        assert os.environ["PA_TESTPARENTVAR"] == "test_parent_value"
        assert os.environ["CH_TESTVAR"] == "test_value"

    def test_get_full_name(self, init_child_env):
        sandbox_dir = Path(".").absolute()
        child_dir = sandbox_dir / "child"

        utils.replace_in_code('name = "sandbox"', 'name = "pa"')
        utils.replace_in_code(
            'name = "child"', 'name = "ch"', file=child_dir / "env_comm.py"
        )

        child_env = utils.env(child_dir)

        assert child_env.get_full_name() == "pa.ch"

    def test_parents_variables_passed_through(self, init_child_env):
        sandbox_dir = Path(".").absolute()
        child_dir = sandbox_dir / "child"

        utils.replace_in_code('name = "sandbox"', 'name = "pa"')
        utils.add_declaration("path: Raw[str]")
        utils.add_definition(
            """
            import os
            self.path = os.environ["PATH"]
            self.path = "/parent_bin_dir:" + self.path
            """
        )

        utils.replace_in_code(
            'name = "child"', 'name = "ch"', file=child_dir / "env_comm.py"
        )
        utils.add_declaration(
            "path: Raw[str]", file=child_dir / "env_comm.py",
        )
        utils.add_definition(
            """
            import os
            self.path = os.environ["PATH"]
            self.path = "/child_bin_dir:" + self.path
            """,
            file=child_dir / "env_comm.py",
        )

        child_env = utils.env(child_dir)
        child_env.activate()

        assert "child_bin_dir" in os.environ["PATH"]
        assert "parent_bin_dir" in os.environ["PATH"]
