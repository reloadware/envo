# import os
# from pathlib import Path
#
# import pexpect
#
# from tests.e2e import utils
#
#
# class TestEnvVariables(utils.TestBase):
#     def test_nested(self):
#         utils.add_declaration(
#             """
#             @dataclass
#             class Python(envo.BaseEnv):
#                 version: str
#
#             python: Python
#             """
#         )
#         utils.add_definition(
#             'self.python = self.Python(version="3.8.2")', file=Path("env_test.py"),
#         )
#
#         e = utils.env()
#         e._activate()
#
#         assert os.environ["SANDBOX_STAGE"] == "test"
#         assert os.environ["SANDBOX_PYTHON_VERSION"] == "3.8.2"
#
#     def test_verify_unset_variable(self):
#         utils.add_declaration("test_var: int")
#
#         e = utils.env()
#
#         with pytest.raises(envo.EnvoError) as exc:
#             e.validate()
#
#         assert str(exc.value) == ('Variable "sandbox.test_var" is unset!')
#
#     def test_verify_variable_undeclared(self):
#         utils.add_definition("self.test_var = 12")
#
#         e = utils.env()
#
#         with pytest.raises(envo.EnvoError) as exc:
#             e.validate()
#
#         assert str(exc.value) == ('Variable "sandbox.test_var" is undeclared!')
#
#     def test_raw(self):
#         utils.add_declaration(
#             """
#             @dataclass
#             class Python(envo.BaseEnv):
#                 version: Raw[str]
#
#             python: Python
#             """
#         )
#         utils.add_definition(
#             'self.python = self.Python(version="3.8.2")', file=Path("env_test.py"),
#         )
#
#         utils.add_declaration("version: Raw[str]")
#
#         utils.add_definition(
#             """
#             self.python = self.Python(version="3.8.2")
#             self.version = self.python.version + ".1"
#             """,
#             file=Path("env_test.py"),
#         )
#
#         e = utils.env()
#         e._activate()
#         assert os.environ["VERSION"] == "3.8.2.1"
#
#     @pytest.mark.skip
#     def test_nested_raw(self):
#         utils.add_declaration("value: Raw[str]")
#         utils.add_definition("self.value = 'test_value'")
#
#         e = utils.env()
#         e._activate()
#         assert os.environ["VALUE"] == "test_value"
#
