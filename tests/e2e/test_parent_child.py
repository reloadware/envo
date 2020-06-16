from tests.e2e import utils
import os
from pathlib import Path


class TestParentChild(utils.TestBase):
    def test_init(self, envo_prompt, init_child_env):
        os.chdir("child")

        nested_prompt = envo_prompt.replace(b"sandbox", b"sandbox.child")
        utils.shell(nested_prompt)

    def test_hot_reload(self, envo_prompt, init_child_env):
        os.chdir("child")

        nested_prompt = envo_prompt.replace(b"sandbox", b"sandbox.child")
        s = utils.shell(nested_prompt)

        child_file = Path("env_comm.py")
        content = child_file.read_text()
        content = content.replace("child", "ch")
        child_file.write_text(content)

        new_prompt1 = nested_prompt.replace(b"child", b"ch")
        s.expect(new_prompt1)

        parent_file = Path("../env_comm.py")
        content = parent_file.read_text()
        content = content.replace("sandbox", "sb")
        parent_file.write_text(content)

        new_prompt2 = new_prompt1.replace(b"sandbox", b"sb")
        s.expect(new_prompt2)

    def test_child_importable(self, envo_prompt, init_child_env):
        Path("__init__.py").touch()
        os.chdir("child")
        Path("__init__.py").touch()

        nested_prompt = envo_prompt.replace(b"sandbox", b"sandbox.child")
        s = utils.shell(nested_prompt)

        test_script = Path("test_script.py")
        content = "from env_test import Env\n"
        content += "env = Env()\n"
        content += 'print("ok")\n'
        test_script.write_text(content)

        s.sendline("python3 test_script.py")
        s.expect("ok")

    def test_same_child_names(self, envo_prompt, init_2_same_childs):
        root_dir = Path(".").absolute()

        os.chdir(root_dir / "sandbox/sandbox")

        nested_prompt = envo_prompt.replace(b"sandbox", b"sandbox.sandbox.sandbox")
        utils.shell(nested_prompt)
