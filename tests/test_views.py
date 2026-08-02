from decimal import Decimal
import unittest

from inventory_manager.views import _validate_settings


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


if __name__ == "__main__":
    unittest.main()
