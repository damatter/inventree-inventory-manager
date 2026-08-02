import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class FakeInvenTreePlugin:
    """Minimal stand-in for the InvenTree plugin base class."""

    def plugin_static_file(self, filename):
        return f"/static/plugins/inventory-manager/{filename}"


class FakeReportMixin:
    """Minimal stand-in for InvenTree's report mixin."""


class FakeSettingsMixin:
    """Minimal stand-in for InvenTree's settings mixin."""

    def get_setting(self, key, cache=False, backup_value=None):
        del key, cache
        return backup_value


class FakeScheduleMixin:
    """Minimal stand-in for InvenTree's schedule mixin."""


class FakeUrlsMixin:
    """Minimal stand-in for InvenTree 1.3.5's URL mixin."""

    base_url = "plugin/inventory-manager/"


class FakeUserInterfaceMixin:
    """Minimal stand-in for InvenTree's UI mixin."""


def import_plugin_module():
    plugin_package = ModuleType("plugin")
    plugin_package.InvenTreePlugin = FakeInvenTreePlugin
    mixins_module = ModuleType("plugin.mixins")
    mixins_module.ReportMixin = FakeReportMixin
    mixins_module.SettingsMixin = FakeSettingsMixin
    mixins_module.ScheduleMixin = FakeScheduleMixin
    mixins_module.UrlsMixin = FakeUrlsMixin
    mixins_module.UserInterfaceMixin = FakeUserInterfaceMixin

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
        self.assertEqual(plugin_class.AUTHOR, "Matt Dick")
        self.assertEqual(plugin_class.MIN_VERSION, "1.0.0")
        self.assertEqual(plugin_class.VERSION, "0.2.2")

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

    def test_report_context_uses_plugin_policy_settings(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        report = SimpleNamespace(
            name="Inventory Replenishment Report", description=""
        )

        values = {
            "DEFAULT_MINIMUM_STOCK": 4,
            "LOW_BUFFER_MULTIPLIER": 1.5,
        }
        plugin.get_setting = lambda key, **kwargs: values.get(
            key, kwargs.get("backup_value")
        )

        with patch.object(module, "build_report_context", return_value={}) as build:
            plugin.add_report_context(report, object(), object(), {})

        policy = build.call_args.kwargs["policy"]
        self.assertEqual(str(policy.assumed_minimum), "4")
        self.assertEqual(str(policy.target_multiplier), "1.5")

    def test_control_panel_url_is_root_relative(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()

        self.assertEqual(plugin.control_panel_url, "/plugin/inventory-manager/")

    def test_broken_spa_navigation_item_is_not_registered(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()

        self.assertEqual(plugin.get_ui_navigation_items(object(), {}), [])

    def test_reporting_shortcuts_are_registered(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()

        action = plugin.get_ui_spotlight_actions(object(), {})[0]
        dashboard = plugin.get_ui_dashboard_items(object(), {})[0]

        self.assertEqual(action["title"], "Reporting")
        self.assertIn("reporting.js:openReporting", action["source"])
        self.assertEqual(dashboard["title"], "Reporting")
        self.assertIn("reporting.js:renderReportingShortcut", dashboard["source"])


if __name__ == "__main__":
    unittest.main()
