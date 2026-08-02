from pathlib import Path
import unittest


class ReportingWidgetTests(unittest.TestCase):
    def test_dashboard_renderer_uses_legacy_two_argument_signature(self) -> None:
        script_path = (
            Path(__file__).parents[1]
            / "src"
            / "inventory_manager"
            / "static"
            / "plugins"
            / "inventory-manager"
            / "reporting.js"
        )
        script = script_path.read_text(encoding="utf-8")

        self.assertIn(
            "renderReportingShortcut(target, context)",
            script,
        )
        self.assertNotIn("target.replaceChildren", script)
        self.assertIn('link.textContent = "Reporting"', script)
        self.assertIn('link.style.whiteSpace = "nowrap"', script)


if __name__ == "__main__":
    unittest.main()
