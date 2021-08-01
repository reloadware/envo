# flake8: noqa E402, F401

import warnings
import sys

# sys.stderr = lambda x: None

warnings.warn = lambda *args, **kwargs: None
warnings._showwarnmsg = lambda x: None

# warnings.simplefilter("ignore")

from rich.console import Console

console = Console()
console._force_terminal = True

import envo.e2e

from envo import e2e
from envo.logs import logger
from envo.devops import *
from envo.env import *
from envo.plugins import *
from envo.misc import EnvoError, import_from_file, add_source_roots, get_repo_root
from envium import (
    env_var,
    ctx_var,
    computed_env_var,
    computed_secret,
    computed_ctx_var,
    EnvGroup,
    CtxGroup,
    SecretsGroup,
    secret,
)
