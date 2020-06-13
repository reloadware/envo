import builtins
import sys
import time
from copy import copy
from typing import Any, Dict

from xonsh.base_shell import BaseShell
from xonsh.execer import Execer
from xonsh.ptk_shell.shell import PromptToolkitShell
from xonsh.readline_shell import ReadlineShell


class Shell(BaseShell):  # type: ignore
    """
    Xonsh shell extension.
    """

    def __init__(self, execer: Execer) -> None:
        super().__init__(execer=execer, ctx={})

        self.environ = builtins.__xonsh__.env  # type: ignore
        self.history = builtins.__xonsh__.history  # type: ignore
        self.environ_before = copy(self.environ)
        self.context: Dict[str, Any] = {}

    def set_prompt_prefix(self, prefix: str) -> None:
        from xonsh.prompt.base import DEFAULT_PROMPT

        self.environ["PROMPT"] = prefix + str(DEFAULT_PROMPT)

    def set_variable(self, name: str, value: Any) -> None:
        """
        Send a variable to the shell.

        :param name: variable name
        :param value: variable value
        :return:
        """
        self.context[name] = value

        built_in_name = f"__envo_{name}__"
        setattr(builtins, built_in_name, value)
        self.default(f"{name} = {built_in_name}")

    def start(self) -> None:
        pass

    def reset(self) -> None:
        self.environ = copy(self.environ_before)
        for n, v in self.context.items():
            self.default(f"del {n}")

        self.context = {}

    @property
    def prompt(self) -> str:
        from xonsh.ansi_colors import ansi_partial_color_format

        return str(ansi_partial_color_format(super().prompt))

    @classmethod
    def create(cls) -> "Shell":
        import signal
        from xonsh.built_ins import load_builtins
        from xonsh.built_ins import XonshSession
        from xonsh.imphooks import install_import_hooks
        from xonsh.xontribs import xontribs_load
        import xonsh.history.main as xhm

        ctx: Dict[str, Any] = {}

        execer = Execer(xonsh_ctx=ctx)

        builtins.__xonsh__ = XonshSession(ctx=ctx, execer=execer)  # type: ignore

        load_builtins(ctx=ctx, execer=execer)
        env = builtins.__xonsh__.env  # type: ignore
        env.update({"XONSH_INTERACTIVE": True, "SHELL_TYPE": "prompt_toolkit"})
        builtins.__xonsh__.history = xhm.construct_history(  # type: ignore
            env=env.detype(), ts=[time.time(), None], locked=True
        )

        builtins.__xonsh__.history.gc.wait_for_shell = False  # type: ignore

        install_import_hooks()
        builtins.aliases.update({"ll": "ls -alF"})  # type: ignore
        xontribs_load([""])

        def func_sig_ttin_ttou(n: Any, f: Any) -> None:
            pass

        signal.signal(signal.SIGTTIN, func_sig_ttin_ttou)
        signal.signal(signal.SIGTTOU, func_sig_ttin_ttou)

        shell = cls(execer)
        builtins.__xonsh__.shell = shell  # type: ignore
        builtins.__xonsh__.shell.shell = shell  # type: ignore

        return shell


class FancyShell(Shell, PromptToolkitShell):  # type: ignore
    @classmethod
    def create(cls) -> "Shell":
        from xonsh.main import _pprint_displayhook

        shell = super().create()
        setattr(sys, "displayhook", _pprint_displayhook)
        return shell

    def start(self) -> None:
        self.cmdloop()


class SimpleShell(Shell, ReadlineShell):  # type: ignore
    def start(self) -> None:
        self.cmdloop()


shells = {"fancy": FancyShell, "simple": SimpleShell, "headless": Shell}
