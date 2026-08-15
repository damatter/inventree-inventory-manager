"""InvenTree plugin entry point."""

from plugin import InvenTreePlugin
from plugin.mixins import (
    AppMixin,
    ReportMixin,
    ScheduleMixin,
    SettingsMixin,
    UrlsMixin,
    UserInterfaceMixin,
)

from .emailing import (
    DEFAULT_EMAIL_SUBJECT,
    generate_and_email_replenishment_report,
    send_stock_entry_report_email,
)
from .inventory import InventoryPolicy
from .mobile import MobileAppMixin
from .reports import (
    build_report_context,
    is_replenishment_report_template,
    is_stock_entry_report_template,
)
from .stock_entries import build_stock_entry_context, previous_month_window


class InventoryManagerPlugin(
    MobileAppMixin,
    ReportMixin,
    SettingsMixin,
    ScheduleMixin,
    AppMixin,
    UrlsMixin,
    UserInterfaceMixin,
    InvenTreePlugin,
):
    """Provide replenishment reports, settings, and scheduled generation."""

    NAME = "InventoryManager"
    SLUG = "inventory-manager"
    TITLE = "Inventory Manager"
    DESCRIPTION = "Stock-level reporting and replenishment planning"
    VERSION = "0.4.0"
    AUTHOR = "Matt Dick"
    MIN_VERSION = "1.3.2"
    MAX_VERSION = "1.3.99"
    LICENSE = "MIT"

    MOBILE_APP_FEATURES = (
        {
            "feature_type": "dashboard",
            "key": "reporting-shortcut",
            "title": "Reporting",
            "renderer": "summary-list-v1",
            "endpoint": "/plugin/inventory-manager/mobile/dashboard/",
        },
    )

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
        "EMAIL_RECIPIENT": {
            "name": "Report recipient",
            "description": "Email address that receives automatic reports",
            "default": "",
            "validator": str,
        },
        "EMAIL_SUBJECT": {
            "name": "Email subject",
            "description": "Subject line used for replenishment report emails",
            "default": DEFAULT_EMAIL_SUBJECT,
            "validator": str,
        },
        "AUTOMATION_ENABLED": {
            "name": "Automatic reports",
            "description": "Generate and email a report on a repeating schedule",
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
        "MONTHLY_STOCK_REPORT_ENABLED": {
            "name": "Monthly stock-entry report",
            "description": "Email the prior calendar month's inventory inflows once per month",
            "default": False,
            "validator": bool,
        },
        "STOCK_ENTRY_EMAIL_SUBJECT": {
            "name": "Stock-entry email subject",
            "description": "Subject used for monthly inventory-inflow reports",
            "default": "DiCor Monthly Stock Entry Report",
            "validator": str,
        },
    }

    @property
    def control_panel_url(self) -> str:
        """Return the plugin URL as a root-relative browser address."""

        return f"/{self.base_url.lstrip('/')}"

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

    def email_recipient(self) -> str:
        """Return the configured automatic report recipient."""

        return str(self._setting("EMAIL_RECIPIENT", "") or "").strip()

    def email_subject(self) -> str:
        """Return the configured report email subject."""

        value = str(
            self._setting("EMAIL_SUBJECT", DEFAULT_EMAIL_SUBJECT) or ""
        ).strip()
        return value or DEFAULT_EMAIL_SUBJECT

    def monthly_stock_report_enabled(self) -> bool:
        value = self._setting("MONTHLY_STOCK_REPORT_ENABLED", False)
        if isinstance(value, str):
            return value.strip().casefold() in {"1", "true", "yes", "on"}
        return bool(value)

    def stock_entry_email_subject(self) -> str:
        return str(
            self._setting("STOCK_ENTRY_EMAIL_SUBJECT", "DiCor Monthly Stock Entry Report")
            or "DiCor Monthly Stock Entry Report"
        ).strip()

    def get_scheduled_tasks(self) -> dict[str, dict[str, object]]:
        """Dynamically register one repeating report task when enabled."""

        if not self.email_recipient():
            return {}

        tasks = {}
        if self.automation_enabled():
            tasks["replenishment_report"] = {
                "func": "run_scheduled_report",
                "schedule": "I",
                "minutes": self.automation_interval_days() * 24 * 60,
                "repeats": -1,
            }
        if self.monthly_stock_report_enabled():
            tasks["monthly_stock_entry_report"] = {
                "func": "run_monthly_stock_entry_report",
                "schedule": "M",
                "repeats": -1,
            }
        return tasks

    def refresh_automation_schedule(self) -> None:
        """Apply an automation setting change without requiring a plugin reload."""

        replenishment_name = self.get_task_name("replenishment_report")
        monthly_name = self.get_task_name("monthly_stock_entry_report")

        from django_q.models import Schedule

        if self.get_scheduled_tasks():
            from datetime import timedelta

            from django.utils import timezone

            self.register_tasks()
            if self.automation_enabled():
                Schedule.objects.filter(name=replenishment_name).update(
                    next_run=timezone.now()
                    + timedelta(days=self.automation_interval_days())
                )
            if self.monthly_stock_report_enabled():
                now = timezone.localtime()
                first_next_month = (now.replace(day=28) + timedelta(days=4)).replace(
                    day=1, hour=7, minute=0, second=0, microsecond=0
                )
                Schedule.objects.filter(name=monthly_name).update(next_run=first_next_month)

        if not self.automation_enabled():
            Schedule.objects.filter(name=replenishment_name).delete()
        if not self.monthly_stock_report_enabled():
            Schedule.objects.filter(name=monthly_name).delete()

    def send_configured_report_email(self):
        """Generate and email a report using the saved delivery settings."""

        return generate_and_email_replenishment_report(
            self.email_recipient(),
            self.email_subject(),
        )

    def run_scheduled_report(self) -> None:
        """Generate and email the configured automatic replenishment report."""

        if self.automation_enabled() and self.email_recipient():
            self.send_configured_report_email()

    def run_monthly_stock_entry_report(self, force: bool = False):
        """Generate, email, and retain one idempotent prior-month report."""

        if (not force and not self.monthly_stock_report_enabled()) or not self.email_recipient():
            return None

        from django.utils import timezone

        from .automation import generate_stock_entry_report
        from .models import StockEntryReportRun

        start, end = previous_month_window(timezone.localdate())
        run, _ = StockEntryReportRun.objects.get_or_create(
            period_key=start.strftime("%Y-%m"),
            defaults={
                "kind": StockEntryReportRun.Kind.MONTHLY,
                "period_start": start,
                "period_end": end,
                "recipient": self.email_recipient(),
            },
        )
        if run.status in {
            StockEntryReportRun.Status.EMAILED,
            StockEntryReportRun.Status.ACKNOWLEDGED,
        }:
            return run

        try:
            output = generate_stock_entry_report(start, end)
            run.output_id = output.pk
            run.status = StockEntryReportRun.Status.GENERATED
            run.error = ""
            run.save(update_fields=["output_id", "status", "error"])
            send_stock_entry_report_email(
                output,
                self.email_recipient(),
                start,
                end,
                self.stock_entry_email_subject(),
            )
            run.status = StockEntryReportRun.Status.EMAILED
            run.sent_at = timezone.now()
            run.save(update_fields=["status", "sent_at"])
        except Exception as error:
            run.status = StockEntryReportRun.Status.FAILED
            run.error = str(error)
            run.save(update_fields=["status", "error"])
            raise

        return run

    def setup_urls(self):
        """Expose the simple Inventory Manager control panel."""

        from django.urls import path
        from InvenTree.permissions import auth_exempt

        def authenticated_mobile_dashboard(request, *args, **kwargs):
            """Apply DRF token authentication without importing it at startup."""

            from rest_framework.decorators import api_view, permission_classes
            from rest_framework.permissions import IsAuthenticated

            @api_view(["GET"])
            @permission_classes([IsAuthenticated])
            def view(api_request):
                return self.mobile_dashboard_view(api_request)

            return view(request, *args, **kwargs)

        return [
            path(
                "reporting.js",
                auth_exempt(self.reporting_script_view),
                name="reporting-script",
            ),
            path(
                "mobile/dashboard/",
                authenticated_mobile_dashboard,
                name="mobile-dashboard",
            ),
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

    def reporting_script_view(self, request):
        """Serve the Reporting UI helper without relying on collectstatic."""

        from .views import reporting_script

        return reporting_script(request)

    def mobile_dashboard_view(self, request):
        """Return a native, token-authenticated replenishment summary."""

        del request

        from rest_framework.response import Response

        context = build_report_context(policy=self.get_inventory_policy())
        summary = context["inventory_summary"]
        rows = context["replenishment_items"][:8]

        overview = [
            {"label": "Critical", "value": str(summary["critical_count"])},
            {"label": "Reorder", "value": str(summary["reorder_count"])},
            {"label": "Low buffer", "value": str(summary["low_buffer_count"])},
            {"label": "Parts evaluated", "value": str(summary["parts_evaluated"])},
        ]
        attention = [
            {
                "label": str(row["part_name"]),
                "value": str(row["status"]).replace("_", " ").title(),
                "detail": (
                    f"Available {row['available']} | "
                    f"Suggested order {row['suggested_order']}"
                ),
                "action": {
                    "type": "model_detail",
                    "model": "part",
                    "pk": row["part_id"],
                },
            }
            for row in rows
        ]

        sections = [{"title": "Stock overview", "items": overview}]
        if attention:
            sections.append({"title": "Needs attention", "items": attention})

        try:
            from .models import StockEntryReportRun

            latest = StockEntryReportRun.objects.first()
        except Exception:
            latest = None
        if latest:
            sections.append(
                {
                    "title": "Stock-entry accounting",
                    "items": [
                        {
                            "label": f"{latest.period_start} to {latest.period_end}",
                            "value": latest.get_status_display(),
                            "detail": latest.accounting_reference
                            or "Open the web Reporting page to record acknowledgement",
                        }
                    ],
                }
            )

        return Response(
            {
                "schema_version": self.MOBILE_APP_SCHEMA_VERSION,
                "title": "Reporting",
                "description": "Stock health and replenishment planning",
                "sections": sections,
            }
        )

    def get_ui_navigation_items(self, request, context, **kwargs):
        """Avoid InvenTree's SPA-only navigation tabs for this server page."""

        del request, context, kwargs
        return []

    def get_ui_spotlight_actions(self, request, context, **kwargs):
        """Provide a working Reporting command in InvenTree search."""

        del request, context, kwargs
        return [
            {
                "key": "open-reporting",
                "title": "Reporting",
                "description": "Open stock reports and replenishment settings",
                "icon": "ti:report-analytics",
                "source": f"{self.control_panel_url}reporting.js:openReporting?v={self.VERSION}",
            }
        ]

    def get_ui_dashboard_items(self, request, context, **kwargs):
        """Offer an optional one-click Reporting dashboard card."""

        del request, context, kwargs
        return [
            {
                "key": "reporting-shortcut",
                "title": "Reporting",
                "description": "Stock reports and replenishment settings",
                "source": (
                    f"{self.control_panel_url}reporting.js:renderReportingShortcut?v={self.VERSION}"
                ),
                "options": {
                    "width": 3,
                    "height": 2,
                    **self.mobile_app_options(
                        "summary-list-v1",
                        "/plugin/inventory-manager/mobile/dashboard/",
                    ),
                },
            }
        ]

    def add_report_context(
        self, report_instance, model_instance, request, context
    ) -> None:
        """Inject replenishment rows and summary totals at report render time."""

        del model_instance

        if is_replenishment_report_template(report_instance):
            context.update(build_report_context(policy=self.get_inventory_policy()))
        elif is_stock_entry_report_template(report_instance):
            start = getattr(request, "inventory_manager_period_start", None)
            end = getattr(request, "inventory_manager_period_end", None)
            if start is None or end is None:
                start, end = previous_month_window()
            context.update(build_stock_entry_context(start, end))
