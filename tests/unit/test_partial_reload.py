import copy
import os
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from envo.misc import import_from_file
from envo.partial_reloader import PartialReloader
from tests.unit import utils


class TestBase:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        pass


class TestFunctions(TestBase):
    def test_added_function(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        source ="""
        import math
        
        global_var = [1, 2, 3]
        
        def fun(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """
        module_file.write_text(dedent(source))

        module = import_from_file(module_file)

        utils.add_function(
            """
            def fun2(arg1: str, arg2: str) -> str:
                return f"{arg1}_{arg2}_{id(global_var)}"
            """,
            module_file
        )

        reloader = PartialReloader(module, source_dirs=[sandbox])
        actions = reloader.old_module.get_actions(reloader.new_module)
        assert len(actions) == 1
        reloader.run()

        assert "fun" in  module.__dict__
        assert "fun2" in module.__dict__

        assert module.fun("str1", "str2") == module.fun2("str1", "str2")

    def test_modified_function(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        source = """
        import math

        global_var = [1, 2, 3]

        def fun(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """
        module_file.write_text(dedent(source))

        module = import_from_file(module_file)
        fun_id_before = id(module.fun)

        new_source = """
        import math

        global_var = [1, 2, 3]

        def fun(arg1: str) -> str:
            return f"{arg1}_{id(global_var)}"
        """
        module_file.write_text(dedent(new_source))

        reloader = PartialReloader(module, source_dirs=[sandbox])
        actions = reloader.old_module.get_actions(reloader.new_module)
        assert len(actions) == 1
        reloader.run()

        assert "fun" in module.__dict__

        global_var_id = id(module.global_var)

        assert module.fun("str1").endswith(str(global_var_id))
        assert id(module.fun) == fun_id_before

    def test_added_global_var(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        source = """
        global_var1 = 1 
        """
        module_file.write_text(dedent(source))

        module = import_from_file(module_file)
        new_source = """
        global_var1 = 1
        global_var2 = 2
        """
        module_file.write_text(dedent(new_source))

        reloader = PartialReloader(module, source_dirs=[sandbox])
        actions = reloader.old_module.get_actions(reloader.new_module)
        assert len(actions) == 1
        reloader.run()

        assert "global_var1" in module.__dict__
        assert "global_var2" in module.__dict__

        assert module.global_var1 == 1
        assert module.global_var2 == 2

    def test_modified_global_var(self, sandbox):
        Path("__init__.py").touch()
        carwash_file_module = sandbox / "carwash.py"
        carwash_file_module.touch()
        carwash_file_module.write_text("""sprinkler_n = 1""")

        car_file_module = sandbox / "car.py"
        car_file_module.touch()
        car_file_module.write_text(
            dedent(
                """
                from carwash import sprinkler_n
                car_sprinklers = sprinkler_n
                
                def clean_car(arg: str) -> None:
                    return (f"Cleaning car using {car_sprinklers} sprinklers " + arg) 
                """)
        )

        office_file_module = sandbox / "office.py"
        office_file_module.touch()
        office_file_module.write_text(
            dedent(
        """
        import carwash
        from carwash import sprinkler_n
        how_many_sprinklers = carwash.sprinkler_n
        """)
        )

        accounting_file_module = sandbox / "accounting.py"
        accounting_file_module.touch()
        accounting_file_module.write_text(
            dedent(
                """
                from office import how_many_sprinklers
                
                def fun_from_accounting() -> None:
                    return (f"Calling fun from accounting. There are {how_many_sprinklers} sprinklers")  
                """)
        )

        main_module_file = sandbox / "main.py"
        main_module_file.touch()
        main_module_file.write_text(dedent(
            """
            import carwash
            import office
            import car
            import accounting
            """
        ))

        main_module = import_from_file(main_module_file)
        clean_car_fun_id = id(main_module.car.clean_car)
        fun_from_accounting_id = id(main_module.accounting.fun_from_accounting)
        # we have to add it manually since we're importing from file
        sys.modules["main"] = main_module

        assert main_module.carwash.sprinkler_n == 1
        assert main_module.office.sprinkler_n == 1
        assert main_module.office.how_many_sprinklers == 1

        # First edit
        carwash_file_module.write_text("""sprinkler_n = 2""")

        reloader = PartialReloader(main_module.carwash, [sandbox])
        actions = reloader.old_module.get_actions(reloader.new_module)
        assert len(actions) == 7

        actions_str = [repr(a) for a in actions]
        assert actions_str == ['Update: Module: carwash', 'Update: Module: office', 'Update: Module: accounting', 'Update: Function: accounting.fun_from_accounting', 'Update: Module: car', 'Update: Function: car.clean_car', 'Update: Module: /home/kwazar/Code/opensource/envo/tests/unit/sandbox/main.py']

        reloader.run()

        assert clean_car_fun_id == id(main_module.car.clean_car)
        assert fun_from_accounting_id == id(main_module.accounting.fun_from_accounting)
        assert main_module.car.clean_car("and hi btw") == "Cleaning car using 2 sprinklers and hi btw"
        assert main_module.accounting.fun_from_accounting() == "Calling fun from accounting. There are 2 sprinklers"

        assert main_module.carwash.sprinkler_n == 2
        assert main_module.office.sprinkler_n == 2
        assert main_module.office.how_many_sprinklers == 2
        assert main_module.accounting.how_many_sprinklers == 2

        # Second edit
        carwash_file_module.write_text("""sprinkler_n = 3""")

        actions = reloader.old_module.get_actions(reloader.new_module)
        assert len(actions) == 7

        actions_str = [repr(a) for a in actions]
        assert actions_str == ['Update: Module: carwash', 'Update: Module: office', 'Update: Module: accounting', 'Update: Function: accounting.fun_from_accounting', 'Update: Module: car', 'Update: Function: car.clean_car', 'Update: Module: /home/kwazar/Code/opensource/envo/tests/unit/sandbox/main.py']

        reloader.run()

        assert clean_car_fun_id == id(main_module.car.clean_car)
        assert fun_from_accounting_id == id(main_module.accounting.fun_from_accounting)
        assert main_module.car.clean_car("and hi btw") == "Cleaning car using 3 sprinklers and hi btw"
        assert main_module.accounting.fun_from_accounting() == "Calling fun from accounting. There are 3 sprinklers"

        assert main_module.carwash.sprinkler_n == 3
        assert main_module.office.sprinkler_n == 3
        assert main_module.office.how_many_sprinklers == 3
        assert main_module.accounting.how_many_sprinklers == 3
