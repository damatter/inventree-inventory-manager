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

    def test_queue_report_uses_inventree_background_worker(self) -> None:
        output = SimpleNamespace(pk=77, refresh_from_db=Mock())
        output_manager = Mock()
        output_manager.create.return_value = output
        data_output = SimpleNamespace(
            objects=output_manager,
            DataOutputTypes=SimpleNamespace(REPORT="report"),
        )
        common_models = ModuleType("common.models")
        common_models.DataOutput = data_output
        common_package = ModuleType("common")
        common_package.models = common_models

        print_reports = Mock()
        report_tasks = ModuleType("report.tasks")
        report_tasks.print_reports = print_reports
        report_package = ModuleType("report")
        report_package.tasks = report_tasks

        offload_task = Mock()
        inventree_tasks = ModuleType("InvenTree.tasks")
        inventree_tasks.offload_task = offload_task
        inventree_package = ModuleType("InvenTree")
        inventree_package.tasks = inventree_tasks

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

        modules = {
            "common": common_package,
            "common.models": common_models,
            "report": report_package,
            "report.tasks": report_tasks,
            "InvenTree": inventree_package,
            "InvenTree.tasks": inventree_tasks,
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
            result = automation.queue_replenishment_report(user)

        self.assertIs(result, output)
        output_manager.create.assert_called_once_with(
            user=user,
            total=1,
            progress=0,
            complete=False,
            output_type="report",
            template_name=template.name,
            plugin="inventory-manager",
            output=None,
        )
        offload_task.assert_called_once_with(print_reports, 5, [6], 77, 9)
        check_user_permission.assert_called_once_with(user, object, "view")
        output.refresh_from_db.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
