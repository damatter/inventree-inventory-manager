import csv
import io
import unittest
from datetime import datetime
from decimal import Decimal

from inventory_manager.csv_exports import replenishment_csv, stock_entry_csv


def rows(content: bytes):
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))


class CsvExportTests(unittest.TestCase):
    def test_replenishment_csv_has_actionable_stock_fields(self) -> None:
        content = replenishment_csv(
            {
                "replenishment_items": [
                    {
                        "part_id": 7,
                        "part_name": "106868 DC",
                        "description": "Bracket",
                        "location_display": "Warehouse/G08-b",
                        "available": Decimal("2"),
                        "configured_minimum": Decimal("4"),
                        "minimum": Decimal("4"),
                        "minimum_assumed": False,
                        "target": Decimal("8"),
                        "suggested_order": Decimal("6"),
                        "status": "reorder",
                    }
                ]
            }
        )

        parsed = rows(content)
        self.assertEqual(parsed[0][0:4], ["Part ID", "Part", "Description", "Locations"])
        self.assertEqual(parsed[1][1], "106868 DC")
        self.assertEqual(parsed[1][-2:], ["6", "reorder"])

    def test_stock_entry_csv_has_accounting_fields(self) -> None:
        content = stock_entry_csv(
            {
                "stock_entry_items": [
                    {
                        "event_id": 9,
                        "entered_at": datetime(2026, 8, 1, 12, 30),
                        "part_id": 7,
                        "part_name": "106868 DC",
                        "quantity": Decimal("24"),
                        "unit_value": Decimal("2.50"),
                        "total_value": Decimal("60.00"),
                        "lowest_sale_price": Decimal("4.00"),
                        "highest_sale_price": Decimal("5.50"),
                        "currency": "CAD",
                        "location": "Warehouse/G08-b",
                        "notes": "",
                    }
                ]
            }
        )

        parsed = rows(content)
        self.assertEqual(parsed[0][0:4], ["Event ID", "Entered At", "Part ID", "Part"])
        self.assertNotIn("Source", parsed[0])
        self.assertNotIn("User", parsed[0])
        self.assertEqual(parsed[1][3], "106868 DC")
        self.assertEqual(
            parsed[0][5:10],
            [
                "Unit Material Cost",
                "Material Value",
                "Lowest Sale Price",
                "Highest Sale Price",
                "Currency",
            ],
        )
        self.assertEqual(parsed[1][5:10], ["2.50", "60.00", "4.00", "5.50", "CAD"])


if __name__ == "__main__":
    unittest.main()
