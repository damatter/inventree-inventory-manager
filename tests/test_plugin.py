import importlib
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class FakeInvenTreePlugin:
    """Minimal stand-in for the InvenTree plugin base class."""


class FakeReportMixin:
    """Minimal stand-in for InvenTree's report mixin."""


class FakeAppMixin:
    """Minimal stand-in for InvenTree's Django app mixin."""


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
    mixins_module.AppMixin = FakeAppMixin
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
        self.assertEqual(plugin_class.MIN_VERSION, "1.3.2")
        self.assertEqual(plugin_class.MAX_VERSION, "1.3.99")
        self.assertEqual(plugin_class.VERSION, "0.6.1")
        from inventory_manager import __version__

        self.assertEqual(__version__, plugin_class.VERSION)

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

    def test_stock_entry_report_receives_requested_window(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        report = SimpleNamespace(name="Monthly Stock Entry Report", description="")
        request = SimpleNamespace(
            inventory_manager_period_start="2026-07-01",
            inventory_manager_period_end="2026-07-31",
        )

        with patch.object(
            module,
            "build_stock_entry_context",
            return_value={"event_count": 4},
        ) as build:
            context = {}
            plugin.add_report_context(report, object(), request, context)

        build.assert_called_once_with("2026-07-01", "2026-07-31")
        self.assertEqual(context["event_count"], 4)

    def test_control_panel_url_is_root_relative(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()

        self.assertEqual(plugin.control_panel_url, "/plugin/inventory-manager/")

    def test_broken_spa_navigation_item_is_not_registered(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()

        self.assertEqual(plugin.get_ui_navigation_items(object(), {}), [])

    def test_reporting_shortcuts_use_plugin_served_script(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()

        action = plugin.get_ui_spotlight_actions(object(), {})[0]
        dashboard = plugin.get_ui_dashboard_items(object(), {})[0]

        self.assertEqual(action["title"], "Reporting")
        self.assertEqual(
            action["source"],
            "/plugin/inventory-manager/reporting.js:openReporting?v=0.6.1",
        )
        self.assertEqual(dashboard["title"], "Reporting")
        self.assertEqual(
            dashboard["options"],
            {
                "width": 3,
                "height": 2,
                "mobile": {
                    "schema_version": 1,
                    "renderer": "summary-list-v1",
                    "endpoint": "/plugin/inventory-manager/mobile/dashboard/",
                },
            },
        )
        self.assertEqual(
            dashboard["source"],
            "/plugin/inventory-manager/reporting.js:renderReportingShortcut?v=0.6.1",
        )

    def test_mobile_dashboard_returns_versioned_summary(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        response_module = ModuleType("rest_framework.response")

        class Response:
            def __init__(self, data):
                self.data = data

        response_module.Response = Response
        report_context = {
            "inventory_summary": {
                "critical_count": 1,
                "reorder_count": 2,
                "low_buffer_count": 3,
                "healthy_count": 4,
                "review_count": 6,
                "parts_evaluated": 10,
            },
            "replenishment_items": [
                {
                    "part_id": 42,
                    "part_name": "Widget",
                    "available": 1,
                    "suggested_order": 5,
                    "status": "reorder",
                }
            ],
        }

        with (
            patch.dict(sys.modules, {"rest_framework.response": response_module}),
            patch.object(module, "build_report_context", return_value=report_context),
        ):
            response = plugin.mobile_dashboard_view(object())

        self.assertEqual(response.data["schema_version"], 1)
        self.assertEqual(response.data["sections"][1]["items"][0]["action"]["pk"], 42)

    def test_email_schedule_requires_enabled_automation_and_recipient(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        values = {
            "AUTOMATION_ENABLED": True,
            "AUTOMATION_INTERVAL_DAYS": 7,
            "EMAIL_RECIPIENT": "dad@example.com",
        }
        plugin.get_setting = lambda key, **kwargs: values.get(
            key, kwargs.get("backup_value")
        )

        task = plugin.get_scheduled_tasks()["replenishment_report"]

        self.assertEqual(task["func"], "run_scheduled_report")
        self.assertEqual(task["schedule"], "I")
        self.assertEqual(task["minutes"], 7 * 24 * 60)
        self.assertEqual(task["repeats"], -1)

        values["EMAIL_RECIPIENT"] = ""
        self.assertEqual(plugin.get_scheduled_tasks(), {})

    def test_stock_entry_report_uses_interval_schedule(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        values = {
            "MONTHLY_STOCK_REPORT_ENABLED": True,
            "EMAIL_RECIPIENT": "dad@example.com",
        }
        plugin.get_setting = lambda key, **kwargs: values.get(
            key, kwargs.get("backup_value")
        )

        task = plugin.get_scheduled_tasks()["monthly_stock_entry_report"]
        self.assertEqual(task["func"], "run_scheduled_stock_entry_report")
        self.assertEqual(task["schedule"], "I")
        self.assertEqual(task["minutes"], 30 * 24 * 60)

    def test_stock_entry_delivery_can_use_an_independent_recipient(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        values = {
            "MONTHLY_STOCK_REPORT_ENABLED": True,
            "EMAIL_RECIPIENT": "",
            "STOCK_ENTRY_EMAIL_RECIPIENT": "accounting@example.com",
            "STOCK_ENTRY_AUTOMATION_INTERVAL_DAYS": 12,
        }
        plugin.get_setting = lambda key, **kwargs: values.get(
            key, kwargs.get("backup_value")
        )

        self.assertEqual(plugin.stock_entry_email_recipient(), "accounting@example.com")
        self.assertEqual(plugin.stock_entry_automation_interval_days(), 12)
        self.assertIn("monthly_stock_entry_report", plugin.get_scheduled_tasks())

    def test_manual_email_uses_saved_recipient_and_subject(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        values = {
            "EMAIL_RECIPIENT": "dad@example.com",
            "EMAIL_SUBJECT": "Weekly Stock Report",
            "AUTOMATION_ENABLED": False,
        }
        plugin.get_setting = lambda key, **kwargs: values.get(
            key, kwargs.get("backup_value")
        )

        with (
            patch.object(module, "build_report_context", return_value={}),
            patch.object(module, "replenishment_csv", return_value=b"csv"),
            patch.object(
                module,
                "generate_and_email_replenishment_report",
                return_value="output",
            ) as deliver,
        ):
            result = plugin.send_configured_report_email()

        self.assertEqual(result, "output")
        deliver.assert_called_once_with(
            "dad@example.com",
            "Weekly Stock Report",
            b"csv",
        )

    def test_scheduled_run_delivers_once_when_enabled(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        plugin.get_setting = lambda key, **kwargs: {
            "AUTOMATION_ENABLED": True,
            "EMAIL_RECIPIENT": "dad@example.com",
        }.get(key, kwargs.get("backup_value"))

        with patch.object(plugin, "send_configured_report_email") as deliver:
            plugin.run_scheduled_report()

        deliver.assert_called_once_with()

    def test_scheduled_run_stops_when_automation_is_disabled(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()
        plugin.get_setting = lambda key, **kwargs: {
            "AUTOMATION_ENABLED": False,
            "EMAIL_RECIPIENT": "dad@example.com",
        }.get(key, kwargs.get("backup_value"))

        with patch.object(plugin, "send_configured_report_email") as deliver:
            plugin.run_scheduled_report()

        deliver.assert_not_called()

    def test_reporting_script_route_is_auth_exempt(self) -> None:
        module = import_plugin_module()
        plugin = module.InventoryManagerPlugin()

        django_package = ModuleType("django")
        django_urls = ModuleType("django.urls")
        inventree_package = ModuleType("InvenTree")
        inventree_permissions = ModuleType("InvenTree.permissions")

        def path(route, callback, name):
            return SimpleNamespace(route=route, callback=callback, name=name)

        def auth_exempt(callback):
            def wrapped(*args, **kwargs):
                return callback(*args, **kwargs)

            wrapped.auth_exempt = True
            return wrapped

        django_urls.path = path
        inventree_permissions.auth_exempt = auth_exempt

        with patch.dict(
            sys.modules,
            {
                "django": django_package,
                "django.urls": django_urls,
                "InvenTree": inventree_package,
                "InvenTree.permissions": inventree_permissions,
            },
        ):
            routes = plugin.setup_urls()

        self.assertEqual(routes[0].route, "reporting.js")
        self.assertTrue(routes[0].callback.auth_exempt)


if __name__ == "__main__":
    unittest.main()
