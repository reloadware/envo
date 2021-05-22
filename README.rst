===========================================
envo - smart environment variables handling
===========================================

Define environmental variables in python and activate hot reloaded shells for them.

Features
--------
* Initialisation of variables in a given directory (creates common variables file too)

.. code-block::

    user@pc:/project$ envo local --init  # creates local environment python files

* Easy and dynamic handling in .py files (See documentation to learn more)
* Provides addons like handling virtual environments

.. code-block::

    user@pc:/project$ envo local --init=venv  # will add .venv to PATH

* Automatic env variables generation based on defined python variables
* Hot reload. Activated shell will reload environmental variables when files change.
* Activating shells for a given environment

.. code-block::

    user@pc:/project$ envo local
    🐣(project)user@pc:/project$
    🐣(project)user@pc:/project$ exit
    user@pc:/project$ envo prod
    🔥(project)user@pc:/project$


* Saving variables to a regular .env file

.. code-block::

    user@pc:/project$ envo local --save

* Printing variables (handy for non interactive CLIs like CI or docker)

.. code-block::

    user@pc:/project$ envo local --dry-run

* Detects undefined variables.
* Perfect for switching kubernetes contexts and devops tasks


Example
#######
Initialising environment

.. code-block::

    user@pc:/project$ envo local --init


Will create :code:`env_comm.py` and :code:`env_local.py`

.. code-block:: python

    # env_comm.py
    @dataclass
    class ProjectEnvComm(Env):
        @dataclass
        class Python(BaseEnv):
            version: str

        class Meta:
            raw = ["kubeconfig"]  # disable namespacing

        python: Python
        number: int
        kubeconfig: Path
        # Add more variables here

        def __init__(self) -> None:
            super().__init__(root=Path(os.path.realpath(__file__)).parent)
            self.name = "proj"
            self.python = self.Python(version="3.8.2")
            self.kubeconfig = self.root / f"{self.stage}/kubeconfig.yaml"

    # env_local.py
    @dataclass
    class ProjectEnv(ProjectEnvComm):
        def __init__(self) -> None:
            self.stage = "test"
            self.emoji = "🛠️"
            super().__init__()

            self.number = 12

    Env = ProjectEnv

Example usage:

.. code-block::

    user@pc:/project$ envo  # short for "envo local"
    🐣(project)user@pc:/project$ echo $PROJ_PYTHON_VERSION
    3.8.2
    🐣(project)user@pc:/project$echo $PROJ_NUMBER
    12


TODO:
Major:
* Refactor start_in
* Add file hooks
* Add bootstrap (versioning etc)
* add error line number

Minor:
* Shell should highlight envo commands on green
* Unnecessary prompt rendered again aftet Ctr-d (only on xonsh?)
* work on public/private fields and methods
* add examples
* print hooks for repr
* Add reload command

Bugs:
* exiting while env loading yields Attribute Error

Improvements:
* type checking ?
