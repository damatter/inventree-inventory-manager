import sys
import unittest
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
    report_status,
)


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
        django_shortcuts.render = Mock()

        modules = {
            "common": common_package,
            "common.models": common_models,
            "inventory_manager.models": inventory_models,
            "django": django_package,
            "django.contrib": django_contrib,
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
        data_output.objects.filter.assert_called_once_with(
            pk=11, plugin="inventory-manager"
        )
        self.assertEqual(outputs.filters, [{"user": request.user}])
        inventory_models.StockEntryReportRun.objects.filter.assert_called_once_with(
            output_id=11
        )


class ReportGenerationTemplateTests(unittest.TestCase):
    def test_both_pdf_actions_use_the_in_page_generation_flow(self) -> None:
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
        self.assertEqual(template.count('action="{{ control_panel_url }}"'), 4)
        self.assertNotIn('formtarget="_blank"', template)
        self.assertIn('id="generation-panel"', template)
        self.assertIn("event.preventDefault()", template)
        self.assertIn('formData.set("response_format", "json")', template)
        self.assertIn("[hidden] { display: none !important; }", template)
        self.assertIn("data.status_json_url", template)
        self.assertIn('id="generation-open" class="button" href="" hidden', template)
        self.assertNotIn('id="generation-open" class="button" href="" target=', template)
        self.assertIn("Generate another report", template)
        self.assertIn("{% if can_view_stock_pricing %}<section", template)
        self.assertIn("purchase-order and sales-order view roles", template)

    def test_status_screen_polls_json_without_meta_refresh(self) -> None:
        template = (
            Path(__file__).parents[1]
            / "src"
            / "inventory_manager"
            / "templates"
            / "inventory_manager"
            / "report_status.html"
        ).read_text(encoding="utf-8")

        self.assertIn('headers: {"Accept": "application/json"}', template)
        self.assertIn('id="open-pdf"', template)
        self.assertNotIn('id="open-pdf" class="button" href="{{ download_url }}" target=', template)
        self.assertIn("Return to Reporting", template)
        self.assertIn('role="progressbar"', template)
        self.assertNotIn("Report job {{ output_id }}", template)
        self.assertNotIn("window.location.assign(data.download_url)", template)
        self.assertNotIn('http-equiv="refresh"', template)

if __name__ == "__main__":
    unittest.main()
