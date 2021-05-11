import builtins
import os
import sys
import time
from copy import copy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, TextIO, Union

import fire
from prompt_toolkit.data_structures import Size
from xonsh.base_shell import BaseShell, _TeeStd
from xonsh.execer import Execer
from xonsh.prompt.base import DEFAULT_PROMPT
from xonsh.ptk_shell.shell import PromptToolkitShell
from xonsh.readline_shell import ReadlineShell

import envo
from envo import logger
from envo.misc import Callback, is_windows


class PromptState(Enum):
    LOADING = 0
    NORMAL = 1


class PromptBase:
    default: str = str(DEFAULT_PROMPT)
    loading: bool = False
    emoji: str = NotImplemented
    state_prefix_map: Dict[PromptState, Callable[[], str]] = NotImplemented
    name: str

    def __init__(self) -> None:
        self.state = PromptState.LOADING
        self.previous_state: Optional[PromptState] = None
        self.emoji = ""
        self.name = ""

    def set_state(self, state: PromptState) -> None:
        self.previous_state = self.state
        self.state = state

    def as_str(self) -> str:
        return self.state_prefix_map[self.state]()

    def __str__(self) -> str:
        return self.state_prefix_map[self.state]()


class Shell(BaseShell):  # type: ignore
    """
    Xonsh shell extension.
    """

    @dataclass
    class Callbacks:
        pre_cmd: Callback = Callback()
        on_stdout: Callback = Callback()
        on_stderr: Callback = Callback()
        on_cmd: Callback = Callback()
        post_cmd: Callback = Callback()
        on_enter: Callback = Callback()
        on_exit: Callback = Callback()
        on_ready: Callback = Callback()

        def reset(self) -> None:
            self.pre_cmd = Callback()
            self.on_stdout = Callback()
            self.on_stderr = Callback()
            self.on_cmd: Callback = Callback()
            self.post_cmd = Callback()
            self.on_enter = Callback()
            self.on_exit = Callback()
            self.on_ready = Callback()

    def __init__(self, calls: Callbacks, execer: Execer) -> None:
        super().__init__(execer=execer, ctx={})

        logger.debug("Shell __init__")
        self.shell_type = "prompt_toolkit"

        self.calls = calls

        self.environ = builtins.__xonsh__.env  # type: ignore
        self.history = builtins.__xonsh__.history  # type: ignore
        self.context: Dict[str, Any] = {}

        self.cmd_lock = Lock()
        self.last_return_code = 0

        self.bootload()

    def bootload(self) -> None:
        self._run_code("import fire")
        self._run_code("import sys")

        self.set_variable("_execute_with_fire", self._execute_with_fire)

    def set_prompt(self, prompt: str) -> None:
        self.environ["PROMPT"] = prompt

    def set_variable(self, name: str, value: Any) -> None:
        """
        Send a variable to the shell.

        :param name: variable name
        :param value: variable value
        :return:
        """
        self.context[name] = value

        if "." in name:
            namespace = name.split(".")[0]
            self.add_namespace_if_not_exists(namespace)

        max_lenght = 50
        log_value = (
            str(value)
            if len(str(value)) < max_lenght
            else f"{str(value)[0:max_lenght]}(...)"
        )
        log_value = log_value.replace("{", "{{")
        log_value = log_value.replace("}", "}}")
        logger.debug(f'Setting "{name} = {log_value}" variable')

        built_in_name = f"__envo_{name}__"
        built_in_name = built_in_name.replace(".", "_")
        setattr(builtins, built_in_name, value)
        exec(f"{name} = {built_in_name}", builtins.__dict__)

    def _execute_with_fire(self, fun: Callable, command: str) -> Any:
        command_name = command.split()[0]
        command_args = command.split()[1:]

        argv_before = sys.argv.copy()
        sys.argv = [command_name, *command_args]

        try:
            fire.Fire(fun)
        finally:
            sys.argv = argv_before

    def add_namespace_if_not_exists(self, name: str) -> None:
        self.run_code(
            f'class Namespace: pass\n{name} = Namespace() if "{name}" not in globals() else {name}'
        )

    def set_context(self, context: Dict[str, Any]) -> None:
        for k, v in context.items():
            self.set_variable(k, v)

        self.context.update(**context)

    def _run_code(self, code: str) -> None:
        exec(code, builtins.__dict__)

    def run_code(self, code: str) -> None:
        logger.debug(f'Running code """{code}"""')
        self._run_code(code)

    def start(self) -> None:
        pass

    def reset(self) -> None:
        for n, v in self.context.items():
            exec(f"del {n}", builtins.__dict__)

        self.context = {}

    @property
    def prompt(self) -> str:
        from xonsh.ansi_colors import ansi_partial_color_format

        return str(ansi_partial_color_format(super().prompt))

    @classmethod
    def create(cls, calls: Callbacks, data_dir_name: str) -> "Shell":
        import signal

        import xonsh.history.main as xhm
        from xonsh.built_ins import XonshSession, load_builtins
        from xonsh.imphooks import install_import_hooks
        from xonsh.xontribs import xontribs_load

        ctx: Dict[str, Any] = {}

        data_dir = Path.home() / f".envo/xonsh_data/{data_dir_name}"
        os.makedirs(data_dir, exist_ok=True)

        execer = Execer(xonsh_ctx=ctx)

        builtins.__xonsh__ = XonshSession(ctx=ctx, execer=execer)  # type: ignore

        load_builtins(ctx=ctx, execer=execer)
        env = builtins.__xonsh__.env  # type: ignore
        env.update(
            {
                "XONSH_INTERACTIVE": True,
                "SHELL_TYPE": "prompt_toolkit",
                "COMPLETIONS_BRACKETS": False,
                "XONSH_DATA_DIR": data_dir,
            }
        )

        if "ENVO_SHELL_NOHISTORY" not in os.environ:
            builtins.__xonsh__.history = xhm.construct_history(  # type: ignore
                env=env.detype(), ts=[time.time(), None], locked=True, buffersize=100
            )
            builtins.__xonsh__.history.gc.wait_for_shell = False  # type: ignore

        install_import_hooks()
        builtins.aliases.update({"ll": "ls -alF"})  # type: ignore
        xontribs_load([""])

        def func_sig_ttin_ttou(n: Any, f: Any) -> None:
            pass

        if not is_windows():
            signal.signal(signal.SIGTTIN, func_sig_ttin_ttou)
            signal.signal(signal.SIGTTOU, func_sig_ttin_ttou)

        shell = cls(calls, execer)
        builtins.__xonsh__.shell = shell  # type: ignore
        builtins.__xonsh__.shell.shell = shell  # type: ignore

        return shell

    def set_fulll_traceback_enabled(self, enabled: bool = True):
        self.environ["XONSH_SHOW_TRACEBACK"] = enabled

    def execute(self, line: str, history_line: str) -> Any:
        self.append_history = BaseShell._append_history
        BaseShell._append_history = lambda self, inp, ts, spc, tee_out: None

        ts0 = time.time()

        if history_line:
            self.append_history(
                self,
                inp=history_line,
                ts=[ts0, ts0],
                spc=self.src_starts_with_space,
                tee_out="",
            )

        BaseShell.default(self, line)

        BaseShell._append_history = self.append_history

        if self.history and self.history.buffer:
            self.last_return_code = self.history.last_cmd_rtn
            self.history.flush()

    def default(self, line: str, raw_line=None) -> Any:
        logger.info("Executing command", {"command": line})
        self.cmd_lock.acquire()

        orig_std_out_write = sys.stdout.write
        orig_std_err_write = sys.stderr.write

        std_out_content = []
        std_err_content = []

        try:
            # W want to catch all exceptions just in case the command fails so we can handle std_err and post_cmd
            hist_line = line
            if self.calls.pre_cmd:
                line = self.calls.pre_cmd(line)

            if self.calls.on_stdout:

                def stdout_write(text: Union[bytes, str]) -> None:
                    text = self.calls.on_stdout(command=line, out=text)
                    orig_std_out_write(text)
                    std_out_content.append(text)

                sys.stdout.write = stdout_write

            if self.calls.on_stderr:

                def stderr_write(text: Union[bytes, str]) -> None:
                    text = self.calls.on_stderr(command=line, out=text)
                    orig_std_err_write(text)
                    std_err_content.append(text)

                sys.stderr.write = stderr_write

            ret = self.execute(line, hist_line)
        finally:
            if self.calls.on_stdout:
                sys.stdout.write = orig_std_out_write

            if self.calls.on_stderr:
                sys.stderr.write = orig_std_err_write

            if self.calls.post_cmd:
                self.calls.post_cmd(
                    command=line, stdout=std_out_content, stderr=std_err_content
                )

            self.cmd_lock.release()

        return ret


class FancyShell(Shell, PromptToolkitShell):  # type: ignore
    @dataclass
    class Callbacks(Shell.Callbacks):
        pass

    @classmethod
    def create(cls, calls: Callbacks, data_dir_name: str) -> "Shell":
        logger.debug("Creating FancyShell")
        from xonsh.main import _pprint_displayhook

        shell = super().create(calls, data_dir_name=data_dir_name)

        setattr(sys, "displayhook", _pprint_displayhook)
        return shell

    def start(self) -> None:
        logger.debug("Starting FancyShell")

        if envo.e2e.enabled:
            self.prompter.output.get_size = lambda: Size(50, 200)

        self.calls.on_enter()

        self.calls.on_ready()

        self.cmdloop()

        self.calls.on_exit()

    def set_prompt(self, prompt: str) -> None:
        super(FancyShell, self).set_prompt(prompt)
        self.prompter.message = self.prompt_tokens()
        self.prompter.app.invalidate()

    def redraw(self) -> None:
        self.prompter.app.renderer.erase(leave_alternate_screen=False)
        self.prompter.app.invalidate()


class SimpleShell(Shell, ReadlineShell):  # type: ignore
    def start(self) -> None:
        logger.debug("Starting SimpleShell")
        self.cmdloop()


shells = {"fancy": FancyShell, "simple": SimpleShell, "headless": Shell}
