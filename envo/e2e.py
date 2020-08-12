import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

STICKYBEAK_PORT = 5416


if TYPE_CHECKING:
    from envo.scripts import EnvoBase


__all__ = ["envo", "enabled"]

envo: Optional["EnvoBase"] = None

enabled = "ENVO_E2E_TEST" in os.environ

server = None

if enabled:
    import os
    import stickybeak

    project_root = Path(__file__).parent
    server = stickybeak.Server(project_root, STICKYBEAK_PORT)
    server.start()
