from time import sleep

from envo import logging
from tests.e2e import utils


class TestLogger(utils.TestBase):
    def test_retrieving(self, shell):
        e = shell.start()
        e.prompt().eval()

        shell.sendline("pass")
        e.prompt()

        logger = shell.envo.get_logger()
        messages = logger.messages
        assert len(messages) != 0

        shell.exit()
        e.exit().eval()

    def test_filtering(self, shell):
        e = shell.start()
        e.prompt(utils.PromptState.MAYBE_LOADING)

        def logger():
            return shell.envo.get_logger()

        assert (
            len(
                logger().get_msgs(
                    filter=logging.MsgFilter(metadata_re={"type": "reload"})
                )
            )
            == 0
        )

        # Test filtering on metadata
        shell.trigger_reload()
        sleep(0.5)
        assert (
            len(
                logger().get_msgs(
                    filter=logging.MsgFilter(metadata_re={"type": r"reload"})
                )
            )
            == 1
        )

        # Test filtering on levels
        shell.sendline("logger.error('test')")
        e.prompt(utils.PromptState.MAYBE_LOADING).eval()

        assert (
            len(logger().get_msgs(filter=logging.MsgFilter(level=logging.Level.ERROR)))
            == 1
        )

        shell.exit()
        e.exit().eval()
