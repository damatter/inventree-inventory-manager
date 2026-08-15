import unittest
from decimal import Decimal
from types import SimpleNamespace

from inventory_manager.views import (
    _output_error,
    _output_url,
    _stock_report_window,
    _validate_settings,
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


if __name__ == "__main__":
    unittest.main()
