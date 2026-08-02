from decimal import Decimal
from types import SimpleNamespace
import unittest

from inventory_manager.views import _output_error, _output_url, _validate_settings


class SettingsValidationTests(unittest.TestCase):
    def test_valid_values_are_normalized(self) -> None:
        values, errors = _validate_settings(
            {
                "default_minimum_stock": "3",
                "low_buffer_multiplier": "1.5",
                "automation_interval_days": "7",
                "automation_enabled": "on",
            }
        )

        self.assertEqual(errors, [])
        self.assertEqual(values["DEFAULT_MINIMUM_STOCK"], 3)
        self.assertEqual(values["LOW_BUFFER_MULTIPLIER"], 1.5)
        self.assertTrue(values["AUTOMATION_ENABLED"])
        self.assertEqual(values["AUTOMATION_INTERVAL_DAYS"], 7)

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


class OutputUrlTests(unittest.TestCase):
    def test_local_output_url_is_root_relative(self) -> None:
        output = SimpleNamespace(output=SimpleNamespace(url="media/report.pdf"))

        self.assertEqual(_output_url(output), "/media/report.pdf")

    def test_absolute_output_url_is_preserved(self) -> None:
        output = SimpleNamespace(
            output=SimpleNamespace(url="https://files.example/report.pdf")
        )

        self.assertEqual(_output_url(output), "https://files.example/report.pdf")


class OutputErrorTests(unittest.TestCase):
    def test_structured_worker_error_is_readable(self) -> None:
        output = type("Output", (), {"errors": {"error": "Worker failed"}})()

        self.assertEqual(_output_error(output), "Worker failed")

    def test_missing_worker_error_is_blank(self) -> None:
        output = type("Output", (), {"errors": None})()

        self.assertEqual(_output_error(output), "")


if __name__ == "__main__":
    unittest.main()
