import types
import unittest
from datetime import datetime

from backend.bridge.function_registry import FunctionRegistry, UnknownFunctionError


def _make_module() -> types.ModuleType:
    module = types.ModuleType("fake_api")
    exec(  # noqa: S102  # Testmodul mit öffentlicher, privater und importierter Funktion
        "from os.path import join\n"
        "def add(a, b):\n    return a + b\n"
        "def _secret():\n    return 1\n",
        module.__dict__,
    )
    module.SomeClass = datetime
    return module


class FunctionRegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = FunctionRegistry.from_module(_make_module())

    def test_only_public_functions_defined_in_module_are_exposed(self):
        self.assertEqual(self.registry.names, ["add"])

    def test_call_passes_arguments(self):
        self.assertEqual(self.registry.call("add", [2, 3]), 5)

    def test_unknown_function_raises(self):
        with self.assertRaises(UnknownFunctionError):
            self.registry.call("_secret", [])


if __name__ == "__main__":
    unittest.main()
