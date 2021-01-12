import sys

from pathlib import Path
from textwrap import dedent
from typing import Any, List

import pytest

from envo.misc import import_from_file
import envo.partial_reloader as hihi
from tests.unit import utils


def assert_actions(reloader: PartialReloader, actions_names: List[str]) -> None:
    actions_str = [
        repr(a) for a in reloader.old_module.get_actions(reloader.new_module)
    ]
    assert actions_str == actions_names


def load_module(path: Path, root: Path) -> Any:
    module = import_from_file(path, root)
    if path.stem == "__init__":
        module.__name__ = (path.absolute()).parent.name
    else:
        module.__name__ = path.stem
    sys.modules[module.__name__] = module
    return module


class TestBase:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        pass


class TestFunctions(TestBase):
    def test_added_function(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        source = """
        import math

        global_var = 2

        def fun(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """
        module_file.write_text(dedent(source))

        module = load_module(module_file, sandbox)

        utils.add_function(
            """
            def fun2(arg1: str, arg2: str) -> str:
                return f"{arg1}_{arg2}_{id(global_var)}"
            """,
            module_file,
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            ['Add: Function: module.fun2']
        )

        reloader.run()

        assert "fun" in module.__dict__
        assert "fun2" in module.__dict__

        assert module.fun("str1", "str2") == module.fun2("str1", "str2")

    def test_modified_function(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        source = """
        import math

        global_var = 2

        def fun(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """
        module_file.write_text(dedent(source))
        module = load_module(module_file, sandbox)

        fun_id_before = id(module.fun)

        new_source = """
        import math

        global_var = 2

        def fun(arg1: str) -> str:
            return f"{arg1}_{id(global_var)}"
        """
        module_file.write_text(dedent(new_source))

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            ["Update: Function: module.fun"],
        )
        reloader.run()

        assert "fun" in module.__dict__

        global_var_id = id(module.global_var)

        assert module.fun("str1").endswith(str(global_var_id))
        assert id(module.fun) == fun_id_before

    def test_deleted_function(self, sandbox):
        Path("__init__.py").touch()
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
        def fun1():
            return 12

        def fun2():
            return 22
        """
            )
        )

        module = load_module(module_file, sandbox)

        assert hasattr(module, "fun1")
        assert hasattr(module, "fun2")

        module_file.write_text(
            dedent(
                """
                def fun1():
                    return 12
                """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(reloader, ["Delete: Function: module.fun2"])

        reloader.run()

        assert hasattr(module, "fun1")
        assert not hasattr(module, "fun2")

    def test_renamed_function(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
            def fun1():
                return 12
            """
            )
        )

        module = load_module(module_file, sandbox)

        assert hasattr(module, "fun1")
        assert not hasattr(module, "fun_renamed")

        module_file.write_text(
            dedent(
                """
            def fun_renamed():
                return 12
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            ["Add: Function: module.fun_renamed", "Delete: Function: module.fun1"],
        )

        reloader.run()

        assert not hasattr(module, "fun1")
        assert hasattr(module, "fun_renamed")


class TestGlobabVariable(TestBase):
    def test_modified_global_var_with_dependencies(self, sandbox):
        init_file = Path("__init__.py")
        init_file.touch()
        init_file.write_text(dedent("""
        import carwash
        import car
        import accounting
        """))

        carwash_file_module = sandbox / "carwash.py"
        carwash_file_module.touch()
        carwash_file_module.write_text(dedent("""
        sprinkler_n = 3
        """))

        car_module = sandbox / "car.py"
        car_module.touch()
        car_module.write_text(dedent("""
        from carwash import sprinkler_n
    
        car_sprinklers = sprinkler_n / 3
        """))

        accounting_module = sandbox / "accounting.py"
        accounting_module.touch()
        accounting_module.write_text(dedent("""
        from car import car_sprinklers

        sprinklers_from_accounting = car_sprinklers * 10
        """))

        module = load_module(init_file, sandbox)
        car_module = load_module(car_module, sandbox)
        carwash_module = load_module(carwash_file_module, sandbox)

        assert carwash_module.sprinkler_n == 3
        assert car_module.car_sprinklers == 1

        carwash_file_module.write_text(dedent("""
                sprinkler_n = 6
                """))

        reloader = PartialReloader(carwash_module, sandbox)
        assert_actions(reloader, ['Update: Variable: carwash.sprinkler_n',
 'Update: Module: car',
 'Update: Module: accounting'])
        reloader.run()

        assert carwash_module.sprinkler_n == 6
        assert car_module.car_sprinklers == 2

    def test_added_global_var(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        source = """
        global_var1 = 1
        """
        module_file.write_text(dedent(source))

        module = load_module(module_file, sandbox)
        new_source = """
        global_var1 = 1
        global_var2 = 2
        """
        module_file.write_text(dedent(new_source))

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            [
                "Add: Variable: module.global_var2"
            ],
        )
        reloader.run()

        assert "global_var1" in module.__dict__
        assert "global_var2" in module.__dict__

        assert module.global_var1 == 1
        assert module.global_var2 == 2

    def test_modified_global_var(self, sandbox):
        Path("__init__.py").touch()
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
        sprinkler_n = 1

        def some_fun():
            return "Some Fun"

        sample_dict = {
            "sprinkler_n_plus_1": sprinkler_n + 1,
            "sprinkler_n_plus_2": sprinkler_n + 2,
            "lambda_fun": lambda x: sprinkler_n + x,
            "fun": some_fun
        }

        def print_sprinkler():
            return (f"There is {sprinkler_n} sprinkler."
             f"({sample_dict['sprinkler_n_plus_1']}, {sample_dict['sprinkler_n_plus_2']})")

        class Car:
            car_sprinkler_n = sprinkler_n
        """
            )
        )

        module = load_module(module_file, sandbox)

        print_sprinkler_id = id(module.print_sprinkler)
        lambda_fun_id = id(module.sample_dict["lambda_fun"])
        some_fun_id = id(module.some_fun)
        assert module.sprinkler_n == 1

        utils.replace_in_code("sprinkler_n = 1", "sprinkler_n = 2", module_file)

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            ['Update: Variable: module.sprinkler_n',
             'Update: DictionaryItem: module.sample_dict.sprinkler_n_plus_1',
             'Update: DictionaryItem: module.sample_dict.sprinkler_n_plus_2',
             'Update: Variable: module.Car.car_sprinkler_n']
        )

        reloader.run()

        assert print_sprinkler_id == id(module.print_sprinkler)
        assert module.Car.car_sprinkler_n == 2
        assert lambda_fun_id == id(module.sample_dict["lambda_fun"])
        assert some_fun_id == id(module.some_fun)
        assert module.sample_dict == {
            "sprinkler_n_plus_1": 3,
            "sprinkler_n_plus_2": 4,
            "lambda_fun": module.sample_dict["lambda_fun"],
            "fun": module.some_fun,
        }

    def test_deleted_global_var(self, sandbox):
        Path("__init__.py").touch()
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
        sprinkler_n = 1
        cars_n = 1
        """
            )
        )

        module = load_module(module_file, sandbox)

        assert hasattr(module, "sprinkler_n")
        assert hasattr(module, "cars_n")

        utils.replace_in_code("sprinkler_n = 1", "", module_file)

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            ['Delete: Variable: module.sprinkler_n']
        )

        reloader.run()

        assert not hasattr(module, "sprinkler_n")
        assert hasattr(module, "cars_n")


class TestClasses(TestBase):
    def test_modified_class_attr_with_dependencies(self, sandbox):
        init_file = Path("__init__.py")
        init_file.touch()
        init_file.write_text(dedent("""
                import carwash1
                import car1
                """))

        carwash_file_module = sandbox / "carwash1.py"
        carwash_file_module.touch()
        carwash_file_module.write_text(dedent(
        """
        import math
        class Carwash:
            sprinkler_n = 3
        """))

        car_module = sandbox / "car1.py"
        car_module.touch()
        car_module.write_text(dedent(
        """
        import math
        from carwash1 import Carwash
        class Car: 
            car_sprinklers = Carwash.sprinkler_n / 3
        """))

        module = load_module(init_file, sandbox)
        carwash_module = load_module(carwash_file_module, sandbox)
        car_module = load_module(car_module, sandbox)

        assert carwash_module.Carwash.sprinkler_n == 3
        assert car_module.Car.car_sprinklers == 1

        carwash_file_module.write_text(dedent(
        """
        import math
        class Carwash:
            sprinkler_n = 6
        """))

        reloader = PartialReloader(carwash_module, sandbox)
        assert_actions(reloader, ['Update: Variable: carwash1.Carwash.sprinkler_n', 'Update: Module: car1'])
        reloader.run()

        assert carwash_module.Carwash.sprinkler_n == 6
        assert car_module.Car.car_sprinklers == 2

    def test_modified_class_attr(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
        import math

        class CarwashBase:
            sprinklers_n: int = 12

            def print_sprinklers(self) -> str:
                return f"There are {self.sprinklers_n} sprinklers (Base)."

        class Carwash(CarwashBase):
            sprinklers_n: int = 22

            def print_sprinklers(self) -> str:
                return f"There are {self.sprinklers_n} sprinklers (Inherited)."
        """
            )
        )

        module = load_module(module_file, sandbox)
        print_sprinklers_id = id(module.CarwashBase.print_sprinklers)

        module_file.write_text(
            dedent(
                """
            import math

            class CarwashBase:
                sprinklers_n: int = 55

                def print_sprinklers(self) -> str:
                    return f"There are {self.sprinklers_n} sprinklers (Base)."

            class Carwash(CarwashBase):
                sprinklers_n: int = 77

                def print_sprinklers(self) -> str:
                    return f"There are {self.sprinklers_n} sprinklers (Inherited)."
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            [
                "Update: Variable: module.CarwashBase.sprinklers_n",
                "Update: Variable: module.Carwash.sprinklers_n",
            ],
        )
        reloader.run()

        assert module.CarwashBase.sprinklers_n == 55
        assert module.Carwash.sprinklers_n == 77
        assert print_sprinklers_id == id(module.CarwashBase.print_sprinklers)

    def test_recursion(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()

        module_file.write_text(
            dedent(
        """
        class Carwash:
            class_attr = 2
            
        Carwash.klass = Carwash 
        """
            )
        )

        module = load_module(module_file, sandbox)

        reloader = PartialReloader(module, sandbox)
        assert list(reloader.old_module.flat.keys()) == ['module', 'module.Carwash.class_attr', 'module.Carwash']

    def test_recursion_two_deep(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()

        module_file.write_text(
            dedent(
                """
                class Carwash:
                    class_attr = 2
                    
                    class Car:
                        class_attr2 = 13
                        
                Carwash.Car.klass = Carwash 
                """
            )
        )

        module = load_module(module_file, sandbox)

        reloader = PartialReloader(module, sandbox)
        assert list(reloader.old_module.flat.keys()) == ['module', 'module.Carwash.class_attr', 'module.Carwash.Car.class_attr2', 'module.Carwash.Car', 'module.Carwash']

    def test_added_class_attr(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
            class Carwash:
                sprinklers_n: int = 22

                def fun(self) -> str:
                    return 12
            """
            )
        )

        module = load_module(module_file, sandbox)

        assert hasattr(module.Carwash, "sprinklers_n")
        assert not hasattr(module.Carwash, "cars_n")

        # First edit
        module_file.write_text(
            dedent(
                """
            class Carwash:
                sprinklers_n: int = 22
                cars_n: int = 15

                def fun(self) -> str:
                    return 12
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            [
                "Add: Variable: module.Carwash.cars_n"
            ],
        )
        reloader.run()

        assert hasattr(module.Carwash, "sprinklers_n")
        assert hasattr(module.Carwash, "cars_n")

    def test_deleted_class_attr(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
            class Carwash:
                sprinklers_n: int = 22
                cars_n: int = 15

                def fun(self) -> str:
                    return 12
            """
            )
        )

        module = load_module(module_file, sandbox)

        assert hasattr(module.Carwash, "sprinklers_n")
        assert hasattr(module.Carwash, "cars_n")

        # First edit
        module_file.write_text(
            dedent(
                """
            class Carwash:
                sprinklers_n: int = 22

                def fun(self) -> str:
                    return 12
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            [
                "Delete: Variable: module.Carwash.cars_n",
            ],
        )
        reloader.run()

        assert hasattr(module.Carwash, "sprinklers_n")
        assert not hasattr(module.Carwash, "cars_n")

    def test_modified_method(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
            class Carwash:
                @classmethod
                def print_sprinklers_cls(cls) -> str:
                    return f"There is one sprinkler (Cls)."

                def print_sprinklers(self) -> str:
                    return f"There is one sprinkler."
            """
            )
        )

        module = load_module(module_file, sandbox)
        reffered_print_sprinklers_cls = module.Carwash.print_sprinklers_cls
        assert module.Carwash.print_sprinklers_cls() == "There is one sprinkler (Cls)."
        assert reffered_print_sprinklers_cls() == "There is one sprinkler (Cls)."
        assert module.Carwash().print_sprinklers() == "There is one sprinkler."

        print_sprinklers_id = id(module.Carwash.print_sprinklers)

        module_file.write_text(
            dedent(
                """
            class Carwash:
                @classmethod
                def print_sprinklers_cls(cls) -> str:
                    return f"There are 5 sprinklers (Cls)."

                def print_sprinklers(self) -> str:
                    return f"There are 5 sprinklers."
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            [
                "Update: Method: module.Carwash.print_sprinklers_cls",
                "Update: Function: module.Carwash.print_sprinklers",
            ],
        )
        reloader.run()

        assert module.Carwash.print_sprinklers_cls() == "There are 5 sprinklers (Cls)."
        assert reffered_print_sprinklers_cls() == "There are 5 sprinklers (Cls)."
        assert module.Carwash().print_sprinklers() == "There are 5 sprinklers."
        assert print_sprinklers_id == id(module.Carwash.print_sprinklers)

    def test_added_method(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
            class Carwash:
                pass
            """
            )
        )

        module = load_module(module_file, sandbox)

        module_file.write_text(
            dedent(
                """
            class Carwash:
                def print_sprinklers(self) -> str:
                    return f"There are 5 sprinklers."
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(reloader, ["Add: Function: module.Carwash.print_sprinklers"])
        reloader.run()

        assert module.Carwash().print_sprinklers() == "There are 5 sprinklers."

    def test_delete_method(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
            class Carwash:
                def fun1(self):
                    return 2

                def fun2(self):
                    return 4
            """
            )
        )

        module = load_module(module_file, sandbox)

        assert hasattr(module.Carwash, "fun1")
        assert hasattr(module.Carwash, "fun2")

        module_file.write_text(
            dedent(
                """
            class Carwash:
                def fun1(self):
                    return 2

            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(reloader, ["Delete: Function: module.Carwash.fun2"])
        reloader.run()

        assert hasattr(module.Carwash, "fun1")
        assert not hasattr(module.Carwash, "fun2")


class TestModules(TestBase):
    def test_import_relative(self, sandbox):
        init_file = Path("__init__.py")
        init_file.touch()

        slave_module_file = sandbox / "slave_module.py"
        slave_module_file.touch()
        source = """
        slave_global_var = 2

        def slave_fun(arg1: str, arg2: str) -> str:
            return "Slave test"
        """
        slave_module_file.write_text(dedent(source))

        master_module_file = sandbox / "module.py"
        master_module_file.touch()
        source = """
        from .slave_module import slave_global_var

        global_var = 2

        def fun(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """
        master_module_file.write_text(dedent(source))
        init = load_module(init_file, sandbox)
        module = load_module(master_module_file, sandbox)

        utils.replace_in_code("global_var = 2", "global_var = 5", master_module_file)

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            [
                "Update: Variable: module.global_var",
            ],
        )

        reloader.run()

        assert module.global_var == 5

    def test_added_import(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
            glob_var = 4
            """
            )
        )

        module = load_module(module_file, sandbox)

        assert not hasattr(module, "math")

        module_file.write_text(
            dedent(
                """
            import math
            glob_var = 4
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader, ["Add: Import: module.math"]
        )
        reloader.run()

        assert hasattr(module, "math")

    def test_removed_import(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
                """
            import math
            glob_var = 4
            """
            )
        )

        module = load_module(module_file, sandbox)

        assert hasattr(module, "math")

        module_file.write_text(
            dedent(
                """
            glob_var = 4
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            ["Delete: Import: module.math"],
        )
        reloader.run()

        assert not hasattr(module, "math")

    def test_add_relative(self, sandbox):
        init_file = Path("__init__.py")
        init_file.touch()
        load_module(init_file, sandbox)
        sys.path.insert(0, str(sandbox.parent))

        slave_module_file = sandbox / "slave_module.py"
        slave_module_file.touch()
        source = """
        slave_global_var = 2
        """
        slave_module_file.write_text(dedent(source))

        master_module_file = sandbox / "module.py"
        master_module_file.touch()
        source = """
        global_var = 2
        """
        master_module_file.write_text(dedent(source))
        module = load_module(master_module_file, sandbox)

        assert not hasattr(module, "slave_module")

        source = """
        from . import slave_module
        global_var = 2
        """
        master_module_file.write_text(dedent(source))

        reloader = PartialReloader(module, sandbox)
        assert_actions(
            reloader,
            ['Add: Import: module.slave_module']
        )

        reloader.run()

        assert hasattr(module, "slave_module")


class TestMisc(TestBase):
    def test_syntax_error(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
            """
            glob_var = 4
            """
            )
        )

        module = load_module(module_file, sandbox)

        module_file.write_text(
            dedent(
            """
            glob_var = 4pfds
            """
            )
        )

        reloader = PartialReloader(module, sandbox)

        with pytest.raises(SyntaxError):
            reloader.run()

    def test_other_error(self, sandbox):
        module_file = sandbox / "module.py"
        module_file.touch()
        module_file.write_text(
            dedent(
            """
            glob_var = 4
            """
            )
        )

        module = load_module(module_file, sandbox)

        module_file.write_text(
            dedent(
            """
            glob_var = 4/0
            """
            )
        )

        reloader = PartialReloader(module, sandbox)
        with pytest.raises(ZeroDivisionError):
            reloader.run()
