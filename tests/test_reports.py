import unittest
from decimal import Decimal
from types import SimpleNamespace

from inventory_manager.inventory import PartStock
from inventory_manager.reports import (
    build_report_context,
    compact_stock_location,
    is_replenishment_report_template,
    is_stock_entry_report_template,
)


class ReportAdapterTests(unittest.TestCase):
    def test_stock_location_is_compacted_to_root_and_leaf(self) -> None:
        location = SimpleNamespace(
            name="A09-c",
            pathstring="DCWarehouse/A/09/A09-c",
            description="Stock Location A09-c",
        )

        self.assertEqual(compact_stock_location(location), "DCWarehouse/A09-c")

    def test_top_level_stock_location_is_not_repeated(self) -> None:
        location = SimpleNamespace(name="DCWarehouse", pathstring="DCWarehouse")

        self.assertEqual(compact_stock_location(location), "DCWarehouse")

    def test_missing_stock_location_is_blank(self) -> None:
        self.assertEqual(compact_stock_location(None), "")

    def test_exact_report_name_opts_in(self) -> None:
        report = SimpleNamespace(
            name="  Inventory Replenishment Report ", description=""
        )

        self.assertTrue(is_replenishment_report_template(report))

    def test_description_marker_opts_in(self) -> None:
        report = SimpleNamespace(
            name="Weekly Stock", description="For Dad [INVENTORY-MANAGER:REPLENISHMENT]"
        )

        self.assertTrue(is_replenishment_report_template(report))

    def test_unrelated_report_does_not_opt_in(self) -> None:
        report = SimpleNamespace(name="Purchase Order", description="Supplier copy")

        self.assertFalse(is_replenishment_report_template(report))

    def test_stock_entry_marker_opts_into_the_separate_context(self) -> None:
        report = SimpleNamespace(
            name="Accounting inflows",
            description="[inventory-manager:stock-entries]",
        )

        self.assertTrue(is_stock_entry_report_template(report))
        self.assertFalse(is_replenishment_report_template(report))

    def test_context_can_be_built_without_django(self) -> None:
        snapshots = [
            PartStock(
                part_id=7,
                name="Test Part",
                description="",
                available=Decimal("1"),
                configured_minimum=Decimal("2"),
            )
        ]

        context = build_report_context(snapshots)

        self.assertEqual(context["reorder_count"], 1)
        self.assertEqual(context["replenishment_items"][0]["part_id"], 7)


if __name__ == "__main__":
    unittest.main()
