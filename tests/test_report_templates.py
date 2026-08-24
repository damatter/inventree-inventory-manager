import unittest
from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).parents[1]
    / "src"
    / "inventory_manager"
    / "templates"
    / "inventory_manager"
)


class ReportTemplateTests(unittest.TestCase):
    def test_stock_entry_columns_use_customer_pricing_values(self) -> None:
        template = (TEMPLATE_ROOT / "stock_entry_report.html").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("Total units entered", template)
        self.assertNotIn(">Source<", template)
        self.assertNotIn(">User<", template)
        self.assertIn("Material Value", template)
        self.assertIn("Lowest Sale / Unit", template)
        self.assertIn("Highest Sale / Unit", template)

    def test_replenishment_summary_uses_the_saved_policy(self) -> None:
        template = (TEMPLATE_ROOT / "replenishment_report.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("inventory_policy.target_multiplier", template)
        self.assertIn("inventory_policy.assumed_minimum", template)
        self.assertNotIn("twice the minimum", template.casefold())


if __name__ == "__main__":
    unittest.main()
