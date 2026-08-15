import unittest
from datetime import date, datetime
from decimal import Decimal

from inventory_manager.stock_entries import (
    CREATED,
    STOCK_ADD,
    StockEntry,
    previous_month_window,
    summarize_stock_entries,
    tracking_quantity,
)


class StockEntryTests(unittest.TestCase):
    def test_previous_month_handles_year_boundary(self) -> None:
        self.assertEqual(
            previous_month_window(date(2026, 1, 15)),
            (date(2025, 12, 1), date(2025, 12, 31)),
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


if __name__ == "__main__":
    unittest.main()
