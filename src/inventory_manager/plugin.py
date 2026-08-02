"""InvenTree plugin entry point."""

from plugin import InvenTreePlugin
from plugin.mixins import (
    ReportMixin,
    ScheduleMixin,
    SettingsMixin,
    UrlsMixin,
    UserInterfaceMixin,
)

from .automation import generate_replenishment_report
from .inventory import InventoryPolicy
from .reports import build_report_context, is_replenishment_report_template


class InventoryManagerPlugin(
    ReportMixin,
    SettingsMixin,
    ScheduleMixin,
    UrlsMixin,
    UserInterfaceMixin,
    InvenTreePlugin,
):
    """Provide replenishment reports, settings, and scheduled generation."""

    NAME = "InventoryManager"
    SLUG = "inventory-manager"
    TITLE = "Inventory Manager"
    DESCRIPTION = "Stock-level reporting and replenishment planning"
    VERSION = "0.2.1"
    AUTHOR = "Matt Dick"
    MIN_VERSION = "1.0.0"
    LICENSE = "MIT"

    SETTINGS = {
        "DEFAULT_MINIMUM_STOCK": {
            "name": "Default minimum stock",
            "description": (
                "Minimum used when a part does not have minimum stock configured"
            ),
            "default": 2,
            "validator": int,
        },
        "LOW_BUFFER_MULTIPLIER": {
            "name": "Low-buffer multiplier",
            "description": (
                "Stock below this multiple of the minimum is shown as low buffer"
            ),
            "default": 2.0,
            "validator": float,
        },
        "AUTOMATION_ENABLED": {
            "name": "Automatic reports",
            "description": "Generate a replenishment report on a repeating schedule",
            "default": False,
            "validator": bool,
        },
        "AUTOMATION_INTERVAL_DAYS": {
            "name": "Report interval",
            "description": "Number of days between automatic replenishment reports",
            "default": 7,
            "validator": int,
            "units": "days",
        },
    }

    def get_inventory_policy(self) -> InventoryPolicy:
        """Build the current report policy from persistent plugin settings."""

        return InventoryPolicy(
            assumed_minimum=self._setting("DEFAULT_MINIMUM_STOCK", 2),
            target_multiplier=self._setting("LOW_BUFFER_MULTIPLIER", 2),
        )

    def _setting(self, key: str, default: object) -> object:
        """Read a setting while remaining safe during early plugin startup."""

        try:
            value = self.get_setting(key, backup_value=default)
        except Exception:
            return default

        return default if value in (None, "") else value

    def automation_enabled(self) -> bool:
        """Return whether scheduled report generation is enabled."""

        value = self._setting("AUTOMATION_ENABLED", False)
        if isinstance(value, str):
            return value.strip().casefold() in {"1", "true", "yes", "on"}
        return bool(value)

    def automation_interval_days(self) -> int:
        """Return the validated automatic report interval."""

        try:
            value = int(self._setting("AUTOMATION_INTERVAL_DAYS", 7))
        except (TypeError, ValueError):
            value = 7
        return min(max(value, 1), 365)

    def get_scheduled_tasks(self) -> dict[str, dict[str, object]]:
        """Dynamically register one repeating report task when enabled."""

        if not self.automation_enabled():
            return {}

        return {
            "replenishment_report": {
                "func": "run_scheduled_report",
                "schedule": "I",
                "minutes": self.automation_interval_days() * 24 * 60,
                "repeats": -1,
            }
        }

    def refresh_automation_schedule(self) -> None:
        """Apply an automation setting change without requiring a plugin reload."""

        task_name = self.get_task_name("replenishment_report")

        if self.automation_enabled():
            self.register_tasks()
            return

        from django_q.models import Schedule

        Schedule.objects.filter(name=task_name).delete()

    def run_scheduled_report(self) -> None:
        """Queue the configured automatic replenishment report."""

        if self.automation_enabled():
            generate_replenishment_report()

    def setup_urls(self):
        """Expose the simple Inventory Manager control panel."""

        from django.urls import path

        return [
            path("", self.control_panel_view, name="control-panel"),
            path(
                "report/<int:output_id>/",
                self.report_status_view,
                name="report-status",
            ),
        ]

    def control_panel_view(self, request):
        """Render the settings and manual report interface."""

        from .views import control_panel

        return control_panel(request, self)

    def report_status_view(self, request, output_id: int):
        """Show report progress and redirect to the completed PDF."""

        from .views import report_status

        return report_status(request, self, output_id)

    def get_ui_navigation_items(self, request, context, **kwargs):
        """Add Inventory Manager to the main InvenTree navigation."""

        del request, context, kwargs
        return [
            {
                "key": "inventory-manager",
                "title": "Inventory Manager",
                "description": "Stock reports and replenishment settings",
                "icon": "ti:report-analytics",
                "options": {"url": self.base_url},
            }
        ]

    def add_report_context(
        self, report_instance, model_instance, request, context
    ) -> None:
        """Inject replenishment rows and summary totals at report render time."""

        del model_instance, request

        if not is_replenishment_report_template(report_instance):
            return

        context.update(build_report_context(policy=self.get_inventory_policy()))
