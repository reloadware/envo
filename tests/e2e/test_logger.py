from time import sleep

from tests.e2e import utils
from envo import logging


class TestLogger(utils.TestBase):
    def test_retrieving(self, shell):
        shell.start()

        e = shell.expecter
        e.prompt().eval()

        shell.sendline("pass")
        e.prompt()

        logger = shell.envo.get_logger()
        messages = logger.messages
        assert len(messages) != 0

        shell.exit()
        e.exit().eval()

    def test_filtering(self, shell):
        shell.start()

        e = shell.expecter
        e.prompt(utils.PromptState.MAYBE_LOADING)

        logger = lambda: shell.envo.get_logger()
        assert len(logger().get_msgs(filter=logging.MsgFilter(metadata_re={"type": "reload"}))) == 0

        # Test filtering on metadata
        shell.trigger_reload()
        sleep(0.5)
        assert len(logger().get_msgs(filter=logging.MsgFilter(metadata_re={"type": r"reload"}))) == 1

        # Test filtering on levels
        shell.sendline("logger.error('test')")
        e.prompt(utils.PromptState.MAYBE_LOADING).eval()

        assert len(logger().get_msgs(filter=logging.MsgFilter(level=logging.Level.ERROR))) == 1

        shell.exit()
        e.exit().eval()
