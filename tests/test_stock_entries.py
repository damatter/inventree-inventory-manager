import unittest
from datetime import date, datetime
from decimal import Decimal
from types import ModuleType
from unittest.mock import patch

from inventory_manager.stock_entries import (
    CREATED,
    STOCK_ADD,
    StockEntry,
    load_customer_pricing_values,
    previous_month_window,
    scheduled_stock_entry_window,
    summarize_stock_entries,
    tracking_quantity,
)


class StockEntryTests(unittest.TestCase):
    def test_previous_month_handles_year_boundary(self) -> None:
        self.assertEqual(
            previous_month_window(date(2026, 1, 15)),
            (date(2025, 12, 1), date(2025, 12, 31)),
        )

    def test_scheduled_window_is_inclusive_and_ends_yesterday(self) -> None:
        self.assertEqual(
            scheduled_stock_entry_window(date(2026, 8, 15), 30),
            (date(2026, 7, 16), date(2026, 8, 14)),
        )

    def test_manual_add_uses_delta_not_resulting_balance(self) -> None:
        self.assertEqual(
            tracking_quantity(STOCK_ADD, {"added": 3, "quantity": 103}),
            Decimal("3"),
        )
        self.assertEqual(
            tracking_quantity(CREATED, {"quantity": "2.5"}), Decimal("2.5")
        )

    def test_summary_keeps_currencies_separate_and_flags_missing_values(self) -> None:
        rows = [
            StockEntry(
                1,
                datetime(2026, 7, 1),
                7,
                "Part A",
                "Received",
                Decimal("2"),
                Decimal("3"),
                "CAD",
                Decimal("6"),
            ),
            StockEntry(
                2,
                datetime(2026, 7, 2),
                8,
                "Part B",
                "Manual",
                Decimal("4"),
            ),
        ]

        summary = summarize_stock_entries(rows)
        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["total_quantity"], Decimal("6"))
        self.assertEqual(summary["valuation_totals"], [{"currency": "CAD", "total": Decimal("6")}])
        self.assertEqual(summary["unvalued_count"], 1)

    def test_customer_pricing_loader_batches_unique_parts(self) -> None:
        calls = []

        class Value:
            currency = "CAD"
            unit_material_cost = Decimal("12.50")
            lowest_sale_price = Decimal("20")
            highest_sale_price = Decimal("30")
            error = None

        reporting_module = ModuleType("inventree_customer_pricing.reporting")

        def reporting_values_for_parts(part_ids):
            calls.append(tuple(part_ids))
            return {7: Value(), 8: Value()}

        reporting_module.reporting_values_for_parts = reporting_values_for_parts
        package = ModuleType("inventree_customer_pricing")
        package.__path__ = []

        with patch.dict(
            "sys.modules",
            {
                "inventree_customer_pricing": package,
                "inventree_customer_pricing.reporting": reporting_module,
            },
        ):
            values = load_customer_pricing_values([7, 7, 8])

        self.assertEqual(calls, [(7, 8)])
        self.assertEqual(values[7]["unit_material_cost"], Decimal("12.50"))
        self.assertEqual(values[7]["lowest_sale_price"], Decimal("20"))
        self.assertEqual(values[7]["highest_sale_price"], Decimal("30"))

    def test_customer_pricing_loader_fails_closed(self) -> None:
        reporting_module = ModuleType("inventree_customer_pricing.reporting")

        def reporting_values_for_parts(_part_ids):
            raise RuntimeError("exchange rate missing")

        reporting_module.reporting_values_for_parts = reporting_values_for_parts
        package = ModuleType("inventree_customer_pricing")
        package.__path__ = []

        with patch.dict(
            "sys.modules",
            {
                "inventree_customer_pricing": package,
                "inventree_customer_pricing.reporting": reporting_module,
            },
        ):
            values = load_customer_pricing_values([7])

        self.assertIsNone(values[7]["unit_material_cost"])
        self.assertIn("exchange rate missing", values[7]["error"])


if __name__ == "__main__":
    unittest.main()
