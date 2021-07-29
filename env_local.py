import os
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple

import envo

root = Path(__file__).parent.absolute()
envo.add_source_roots([root])

from envo import Namespace, command, console, inject, logger, run

# Declare your command namespaces here
# like this:

localci = Namespace(name="localci")
p = Namespace(name="p")

from env_comm import ThisEnv as ParentEnv


@dataclass
class Version:
    version: str
    venv_name: str


class EnvoLocalEnv(ParentEnv):
    class Meta(ParentEnv.Meta):
        stage: str = "local"
        emoji: str = "🐣"
        verbose_run = True

    class Environ(ParentEnv.Environ):
        pass

    e: Environ

    supported_versions: List[int] = ["3.6", "3.7", "3.8", "3.9"]

    def init(self) -> None:
        self.package_name = "reloader"
        super().init()
        self.utils_dir = Path("common/utils")

        self.ci_template = self.meta.root / ".github/workflows/test.yml.templ"
        self.ci_out = self.meta.root / ".github/workflows/test.yml"

        self.black_ver = "21.7b0"

        self.python_versions = {
            "3.6": Version("3.6.13", ".venv36"),
            "3.7": Version("3.7.10", ".venv37"),
            "3.8": Version("3.8.10", ".venv38"),
            "3.9": Version("3.9.5", ".venv39"),
        }

    @p.command
    def bootstrap(self, version="3.9") -> None:
        v = self.python_versions[version]
        v.venv_name = ".venv"
        self.bootstrap_python_version(v)

    def bootstrap_python_version(self, v: Version) -> None:
        path_tmp = os.environ["PATH"]
        run(f"rm {v.venv_name} -rf")
        os.environ["PATH"] = f"{Path.home()}/.pyenv/versions/{v.version}/bin/:{os.environ['PATH']}"
        run(f"python -m venv {v.venv_name}")
        run(f"{v.venv_name}/bin/pip install pip=={self.ctx.pip_ver}")
        run(f"{v.venv_name}/bin/pip install poetry=={self.ctx.poetry_ver}")
        run(f"source {v.venv_name}/bin/activate && poetry config virtualenvs.create false")
        run(f"source {v.venv_name}/bin/activate && poetry config virtualenvs.in-project false")
        run(f"source {v.venv_name}/bin/activate && poetry install")
        os.environ["PATH"] = path_tmp

    @p.command
    def render_ci(self) -> None:
        from jinja2 import StrictUndefined, Template

        bootstrap_code = dedent(
            """
        - uses: actions/checkout@v2
        - name: Set up Python
          uses: actions/setup-python@v2
          with:
            {%- raw %}
            python-version: ${{ matrix.python_version }}
            {%- endraw %}
        - uses: gerbal/always-cache@v1.0.3
          id: pip-cache
          with:
            path: ~/.cache/pip
            key: pip-cache-{{ pip_ver }}-{{ poetry_ver }}
            restore-keys: pip-cache-
        - uses: gerbal/always-cache@v1.0.3
          id: root-venv-cache
          with:
            path: .venv
            {%- raw %}
            key: root-venv-${{ hashFiles('poetry.lock') }}
            {%- endraw %}
            restore-keys: root-venv-
        - run: pip install pip=={{ pip_ver }}
        - run: pip install poetry=={{ poetry_ver }}
        - run: poetry config virtualenvs.create true
        - run: poetry config virtualenvs.in-project true
        - run: poetry install
        """
        )

        ctx = {
            "pip_ver": self.ctx.pip_ver,
            "poetry_ver": self.ctx.poetry_ver,
        }

        bootstrap_code = Template(bootstrap_code, undefined=StrictUndefined).render(**ctx)

        ctx = {
            "black_ver": self.black_ver,
            "python_versions": [3.6, 3.7, 3.8, 3.9],
            "bootstrap_code": bootstrap_code,
        }

        templ = Template(self.ci_template.read_text(), undefined=StrictUndefined)
        self.ci_out.write_text(templ.render(**ctx))

    @p.command
    def test(self) -> None:
        logger.info("Running tests")
        run("pytest tests -v -n auto --reruns 3")

    @p.command
    def verbose_test(self) -> None:
        run("echo verbose cmd")
        print("Output")
        run("echo verbose hihi")

    @p.command
    def flake(self) -> None:
        self.black()
        run("flake8")

    @p.command
    def mypy(self, arg) -> None:
        logger.info("Running mypy")
        run("mypy envo")

    @p.command
    def black(self) -> None:
        run("isort .", print_output=False)
        run("black .", print_output=False)

    @p.command
    def ci(self) -> None:
        self.flake()
        self.mypy()
        self.test()

    @p.command
    def long(self) -> None:
        run("sleep 5")

    @localci.command
    def __flake(self) -> None:
        run("circleci local execute --job flake8")

    @p.command
    def amend_and_push(self) -> None:
        self.render_ci()
        inject("git add .")
        inject("git commit --amend --no-edit")
        inject("git push -f")


ThisEnv = EnvoLocalEnv
