import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from inventory_manager.views import (
    _accepts_json,
    _output_error,
    _output_url,
    _report_job_payload,
    _report_status_payload,
    _require_stock_entry_access,
    _stock_report_window,
    _validate_settings,
    control_panel,
    report_status,
)


class FakeResponse:
    """Small response stand-in for view tests which do not require Django."""

    def __init__(self, **values):
        self.headers = {}
        self.__dict__.update(values)

    def __setitem__(self, key, value):
        self.headers[key] = value


def django_view_modules(*, output=None, stock_entry_run=None):
    """Build the Django and model modules imported inside the plugin views."""

    permission_denied = type("PermissionDenied", (Exception,), {})
    validation_error = type("ValidationError", (Exception,), {})

    messages = ModuleType("django.contrib.messages")
    messages.error = Mock()
    messages.success = Mock()

    decorators = ModuleType("django.contrib.auth.decorators")
    decorators.login_required = lambda view: view
    auth = ModuleType("django.contrib.auth")
    auth.decorators = decorators
    contrib = ModuleType("django.contrib")
    contrib.auth = auth
    contrib.messages = messages

    exceptions = ModuleType("django.core.exceptions")
    exceptions.PermissionDenied = permission_denied
    exceptions.ValidationError = validation_error
    core = ModuleType("django.core")
    core.exceptions = exceptions

    http = ModuleType("django.http")

    class JsonResponse(FakeResponse):
        def __init__(self, data, status=200):
            super().__init__(data=data, status_code=status)

    http.JsonResponse = JsonResponse

    shortcuts = ModuleType("django.shortcuts")
    shortcuts.redirect = Mock(
        side_effect=lambda url: FakeResponse(status_code=302, url=str(url))
    )
    shortcuts.render = Mock(
        side_effect=lambda request, template, context: FakeResponse(
            status_code=200,
            template=template,
            context=context,
        )
    )
    shortcuts.get_object_or_404 = Mock(return_value=output)

    django = ModuleType("django")
    django.contrib = contrib
    django.core = core
    django.http = http
    django.shortcuts = shortcuts

    inventory_models = ModuleType("inventory_manager.models")
    if stock_entry_run is None:
        stock_entry_run = SimpleNamespace(
            objects=SimpleNamespace(
                filter=Mock(
                    return_value=SimpleNamespace(exists=Mock(return_value=False))
                )
            )
        )
    inventory_models.StockEntryReportRun = stock_entry_run

    modules = {
        "django": django,
        "django.contrib": contrib,
        "django.contrib.auth": auth,
        "django.contrib.auth.decorators": decorators,
        "django.contrib.messages": messages,
        "django.core": core,
        "django.core.exceptions": exceptions,
        "django.http": http,
        "django.shortcuts": shortcuts,
        "inventory_manager.models": inventory_models,
    }
    controls = SimpleNamespace(
        messages=messages,
        redirects=shortcuts.redirect,
        renders=shortcuts.render,
        get_object_or_404=shortcuts.get_object_or_404,
        PermissionDenied=permission_denied,
        ValidationError=validation_error,
    )
    return modules, controls


class SettingsValidationTests(unittest.TestCase):
    def test_valid_values_are_normalized(self) -> None:
        values, errors = _validate_settings(
            {
                "default_minimum_stock": "3",
                "low_buffer_multiplier": "1.5",
                "automation_interval_days": "7",
                "automation_enabled": "on",
                "email_recipient": " dad@example.com ",
                "email_subject": "Weekly Stock Report",
                "stock_entry_email_recipient": (
                    " accounts@example.com, owner@example.com "
                ),
                "stock_entry_automation_interval_days": "12",
            }
        )

        self.assertEqual(errors, [])
        self.assertEqual(values["DEFAULT_MINIMUM_STOCK"], 3)
        self.assertEqual(values["LOW_BUFFER_MULTIPLIER"], 1.5)
        self.assertTrue(values["AUTOMATION_ENABLED"])
        self.assertEqual(values["AUTOMATION_INTERVAL_DAYS"], 7)
        self.assertEqual(values["EMAIL_RECIPIENT"], "dad@example.com")
        self.assertEqual(values["EMAIL_SUBJECT"], "Weekly Stock Report")
        self.assertEqual(
            values["STOCK_ENTRY_EMAIL_RECIPIENT"],
            "accounts@example.com, owner@example.com",
        )
        self.assertEqual(values["STOCK_ENTRY_AUTOMATION_INTERVAL_DAYS"], 12)

    def test_invalid_values_return_safe_defaults(self) -> None:
        values, errors = _validate_settings(
            {
                "default_minimum_stock": "0",
                "low_buffer_multiplier": "not-a-number",
                "automation_interval_days": "999",
            }
        )

        self.assertEqual(len(errors), 3)
        self.assertEqual(values["DEFAULT_MINIMUM_STOCK"], 2)
        self.assertEqual(Decimal(str(values["LOW_BUFFER_MULTIPLIER"])), Decimal("2"))
        self.assertEqual(values["AUTOMATION_INTERVAL_DAYS"], 7)
        self.assertFalse(values["AUTOMATION_ENABLED"])

    def test_automation_requires_a_recipient(self) -> None:
        values, errors = _validate_settings(
            {
                "default_minimum_stock": "2",
                "low_buffer_multiplier": "2",
                "automation_interval_days": "7",
                "automation_enabled": "on",
            }
        )

        self.assertEqual(
            errors,
            [
                "Enter a replenishment recipient before enabling its automatic delivery."
            ],
        )
        self.assertEqual(values["EMAIL_RECIPIENT"], "")
        self.assertTrue(values["AUTOMATION_ENABLED"])

    def test_stock_entry_delivery_requires_recipient_and_valid_interval(self) -> None:
        values, errors = _validate_settings(
            {
                "default_minimum_stock": "2",
                "low_buffer_multiplier": "2",
                "automation_interval_days": "7",
                "stock_entry_automation_interval_days": "400",
                "stock_entry_automation_enabled": "on",
            }
        )

        self.assertEqual(values["STOCK_ENTRY_AUTOMATION_INTERVAL_DAYS"], 30)
        self.assertIn(
            "Stock-entry report interval must be between 1 and 365 days.", errors
        )
        self.assertIn(
            "Enter a stock-entry recipient before enabling its automatic delivery.",
            errors,
        )

    def test_invalid_recipient_is_rejected(self) -> None:
        values, errors = _validate_settings(
            {
                "default_minimum_stock": "2",
                "low_buffer_multiplier": "2",
                "automation_interval_days": "7",
                "email_recipient": "not-an-email",
            }
        )

        self.assertEqual(
            errors, ["Enter a valid recipient email address: not-an-email"]
        )
        self.assertEqual(values["EMAIL_RECIPIENT"], "not-an-email")


class OutputUrlTests(unittest.TestCase):
    def test_local_output_url_is_root_relative(self) -> None:
        output = SimpleNamespace(output=SimpleNamespace(url="media/report.pdf"))

        self.assertEqual(_output_url(output), "/media/report.pdf")

    def test_absolute_output_url_is_preserved(self) -> None:
        output = SimpleNamespace(
            output=SimpleNamespace(url="https://files.example/report.pdf")
        )

        self.assertEqual(_output_url(output), "https://files.example/report.pdf")


class StockReportWindowTests(unittest.TestCase):
    def test_valid_inclusive_window(self) -> None:
        start, end, error = _stock_report_window(
            {"period_start": "2026-07-01", "period_end": "2026-07-31"}
        )

        self.assertEqual(str(start), "2026-07-01")
        self.assertEqual(str(end), "2026-07-31")
        self.assertEqual(error, "")

    def test_reversed_window_is_rejected(self) -> None:
        start, end, error = _stock_report_window(
            {"period_start": "2026-08-01", "period_end": "2026-07-31"}
        )

        self.assertIsNone(start)
        self.assertIsNone(end)
        self.assertIn("must not be after", error)


class ControlPanelGenerationTests(unittest.TestCase):
    def test_render_context_uses_root_relative_control_panel_url(self) -> None:
        class EmptyQuery:
            def exclude(self, **kwargs):
                return self

            def values_list(self, *args, **kwargs):
                return []

            def select_related(self, *args, **kwargs):
                return self

            def filter(self, **kwargs):
                return self

            def order_by(self, *args):
                return self

            def count(self):
                return 0

            def __getitem__(self, key):
                del key
                return []

            def __iter__(self):
                return iter(())

        empty_query = EmptyQuery()
        stock_entry_run = SimpleNamespace(
            Status=SimpleNamespace(ACKNOWLEDGED="acknowledged", FAILED="failed"),
            objects=empty_query,
        )
        modules, controls = django_view_modules(stock_entry_run=stock_entry_run)

        timezone = ModuleType("django.utils.timezone")
        timezone.localdate = Mock(return_value=date(2026, 8, 24))
        django_utils = ModuleType("django.utils")
        django_utils.timezone = timezone
        modules["django.utils"] = django_utils
        modules["django.utils.timezone"] = timezone

        common_models = ModuleType("common.models")
        common_models.DataOutput = SimpleNamespace(objects=empty_query)
        common_package = ModuleType("common")
        common_package.models = common_models
        modules["common"] = common_package
        modules["common.models"] = common_models

        request = SimpleNamespace(
            method="GET",
            GET={},
            POST={},
            headers={},
            user=SimpleNamespace(is_staff=True),
        )
        plugin = SimpleNamespace(
            TITLE="Inventory Manager",
            VERSION="0.7.3",
            control_panel_url="/plugin/inventory-manager/",
            _setting=lambda key, fallback: fallback,
            automation_enabled=lambda: False,
            automation_interval_days=lambda: 7,
            email_recipient=lambda: "",
            email_subject=lambda: "Stock report",
            monthly_stock_report_enabled=lambda: False,
            stock_entry_email_recipient=lambda: "",
            stock_entry_email_subject=lambda: "Stock entries",
            stock_entry_automation_interval_days=lambda: 30,
        )

        with (
            patch.dict(sys.modules, modules),
            patch(
                "inventory_manager.views.user_can_view_stock_entry_pricing",
                return_value=True,
            ),
            patch("inventory_manager.views.email_delivery_available", return_value=False),
            patch("inventory_manager.views._schedule_integration_enabled", return_value=False),
        ):
            response = control_panel(request, plugin)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["control_panel_url"], "/plugin/inventory-manager/")
        controls.renders.assert_called_once_with(
            request,
            "inventory_manager/control_panel.html",
            response.context,
        )

    def test_replenishment_normal_post_queues_and_redirects_to_status(self) -> None:
        output = SimpleNamespace(pk=71, complete=False, progress=0, total=1)
        modules, controls = django_view_modules()
        request = SimpleNamespace(
            method="POST",
            GET={},
            POST={"action": "generate-report"},
            headers={"Accept": "text/html"},
            user=SimpleNamespace(is_staff=False),
        )
        plugin = SimpleNamespace(control_panel_url="/plugin/inventory-manager/")

        with (
            patch.dict(sys.modules, modules),
            patch(
                "inventory_manager.views.user_can_view_stock_entry_pricing",
                return_value=False,
            ),
            patch(
                "inventory_manager.views.queue_replenishment_report",
                return_value=output,
            ) as queue_report,
        ):
            response = control_panel(request, plugin)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/plugin/inventory-manager/report/71/")
        queue_report.assert_called_once_with(request)
        controls.redirects.assert_called_once_with(
            "/plugin/inventory-manager/report/71/"
        )

    def test_stock_entry_normal_post_generates_synchronously_then_redirects(self) -> None:
        output = SimpleNamespace(pk=72, complete=True, output=SimpleNamespace(url="report.pdf"))
        run_manager = Mock()
        stock_entry_run = SimpleNamespace(
            Kind=SimpleNamespace(MANUAL="manual"),
            Status=SimpleNamespace(GENERATED="generated"),
            objects=run_manager,
        )
        modules, controls = django_view_modules(stock_entry_run=stock_entry_run)
        user = SimpleNamespace(is_staff=False)
        request = SimpleNamespace(
            method="POST",
            GET={},
            POST={
                "action": "generate-stock-entry-report",
                "period_start": "2026-08-01",
                "period_end": "2026-08-21",
            },
            headers={"Accept": "text/html"},
            user=user,
        )
        plugin = SimpleNamespace(control_panel_url="/plugin/inventory-manager/")

        with (
            patch.dict(sys.modules, modules),
            patch(
                "inventory_manager.views.user_can_view_stock_entry_pricing",
                return_value=True,
            ),
            patch("inventory_manager.views._require_stock_entry_access") as require_access,
            patch(
                "inventory_manager.views.generate_stock_entry_report",
                return_value=output,
            ) as generate_report,
        ):
            response = control_panel(request, plugin)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/plugin/inventory-manager/report/72/")
        require_access.assert_called_once_with(user)
        generate_report.assert_called_once()
        start, end = generate_report.call_args.args
        self.assertEqual(str(start), "2026-08-01")
        self.assertEqual(str(end), "2026-08-21")
        self.assertIs(generate_report.call_args.kwargs["request"], request)
        run_manager.create.assert_called_once_with(
            kind="manual",
            period_start=start,
            period_end=end,
            status="generated",
            output_id=72,
            generated_by=user,
        )
        controls.redirects.assert_called_once_with(
            "/plugin/inventory-manager/report/72/"
        )


class OutputErrorTests(unittest.TestCase):
    def test_structured_worker_error_is_readable(self) -> None:
        output = type("Output", (), {"errors": {"error": "Worker failed"}})()

        self.assertEqual(_output_error(output), "Worker failed")

    def test_missing_worker_error_is_blank(self) -> None:
        output = type("Output", (), {"errors": None})()

        self.assertEqual(_output_error(output), "")


class ReportStatusPayloadTests(unittest.TestCase):
    def test_stock_entry_access_fails_closed_when_pricing_denies_user(self) -> None:
        class PermissionDenied(Exception):
            pass

        django_package = ModuleType("django")
        django_core = ModuleType("django.core")
        django_exceptions = ModuleType("django.core.exceptions")
        django_exceptions.PermissionDenied = PermissionDenied
        django_core.exceptions = django_exceptions
        django_package.core = django_core

        with (
            patch(
                "inventory_manager.views.user_can_view_stock_entry_pricing",
                return_value=False,
            ),
            patch.dict(
                sys.modules,
                {
                    "django": django_package,
                    "django.core": django_core,
                    "django.core.exceptions": django_exceptions,
                },
            ),
            self.assertRaises(PermissionDenied),
        ):
            _require_stock_entry_access(object())

    def test_json_accept_detection_is_explicit(self) -> None:
        self.assertTrue(
            _accepts_json(SimpleNamespace(headers={"Accept": "application/json"}))
        )
        self.assertFalse(_accepts_json(SimpleNamespace(headers={"Accept": "text/html"})))
        self.assertTrue(
            _accepts_json(
                SimpleNamespace(
                    GET={},
                    POST={"response_format": "json"},
                    headers={"Accept": "text/html"},
                )
            )
        )
        self.assertTrue(
            _accepts_json(
                SimpleNamespace(
                    GET={"format": "json"},
                    POST={},
                    headers={"Accept": "text/html"},
                )
            )
        )

    def test_pending_job_reports_progress_without_exposing_file(self) -> None:
        output = SimpleNamespace(
            pk=7,
            complete=False,
            progress=2,
            total=5,
            errors=None,
            output=SimpleNamespace(url="media/unfinished.pdf"),
        )

        payload = _report_status_payload(output)

        self.assertEqual(payload["state"], "pending")
        self.assertEqual(payload["progress"], 2)
        self.assertEqual(payload["total"], 5)
        self.assertEqual(payload["download_url"], "")

    def test_complete_job_has_root_relative_pdf_url(self) -> None:
        output = SimpleNamespace(
            pk=8,
            complete=True,
            progress=1,
            total=1,
            errors=None,
            output=SimpleNamespace(url="media/ready.pdf"),
        )

        payload = _report_status_payload(output)

        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["download_url"], "/media/ready.pdf")

    def test_job_payload_keeps_the_existing_status_route(self) -> None:
        output = SimpleNamespace(
            pk=12,
            complete=False,
            progress=0,
            total=1,
            errors=None,
            output=None,
        )

        payload = _report_job_payload(output, "/plugin/inventory-manager/")

        self.assertEqual(
            payload["status_url"], "/plugin/inventory-manager/report/12/"
        )
        self.assertEqual(
            payload["status_json_url"],
            "/plugin/inventory-manager/report/12/?format=json",
        )
        self.assertEqual(payload["state"], "pending")

    def test_worker_error_is_terminal_and_readable(self) -> None:
        output = SimpleNamespace(
            pk=9,
            complete=False,
            progress=0,
            total=0,
            errors={"error": "PDF renderer failed"},
            output=None,
        )

        payload = _report_status_payload(output)

        self.assertEqual(payload["state"], "error")
        self.assertIn("PDF renderer failed", payload["message"])

    def test_complete_job_without_file_is_an_error(self) -> None:
        output = SimpleNamespace(
            pk=10,
            complete=True,
            progress=1,
            total=1,
            errors=None,
            output=None,
        )

        payload = _report_status_payload(output)

        self.assertEqual(payload["state"], "error")
        self.assertIn("without a downloadable PDF", payload["message"])

    def test_status_route_returns_authenticated_json(self) -> None:
        output = SimpleNamespace(
            pk=11,
            complete=True,
            progress=1,
            total=1,
            errors=None,
            output=SimpleNamespace(url="media/stock-entry.pdf"),
        )

        class FakeQuerySet:
            def __init__(self):
                self.filters = []

            def filter(self, **kwargs):
                self.filters.append(kwargs)
                return self

        outputs = FakeQuerySet()
        data_output = SimpleNamespace(
            objects=SimpleNamespace(filter=Mock(return_value=outputs))
        )
        common_models = ModuleType("common.models")
        common_models.DataOutput = data_output
        common_package = ModuleType("common")
        common_package.models = common_models
        stock_run_filter = SimpleNamespace(exists=Mock(return_value=False))
        inventory_models = ModuleType("inventory_manager.models")
        inventory_models.StockEntryReportRun = SimpleNamespace(
            objects=SimpleNamespace(filter=Mock(return_value=stock_run_filter))
        )

        class JsonResponse:
            def __init__(self, data):
                self.data = data
                self.headers = {}

            def __setitem__(self, key, value):
                self.headers[key] = value

        django_package = ModuleType("django")
        django_contrib = ModuleType("django.contrib")
        django_messages = ModuleType("django.contrib.messages")
        django_messages.error = Mock()
        django_contrib.messages = django_messages
        django_auth = ModuleType("django.contrib.auth")
        django_decorators = ModuleType("django.contrib.auth.decorators")
        django_decorators.login_required = lambda view: view
        django_core = ModuleType("django.core")
        django_exceptions = ModuleType("django.core.exceptions")
        django_exceptions.PermissionDenied = type("PermissionDenied", (Exception,), {})
        django_core.exceptions = django_exceptions
        django_http = ModuleType("django.http")
        django_http.JsonResponse = JsonResponse
        django_shortcuts = ModuleType("django.shortcuts")
        django_shortcuts.get_object_or_404 = lambda queryset: output
        django_shortcuts.redirect = Mock()
        django_shortcuts.render = Mock()

        modules = {
            "common": common_package,
            "common.models": common_models,
            "inventory_manager.models": inventory_models,
            "django": django_package,
            "django.contrib": django_contrib,
            "django.contrib.messages": django_messages,
            "django.contrib.auth": django_auth,
            "django.contrib.auth.decorators": django_decorators,
            "django.core": django_core,
            "django.core.exceptions": django_exceptions,
            "django.http": django_http,
            "django.shortcuts": django_shortcuts,
        }
        request = SimpleNamespace(
            GET={"format": "json"},
            headers={},
            user=SimpleNamespace(is_staff=False),
        )
        plugin = SimpleNamespace(
            TITLE="Inventory Manager",
            control_panel_url="/plugin/inventory-manager/",
        )

        with patch.dict(sys.modules, modules):
            response = report_status(request, plugin, output.pk)

        self.assertEqual(response.data["state"], "ready")
        self.assertEqual(response.data["download_url"], "/media/stock-entry.pdf")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        django_shortcuts.render.assert_not_called()
        django_shortcuts.redirect.assert_not_called()
        data_output.objects.filter.assert_called_once_with(
            pk=11, plugin="inventory-manager"
        )
        self.assertEqual(outputs.filters, [{"user": request.user}])
        inventory_models.StockEntryReportRun.objects.filter.assert_called_once_with(
            output_id=11
        )


class ReportStatusRouteTests(unittest.TestCase):
    def call_status(self, output):
        output_queryset = SimpleNamespace(filter=Mock(return_value=None))
        data_output = SimpleNamespace(
            objects=SimpleNamespace(filter=Mock(return_value=output_queryset))
        )
        common_models = ModuleType("common.models")
        common_models.DataOutput = data_output
        common_package = ModuleType("common")
        common_package.models = common_models

        modules, controls = django_view_modules(output=output)
        modules["common"] = common_package
        modules["common.models"] = common_models
        request = SimpleNamespace(
            GET={},
            POST={},
            headers={"Accept": "text/html"},
            user=SimpleNamespace(is_staff=True),
        )
        plugin = SimpleNamespace(
            TITLE="Inventory Manager",
            control_panel_url="/plugin/inventory-manager/",
        )

        with patch.dict(sys.modules, modules):
            response = report_status(request, plugin, output.pk)

        data_output.objects.filter.assert_called_once_with(
            pk=output.pk,
            plugin="inventory-manager",
        )
        return response, request, controls

    def test_pending_status_renders_auto_refresh_screen(self) -> None:
        output = SimpleNamespace(
            pk=81,
            template_name="Inventory Replenishment Report",
            complete=False,
            progress=0,
            total=1,
            errors=None,
            output=None,
        )

        response, request, controls = self.call_status(output)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template, "inventory_manager/report_status.html")
        self.assertEqual(response.context["state"], "pending")
        self.assertEqual(
            response.context["control_panel_url"],
            "/plugin/inventory-manager/",
        )
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        controls.renders.assert_called_once_with(
            request,
            "inventory_manager/report_status.html",
            response.context,
        )
        controls.redirects.assert_not_called()

    def test_ready_status_renders_download_then_return_screen(self) -> None:
        output = SimpleNamespace(
            pk=82,
            template_name="Inventory Replenishment Report",
            complete=True,
            progress=1,
            total=1,
            errors=None,
            output=SimpleNamespace(url="media/replenishment.pdf"),
        )

        response, request, controls = self.call_status(output)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template, "inventory_manager/report_complete.html")
        self.assertEqual(
            response.context,
            {
                "download_url": "/media/replenishment.pdf",
                "control_panel_url": "/plugin/inventory-manager/",
            },
        )
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        controls.renders.assert_called_once_with(
            request,
            "inventory_manager/report_complete.html",
            response.context,
        )
        controls.redirects.assert_not_called()

    def test_error_status_returns_to_reporting_with_message(self) -> None:
        output = SimpleNamespace(
            pk=83,
            template_name="Inventory Replenishment Report",
            complete=False,
            progress=0,
            total=1,
            errors={"error": "PDF renderer failed"},
            output=None,
        )

        response, request, controls = self.call_status(output)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/plugin/inventory-manager/")
        controls.messages.error.assert_called_once_with(
            request,
            "Report generation failed: PDF renderer failed",
        )
        controls.redirects.assert_called_once_with("/plugin/inventory-manager/")
        controls.renders.assert_not_called()


class ReportGenerationTemplateTests(unittest.TestCase):
    def test_both_pdf_actions_use_normal_same_tab_post_with_loading_overlay(self) -> None:
        template = (
            Path(__file__).parents[1]
            / "src"
            / "inventory_manager"
            / "templates"
            / "inventory_manager"
            / "control_panel.html"
        ).read_text(encoding="utf-8")

        self.assertIn('value="generate-report" type="submit">Generate PDF', template)
        self.assertIn('value="generate-stock-entry-report" type="submit">Generate PDF', template)
        self.assertEqual(template.count('class="button pdf-generation-button"'), 2)
        self.assertEqual(template.count('class="workflow-form pdf-generation-form"'), 2)
        self.assertEqual(template.count('action="{{ control_panel_url }}"'), 4)
        self.assertNotIn('formtarget="_blank"', template)
        self.assertNotIn("window.open", template)
        self.assertNotIn("event.preventDefault()", template)
        self.assertNotIn("window.fetch", template)
        self.assertNotIn("fetch(", template)
        self.assertNotIn("FormData", template)
        self.assertNotIn("generationButtons", template)
        self.assertNotIn("submitter.disabled", template)
        self.assertNotIn("disabled = true", template)
        self.assertIn('id="generation-overlay"', template)
        self.assertIn('id="generation-title"', template)
        self.assertIn("[hidden] { display: none !important; }", template)
        self.assertIn('document.querySelectorAll(".pdf-generation-form")', template)
        self.assertIn('window.addEventListener("pageshow", resetOverlay)', template)
        self.assertIn("{% if can_view_stock_pricing %}<section", template)
        self.assertIn("purchase-order and sales-order view roles", template)

    def test_status_screen_uses_server_refresh_until_automatic_download(self) -> None:
        template = (
            Path(__file__).parents[1]
            / "src"
            / "inventory_manager"
            / "templates"
            / "inventory_manager"
            / "report_status.html"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '{% if state == "pending" %}<meta http-equiv="refresh" content="2">',
            template,
        )
        self.assertIn("The download will begin automatically", template)
        self.assertIn("Return to Reporting", template)
        self.assertIn('role="progressbar"', template)
        self.assertNotIn("Progress: 0 of 1", template)
        self.assertNotIn("Report job {{ output_id }}", template)
        self.assertNotIn("window.fetch", template)
        self.assertNotIn("fetch(", template)
        self.assertNotIn('target="_blank"', template)

    def test_complete_screen_downloads_in_place_then_returns_to_reporting(self) -> None:
        template = (
            Path(__file__).parents[1]
            / "src"
            / "inventory_manager"
            / "templates"
            / "inventory_manager"
            / "report_complete.html"
        ).read_text(encoding="utf-8")

        self.assertIn('<iframe src="{{ download_url }}"', template)
        self.assertIn('iframe { display: none; }', template)
        self.assertIn('<a href="{{ download_url }}">Download the PDF again</a>', template)
        self.assertIn('<a href="{{ control_panel_url }}">Return now</a>', template)
        self.assertIn(
            '<meta http-equiv="refresh" content="4;url={{ control_panel_url }}">',
            template,
        )
        self.assertIn(
            'window.location.replace("{{ control_panel_url|escapejs }}")',
            template,
        )
        self.assertNotIn('target="_blank"', template)

if __name__ == "__main__":
    unittest.main()
