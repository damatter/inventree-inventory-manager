import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class FakeInvenTreePlugin:
    """Minimal stand-in for the InvenTree plugin base class."""


class FakeReportMixin:
    """Minimal stand-in for InvenTree's report mixin."""


def import_plugin_module():
    plugin_package = ModuleType("plugin")
    plugin_package.InvenTreePlugin = FakeInvenTreePlugin
    mixins_module = ModuleType("plugin.mixins")
    mixins_module.ReportMixin = FakeReportMixin

    with patch.dict(
        sys.modules,
        {"plugin": plugin_package, "plugin.mixins": mixins_module},
    ):
        sys.modules.pop("inventory_manager.plugin", None)
        return importlib.import_module("inventory_manager.plugin")


class PluginTests(unittest.TestCase):
    def test_plugin_metadata_and_inheritance(self) -> None:
        module = import_plugin_module()
        plugin_class = module.InventoryManagerPlugin

        self.assertTrue(issubclass(plugin_class, FakeReportMixin))
        self.assertTrue(issubclass(plugin_class, FakeInvenTreePlugin))
        self.assertEqual(plugin_class.MIN_VERSION, "1.0.0")
        self.assertEqual(plugin_class.VERSION, "0.1.0")

    def test_unrelated_report_does_not_query_inventory(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        report = SimpleNamespace(name="Purchase Order", description="")
        context = {}

        with patch.object(module, "build_report_context") as build_context:
            plugin.add_report_context(report, object(), object(), context)

        build_context.assert_not_called()
        self.assertEqual(context, {})

    def test_replenishment_report_receives_context(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        report = SimpleNamespace(
            name="Inventory Replenishment Report", description=""
        )
        context = {"existing": True}

        with patch.object(
            module,
            "build_report_context",
            return_value={"critical_count": 3},
        ):
            plugin.add_report_context(report, object(), object(), context)

        self.assertEqual(context, {"existing": True, "critical_count": 3})


if __name__ == "__main__":
    unittest.main()

