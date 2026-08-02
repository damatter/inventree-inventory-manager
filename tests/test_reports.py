from decimal import Decimal
from types import SimpleNamespace
import unittest

from inventory_manager.inventory import PartStock
from inventory_manager.reports import (
    build_report_context,
    is_replenishment_report_template,
)


class ReportAdapterTests(unittest.TestCase):
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

