import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from inventory_manager import automation


class AutomationTests(unittest.TestCase):
    def test_report_anchor_uses_active_physical_part(self) -> None:
        anchor = SimpleNamespace(pk=12)
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.order_by.return_value = queryset
        queryset.first.return_value = anchor
        part_model = SimpleNamespace(
            __name__="Part",
            objects=SimpleNamespace(all=Mock(return_value=queryset)),
        )
        template = SimpleNamespace(
            get_model=Mock(return_value=part_model),
            get_filters=Mock(return_value={"category": 4}),
        )

        result = automation.report_anchor(template)

        self.assertIs(result, anchor)
        queryset.filter.assert_any_call(category=4)
        queryset.filter.assert_any_call(active=True, virtual=False)
        queryset.order_by.assert_called_once_with("pk")

    def test_manual_queue_uses_installed_inventree_print_path(self) -> None:
        output = SimpleNamespace(pk=77, plugin=None, save=Mock())
        output_manager = Mock()
        output_manager.get.return_value = output
        data_output = SimpleNamespace(objects=output_manager)
        common_models = ModuleType("common.models")
        common_models.DataOutput = data_output
        common_package = ModuleType("common")
        common_package.models = common_models

        printer = Mock()
        printer.print.return_value = SimpleNamespace(data={"pk": 77})
        report_api = ModuleType("report.api")
        report_api.ReportPrint = Mock(return_value=printer)
        report_package = ModuleType("report")
        report_package.api = report_api

        class PermissionDenied(Exception):
            pass

        django_exceptions = ModuleType("django.core.exceptions")
        django_exceptions.PermissionDenied = PermissionDenied
        django_core = ModuleType("django.core")
        django_core.exceptions = django_exceptions
        django_package = ModuleType("django")
        django_package.core = django_core

        check_user_permission = Mock(return_value=True)
        user_permissions = ModuleType("users.permissions")
        user_permissions.check_user_permission = check_user_permission
        users_package = ModuleType("users")
        users_package.permissions = user_permissions

        template = SimpleNamespace(
            pk=5,
            name="Inventory Replenishment Report",
            get_model=Mock(return_value=object),
        )
        anchor = SimpleNamespace(pk=6)
        user = SimpleNamespace(pk=9, is_authenticated=True)
        request = SimpleNamespace(user=user)

        modules = {
            "common": common_package,
            "common.models": common_models,
            "report": report_package,
            "report.api": report_api,
            "django": django_package,
            "django.core": django_core,
            "django.core.exceptions": django_exceptions,
            "users": users_package,
            "users.permissions": user_permissions,
        }

        with (
            patch.dict(sys.modules, modules),
            patch.object(automation, "find_replenishment_template", return_value=template),
            patch.object(automation, "report_anchor", return_value=anchor),
        ):
            result = automation.queue_replenishment_report(request)

        self.assertIs(result, output)
        printer.print.assert_called_once_with(template, [anchor], request)
        check_user_permission.assert_called_once_with(user, object, "view")
        output_manager.get.assert_called_once_with(pk=77)
        self.assertEqual(output.plugin, "inventory-manager")
        output.save.assert_called_once_with(update_fields=["plugin"])

    def test_scheduled_report_renders_inside_existing_worker(self) -> None:
        output = SimpleNamespace(plugin=None, save=Mock())
        anchor = SimpleNamespace(pk=6)
        template = SimpleNamespace(print=Mock(return_value=output))

        with (
            patch.object(automation, "find_replenishment_template", return_value=template),
            patch.object(automation, "report_anchor", return_value=anchor),
        ):
            result = automation.generate_replenishment_report()

        self.assertIs(result, output)
        template.print.assert_called_once_with([anchor])
        self.assertEqual(output.plugin, "inventory-manager")
        output.save.assert_called_once_with(update_fields=["plugin"])


if __name__ == "__main__":
    unittest.main()
