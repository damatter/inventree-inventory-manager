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

if __name__ == "__main__":
    unittest.main()
