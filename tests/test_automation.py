import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from inventory_manager import automation


class AutomationTests(unittest.TestCase):
    def test_background_report_request_uses_django_request_factory(self) -> None:
        class FakeAnonymousUser:
            is_authenticated = False

        class FakeRequestFactory:
            get = Mock()

        def build_request(path, *, secure=False, HTTP_HOST="testserver"):
            scheme = "https" if secure else "http"
            return SimpleNamespace(
                path=path,
                user=None,
                build_absolute_uri=lambda location="/": (
                    f"{scheme}://{HTTP_HOST}{location}"
                ),
            )

        FakeRequestFactory.get.side_effect = build_request
        django_test = ModuleType("django.test")
        django_test.RequestFactory = Mock(return_value=FakeRequestFactory())
        django_auth_models = ModuleType("django.contrib.auth.models")
        django_auth_models.AnonymousUser = FakeAnonymousUser
        django_auth = ModuleType("django.contrib.auth")
        django_auth.models = django_auth_models
        django_contrib = ModuleType("django.contrib")
        django_contrib.auth = django_auth
        django_package = ModuleType("django")
        django_package.contrib = django_contrib
        django_package.test = django_test
        helpers_model = ModuleType("InvenTree.helpers_model")
        helpers_model.get_base_url = Mock(
            return_value="https://inventree.dicoreng.com"
        )
        inventree_package = ModuleType("InvenTree")
        inventree_package.helpers_model = helpers_model
        user = SimpleNamespace(pk=4)

        with patch.dict(
            sys.modules,
            {
                "django": django_package,
                "django.contrib": django_contrib,
                "django.contrib.auth": django_auth,
                "django.contrib.auth.models": django_auth_models,
                "django.test": django_test,
                "InvenTree": inventree_package,
                "InvenTree.helpers_model": helpers_model,
            },
        ):
            result = automation._background_report_request(user)

        FakeRequestFactory.get.assert_called_once_with(
            "/plugin/inventory-manager/",
            secure=True,
            HTTP_HOST="inventree.dicoreng.com",
        )
        self.assertIs(result.user, user)
        self.assertEqual(
            result.build_absolute_uri("/"),
            "https://inventree.dicoreng.com/",
        )
        self.assertNotIn("testserver", result.build_absolute_uri("/"))

    def test_background_report_request_supplies_anonymous_user(self) -> None:
        class FakeAnonymousUser:
            is_authenticated = False

        request = SimpleNamespace(path="/plugin/inventory-manager/", user=None)
        request_factory = Mock()
        request_factory.get.return_value = request
        django_test = ModuleType("django.test")
        django_test.RequestFactory = Mock(return_value=request_factory)
        django_auth_models = ModuleType("django.contrib.auth.models")
        django_auth_models.AnonymousUser = FakeAnonymousUser
        django_auth = ModuleType("django.contrib.auth")
        django_auth.models = django_auth_models
        django_contrib = ModuleType("django.contrib")
        django_contrib.auth = django_auth
        django_package = ModuleType("django")
        django_package.contrib = django_contrib
        django_package.test = django_test
        helpers_model = ModuleType("InvenTree.helpers_model")
        helpers_model.get_base_url = Mock(return_value="https://inventree.dicoreng.com")
        inventree_package = ModuleType("InvenTree")
        inventree_package.helpers_model = helpers_model

        with patch.dict(
            sys.modules,
            {
                "django": django_package,
                "django.contrib": django_contrib,
                "django.contrib.auth": django_auth,
                "django.contrib.auth.models": django_auth_models,
                "django.test": django_test,
                "InvenTree": inventree_package,
                "InvenTree.helpers_model": helpers_model,
            },
        ):
            result = automation._background_report_request()

        self.assertIsInstance(result.user, FakeAnonymousUser)
        self.assertFalse(result.user.is_authenticated)

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

    def test_stock_entry_report_reuses_one_pricing_context(self) -> None:
        output = SimpleNamespace(plugin=None, save=Mock())
        anchor = SimpleNamespace(pk=6)
        template = SimpleNamespace(print=Mock(return_value=output))
        request = SimpleNamespace(user=None)
        prepared = {"stock_entry_items": [{"part_id": 7}]}

        with (
            patch.object(automation, "find_stock_entry_template", return_value=template),
            patch.object(automation, "report_anchor", return_value=anchor),
        ):
            result = automation.generate_stock_entry_report(
                "2026-08-01",
                "2026-08-21",
                request=request,
                context=prepared,
            )

        self.assertIs(result, output)
        self.assertIs(request.inventory_manager_stock_entry_context, prepared)
        self.assertIs(output.inventory_manager_stock_entry_context, prepared)
        template.print.assert_called_once_with([anchor], request=request)

    def test_stock_entry_report_without_request_uses_django_request(self) -> None:
        output = SimpleNamespace(plugin=None, save=Mock())
        anchor = SimpleNamespace(pk=6)
        template = SimpleNamespace(print=Mock(return_value=output))
        request = SimpleNamespace(user=None, build_absolute_uri=Mock())
        prepared = {"stock_entry_items": []}

        with (
            patch.object(
                automation, "find_stock_entry_template", return_value=template
            ),
            patch.object(automation, "report_anchor", return_value=anchor),
            patch.object(
                automation, "_background_report_request", return_value=request
            ) as request_factory,
        ):
            result = automation.generate_stock_entry_report(
                "2026-08-01",
                "2026-08-21",
                context=prepared,
            )

        self.assertIs(result, output)
        request_factory.assert_called_once_with()
        self.assertIs(request.inventory_manager_stock_entry_context, prepared)
        template.print.assert_called_once_with([anchor], request=request)

    def test_manual_stock_entry_report_is_queued_with_primitive_context(self) -> None:
        output = SimpleNamespace(
            pk=91,
            refresh_from_db=Mock(),
            mark_failure=Mock(),
        )
        output_manager = Mock()
        output_manager.create.return_value = output
        data_output = SimpleNamespace(
            DataOutputTypes=SimpleNamespace(REPORT="report"),
            objects=output_manager,
        )
        common_models = ModuleType("common.models")
        common_models.DataOutput = data_output
        common_package = ModuleType("common")
        common_package.models = common_models

        offload_task = Mock(return_value="task-123")
        inventree_tasks = ModuleType("InvenTree.tasks")
        inventree_tasks.offload_task = offload_task
        inventree_package = ModuleType("InvenTree")
        inventree_package.tasks = inventree_tasks

        template = SimpleNamespace(pk=22, name="Stock entries")
        anchor = SimpleNamespace(pk=33)
        user = SimpleNamespace(pk=44, is_authenticated=True)
        request = SimpleNamespace(user=user)

        with (
            patch.dict(
                sys.modules,
                {
                    "common": common_package,
                    "common.models": common_models,
                    "InvenTree": inventree_package,
                    "InvenTree.tasks": inventree_tasks,
                },
            ),
            patch.object(
                automation, "find_stock_entry_template", return_value=template
            ),
            patch.object(automation, "report_anchor", return_value=anchor),
            patch.object(automation, "_check_report_permission") as check_permission,
        ):
            result = automation.queue_stock_entry_report(
                SimpleNamespace(isoformat=Mock(return_value="2026-08-01")),
                SimpleNamespace(isoformat=Mock(return_value="2026-08-21")),
                request,
                plugin_slug="inventory-manager",
            )

        self.assertIs(result, output)
        check_permission.assert_called_once_with(user, template)
        output_manager.create.assert_called_once_with(
            user=user,
            total=1,
            progress=0,
            complete=False,
            output_type="report",
            template_name=automation.STOCK_ENTRY_REPORT_NAME,
            plugin="inventory-manager",
            output=None,
        )
        offload_task.assert_called_once_with(
            "plugin.registry.call_plugin_function",
            "inventory-manager",
            "render_stock_entry_report_job",
            91,
            22,
            33,
            "2026-08-01",
            "2026-08-21",
            44,
            group="inventory-manager-stock-entry-report",
        )
        output.refresh_from_db.assert_called_once_with()

    def test_stock_entry_worker_rebuilds_dates_and_pricing_context(self) -> None:
        output = SimpleNamespace(pk=91, errors=None, refresh_from_db=Mock())
        output_manager = Mock()
        output_manager.get.return_value = output
        data_output = SimpleNamespace(objects=output_manager)
        common_models = ModuleType("common.models")
        common_models.DataOutput = data_output
        common_package = ModuleType("common")
        common_package.models = common_models

        anchor = SimpleNamespace(pk=33)
        anchor_manager = Mock()
        anchor_manager.get.return_value = anchor
        template = SimpleNamespace(
            get_model=Mock(
                return_value=SimpleNamespace(objects=anchor_manager)
            ),
            print=Mock(return_value=output),
        )
        template_manager = Mock()
        template_manager.get.return_value = template
        report_models = ModuleType("report.models")
        report_models.ReportTemplate = SimpleNamespace(objects=template_manager)
        report_package = ModuleType("report")
        report_package.models = report_models

        user = SimpleNamespace(pk=44)
        user_queryset = Mock()
        user_queryset.first.return_value = user
        user_model = SimpleNamespace(
            objects=SimpleNamespace(filter=Mock(return_value=user_queryset))
        )
        django_auth = ModuleType("django.contrib.auth")
        django_auth.get_user_model = Mock(return_value=user_model)
        django_contrib = ModuleType("django.contrib")
        django_contrib.auth = django_auth
        django_package = ModuleType("django")
        django_package.contrib = django_contrib
        prepared = {"stock_entry_items": [{"part_id": 7}]}
        worker_request = SimpleNamespace(
            user=user,
            build_absolute_uri=Mock(
                return_value="http://testserver/plugin/inventory-manager/"
            ),
        )
        run_manager = Mock()
        stock_run = SimpleNamespace(
            Kind=SimpleNamespace(MANUAL="manual"),
            Status=SimpleNamespace(GENERATED="generated", FAILED="failed"),
            objects=run_manager,
        )
        inventory_models = ModuleType("inventory_manager.models")
        inventory_models.StockEntryReportRun = stock_run

        with (
            patch.dict(
                sys.modules,
                {
                    "common": common_package,
                    "common.models": common_models,
                    "report": report_package,
                    "report.models": report_models,
                    "django": django_package,
                    "django.contrib": django_contrib,
                    "django.contrib.auth": django_auth,
                    "inventory_manager.models": inventory_models,
                },
            ),
            patch(
                "inventory_manager.stock_entries.build_stock_entry_context",
                return_value=prepared,
            ) as build_context,
            patch.object(
                automation,
                "_background_report_request",
                return_value=worker_request,
            ) as background_request,
            patch.object(automation, "_tag_output", return_value=output) as tag_output,
        ):
            result = automation.render_stock_entry_report_job(
                91,
                22,
                33,
                "2026-08-01",
                "2026-08-21",
                44,
            )

        self.assertIs(result, output)
        build_context.assert_called_once()
        report_request = template.print.call_args.kwargs["request"]
        self.assertEqual(str(report_request.inventory_manager_period_start), "2026-08-01")
        self.assertEqual(str(report_request.inventory_manager_period_end), "2026-08-21")
        self.assertIs(report_request.inventory_manager_stock_entry_context, prepared)
        self.assertIs(report_request.user, user)
        self.assertTrue(callable(report_request.build_absolute_uri))
        template.print.assert_called_once_with(
            [anchor], request=report_request, output=output
        )
        background_request.assert_called_once_with(user)
        tag_output.assert_called_once_with(output)
        run_manager.create.assert_called_once_with(
            kind="manual",
            period_start=report_request.inventory_manager_period_start,
            period_end=report_request.inventory_manager_period_end,
            status="generated",
            output_id=91,
            generated_by=user,
        )

    def test_stock_entry_worker_records_detailed_failure(self) -> None:
        output = SimpleNamespace(pk=91, mark_failure=Mock())
        common_models = ModuleType("common.models")
        common_models.DataOutput = SimpleNamespace(
            objects=SimpleNamespace(get=Mock(return_value=output))
        )
        common_package = ModuleType("common")
        common_package.models = common_models

        report_models = ModuleType("report.models")
        report_models.ReportTemplate = SimpleNamespace(
            objects=SimpleNamespace(get=Mock(side_effect=ValueError("template missing")))
        )
        report_package = ModuleType("report")
        report_package.models = report_models

        django_auth = ModuleType("django.contrib.auth")
        django_auth.get_user_model = Mock()
        django_contrib = ModuleType("django.contrib")
        django_contrib.auth = django_auth
        django_package = ModuleType("django")
        django_package.contrib = django_contrib

        run_manager = Mock()
        inventory_models = ModuleType("inventory_manager.models")
        inventory_models.StockEntryReportRun = SimpleNamespace(
            Kind=SimpleNamespace(MANUAL="manual"),
            Status=SimpleNamespace(FAILED="failed"),
            objects=run_manager,
        )

        with (
            patch.dict(
                sys.modules,
                {
                    "common": common_package,
                    "common.models": common_models,
                    "report": report_package,
                    "report.models": report_models,
                    "django": django_package,
                    "django.contrib": django_contrib,
                    "django.contrib.auth": django_auth,
                    "inventory_manager.models": inventory_models,
                },
            ),
            self.assertRaisesRegex(ValueError, "template missing"),
        ):
            automation.render_stock_entry_report_job(
                91,
                22,
                33,
                "2026-08-01",
                "2026-08-21",
                44,
            )

        output.mark_failure.assert_called_once_with(error="template missing")
        run_manager.create.assert_called_once()
        failed_values = run_manager.create.call_args.kwargs
        self.assertEqual(failed_values["status"], "failed")
        self.assertEqual(failed_values["output_id"], 91)
        self.assertEqual(failed_values["error"], "template missing")


if __name__ == "__main__":
    unittest.main()
