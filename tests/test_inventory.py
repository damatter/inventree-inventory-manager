from decimal import Decimal
import unittest

from inventory_manager.inventory import (
    InventoryPolicy,
    PartStock,
    StockStatus,
    build_replenishment_report,
    evaluate_part,
)


def part(
    part_id: int,
    name: str,
    available: str,
    minimum: str,
    locations: tuple[str, ...] = (),
) -> PartStock:
    return PartStock(
        part_id=part_id,
        name=name,
        description=f"{name} description",
        available=Decimal(available),
        configured_minimum=Decimal(minimum),
        locations=locations,
    )


class EvaluatePartTests(unittest.TestCase):
    def test_zero_stock_is_critical(self) -> None:
        row = evaluate_part(part(1, "Bearing", "0", "5"))

        self.assertEqual(row.status, StockStatus.CRITICAL)
        self.assertEqual(row.minimum, Decimal("5"))
        self.assertEqual(row.target, Decimal("10"))
        self.assertEqual(row.suggested_order, Decimal("10"))
        self.assertFalse(row.minimum_assumed)

    def test_missing_minimum_uses_assumed_two(self) -> None:
        row = evaluate_part(part(1, "Pin", "1", "0"))

        self.assertEqual(row.status, StockStatus.REORDER)
        self.assertEqual(row.minimum, Decimal("2"))
        self.assertEqual(row.target, Decimal("4"))
        self.assertEqual(row.suggested_order, Decimal("3"))
        self.assertTrue(row.minimum_assumed)

    def test_status_boundaries(self) -> None:
        cases = [
            ("-1", StockStatus.CRITICAL),
            ("0", StockStatus.CRITICAL),
            ("4.999999", StockStatus.REORDER),
            ("5", StockStatus.LOW_BUFFER),
            ("9.999999", StockStatus.LOW_BUFFER),
            ("10", StockStatus.HEALTHY),
        ]

        for available, expected in cases:
            with self.subTest(available=available):
                row = evaluate_part(part(1, "Part", available, "5"))
                self.assertEqual(row.status, expected)

    def test_decimal_replenishment_is_exact(self) -> None:
        row = evaluate_part(part(1, "Fluid", "1.125", "1.25"))

        self.assertEqual(row.target, Decimal("2.50"))
        self.assertEqual(row.suggested_order, Decimal("1.375"))

    def test_location_display_is_sorted_and_deduplicated(self) -> None:
        row = evaluate_part(
            part(1, "Bolt", "0", "2", ("Bin B", "Bin A", "Bin B"))
        )

        self.assertEqual(row.locations, ("Bin A", "Bin B"))
        self.assertEqual(row.location_display, "Bin A, Bin B")


class BuildReportTests(unittest.TestCase):
    def test_summary_sorting_and_healthy_exclusion(self) -> None:
        report = build_replenishment_report(
            [
                part(1, "Low", "5", "5"),
                part(2, "Healthy", "10", "5"),
                part(3, "Reorder", "4", "5"),
                part(4, "Critical Z", "0", "5"),
                part(5, "Critical A", "0", "5"),
            ]
        )

        self.assertEqual(report.critical_count, 2)
        self.assertEqual(report.reorder_count, 1)
        self.assertEqual(report.low_buffer_count, 1)
        self.assertEqual(report.healthy_count, 1)
        self.assertEqual(report.review_count, 4)
        self.assertEqual(report.parts_evaluated, 5)
        self.assertEqual(
            [row.part_name for row in report.rows],
            ["Critical A", "Critical Z", "Reorder", "Low"],
        )
        self.assertNotIn("Healthy", [row.part_name for row in report.rows])

    def test_template_context_contains_flat_and_grouped_summaries(self) -> None:
        context = build_replenishment_report([part(1, "Pin", "0", "0")]).as_context()

        self.assertEqual(context["critical_count"], 1)
        self.assertEqual(context["review_count"], 1)
        self.assertEqual(context["inventory_summary"]["critical_count"], 1)
        self.assertEqual(context["replenishment_items"][0]["minimum"], Decimal("2"))

    def test_policy_rejects_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            InventoryPolicy(assumed_minimum=Decimal("0"))

        with self.assertRaises(ValueError):
            InventoryPolicy(target_multiplier=Decimal("0.5"))


if __name__ == "__main__":
    unittest.main()

