"""Server-rendered Inventory Manager control panel."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from .automation import (
    PLUGIN_SLUG,
    ReportSetupError,
    generate_stock_entry_report,
    queue_replenishment_report,
)
from .emailing import (
    DEFAULT_EMAIL_SUBJECT,
    ReportEmailError,
    email_delivery_available,
    normalize_recipient,
    queue_replenishment_report_email,
)


def _validate_settings(post_data) -> tuple[dict[str, object], list[str]]:
    """Validate control-panel values and return normalized settings."""

    errors = []

    try:
        default_minimum = int(post_data.get("default_minimum_stock", "2"))
        if default_minimum < 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Default minimum stock must be a whole number of at least 1.")
        default_minimum = 2

    try:
        low_buffer = Decimal(post_data.get("low_buffer_multiplier", "2"))
        if low_buffer < Decimal("1"):
            raise ValueError
    except (InvalidOperation, TypeError, ValueError):
        errors.append("Low-buffer multiplier must be a number of at least 1.")
        low_buffer = Decimal("2")

    try:
        interval = int(post_data.get("automation_interval_days", "7"))
        if not 1 <= interval <= 365:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Automatic report interval must be between 1 and 365 days.")
        interval = 7

    automation_enabled = post_data.get("automation_enabled") == "on"
    monthly_stock_report_enabled = post_data.get("monthly_stock_report_enabled") == "on"
    email_recipient = str(post_data.get("email_recipient", "") or "").strip()
    email_subject = (
        str(post_data.get("email_subject", "") or "").strip()
        or DEFAULT_EMAIL_SUBJECT
    )
    stock_entry_email_subject = (
        str(post_data.get("stock_entry_email_subject", "") or "").strip()
        or "DiCor Monthly Stock Entry Report"
    )

    if email_recipient:
        try:
            email_recipient = normalize_recipient(email_recipient)
        except ReportEmailError as error:
            errors.append(str(error))
    elif automation_enabled or monthly_stock_report_enabled:
        errors.append(
            "Enter a recipient email address before enabling automatic delivery."
        )

    return (
        {
            "DEFAULT_MINIMUM_STOCK": default_minimum,
            "LOW_BUFFER_MULTIPLIER": float(low_buffer),
            "EMAIL_RECIPIENT": email_recipient,
            "EMAIL_SUBJECT": email_subject,
            "AUTOMATION_ENABLED": automation_enabled,
            "AUTOMATION_INTERVAL_DAYS": interval,
            "MONTHLY_STOCK_REPORT_ENABLED": monthly_stock_report_enabled,
            "STOCK_ENTRY_EMAIL_SUBJECT": stock_entry_email_subject,
        },
        errors,
    )


def _stock_report_window(post_data) -> tuple[date | None, date | None, str]:
    """Validate an inclusive manual stock-entry report date window."""

    try:
        start = date.fromisoformat(str(post_data.get("period_start", "")))
        end = date.fromisoformat(str(post_data.get("period_end", "")))
    except ValueError:
        return None, None, "Enter a valid start and end date."
    if start > end:
        return None, None, "The start date must not be after the end date."
    if end - start > timedelta(days=366):
        return None, None, "Choose a reporting window of one year or less."
    return start, end, ""


def _schedule_integration_enabled() -> bool:
    """Return whether InvenTree allows plugins to register scheduled tasks."""

    try:
        from common.models import InvenTreeSetting

        value = InvenTreeSetting.get_setting("ENABLE_PLUGINS_SCHEDULE")
    except Exception:
        return False

    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def _rooted_url(url: str) -> str:
    """Make a local browser URL root-relative while preserving absolute URLs."""

    if not url or url.startswith(("/", "http://", "https://")):
        return url
    return f"/{url}"


def _output_url(output) -> str:
    """Return a generated file URL without failing for incomplete jobs."""

    try:
        url = output.output.url if output.output else ""
    except (AttributeError, ValueError):
        return ""
    return _rooted_url(url)


def _output_error(output) -> str:
    """Return a readable error from an InvenTree DataOutput."""

    errors = getattr(output, "errors", None)
    if not errors:
        return ""
    if isinstance(errors, dict):
        return str(errors.get("error") or errors.get("detail") or errors)
    return str(errors)


def reporting_script(request):
    """Serve the small Reporting UI module directly from the plugin package."""

    from pathlib import Path

    from django.http import HttpResponse

    del request
    script_path = (
        Path(__file__).parent
        / "static"
        / "plugins"
        / "inventory-manager"
        / "reporting.js"
    )
    response = HttpResponse(
        script_path.read_text(encoding="utf-8"),
        content_type="text/javascript; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache"
    return response


def control_panel(request, plugin):
    """Handle settings updates and manual report generation."""

    from django.contrib import messages
    from django.contrib.auth.decorators import login_required
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import redirect, render

    @login_required
    def authenticated_view(request):
        if request.method == "POST":
            action = request.POST.get("action")

            if action == "save-settings":
                if not request.user.is_staff:
                    raise PermissionDenied(
                        "Only an InvenTree administrator can change report settings."
                    )

                values, errors = _validate_settings(request.POST)
                if errors:
                    for error in errors:
                        messages.error(request, error)
                else:
                    for key, value in values.items():
                        plugin.set_setting(key, value, user=request.user)
                    plugin.refresh_automation_schedule()
                    messages.success(request, "Inventory Manager settings saved.")
                    return redirect(plugin.control_panel_url)

            elif action == "send-report-email":
                if not request.user.is_staff:
                    raise PermissionDenied(
                        "Only an InvenTree administrator can send report emails."
                    )

                recipient = plugin.email_recipient()
                try:
                    queue_replenishment_report_email(
                        plugin.SLUG,
                        recipient,
                    )
                except ReportEmailError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(
                        request,
                        f"Report email queued for {recipient}.",
                    )
                    return redirect(plugin.control_panel_url)

            elif action == "send-stock-entry-email":
                if not request.user.is_staff:
                    raise PermissionDenied(
                        "Only an InvenTree administrator can send report emails."
                    )
                try:
                    run = plugin.run_monthly_stock_entry_report(force=True)
                except Exception as error:
                    messages.error(request, f"Stock-entry report delivery failed: {error}")
                else:
                    if run is None:
                        messages.error(request, "Enter and save a report recipient first.")
                    else:
                        messages.success(
                            request,
                            (
                                f"Stock-entry report for {run.period_start:%B %Y} is "
                                f"{run.get_status_display().lower()}."
                            ),
                        )
                        return redirect(plugin.control_panel_url)

            elif action == "generate-report":
                try:
                    output = queue_replenishment_report(request)
                except ReportSetupError as error:
                    messages.error(request, str(error))
                else:
                    status_url = f"{plugin.control_panel_url}report/{output.pk}/"
                    return redirect(status_url)

            elif action == "generate-stock-entry-report":
                start, end, error = _stock_report_window(request.POST)
                if error:
                    messages.error(request, error)
                else:
                    try:
                        output = generate_stock_entry_report(start, end, request=request)
                    except ReportSetupError as report_error:
                        messages.error(request, str(report_error))
                    else:
                        from .models import StockEntryReportRun

                        StockEntryReportRun.objects.create(
                            kind=StockEntryReportRun.Kind.MANUAL,
                            period_start=start,
                            period_end=end,
                            status=StockEntryReportRun.Status.GENERATED,
                            output_id=output.pk,
                            generated_by=request.user,
                        )
                        return redirect(
                            f"{plugin.control_panel_url}report/{output.pk}/"
                        )

            elif action == "acknowledge-stock-report":
                from django.shortcuts import get_object_or_404
                from django.utils import timezone

                from .models import StockEntryReportRun

                run = get_object_or_404(
                    StockEntryReportRun,
                    pk=request.POST.get("report_run_id"),
                )
                run.status = StockEntryReportRun.Status.ACKNOWLEDGED
                run.acknowledged_at = timezone.now()
                run.acknowledged_by = request.user
                run.accounting_reference = str(
                    request.POST.get("accounting_reference", "") or ""
                ).strip()[:120]
                run.acknowledgement_notes = str(
                    request.POST.get("acknowledgement_notes", "") or ""
                ).strip()
                run.save(
                    update_fields=[
                        "status",
                        "acknowledged_at",
                        "acknowledged_by",
                        "accounting_reference",
                        "acknowledgement_notes",
                    ]
                )
                messages.success(request, "The stock-entry report was marked as recorded.")
                return redirect(plugin.control_panel_url)

        from common.models import DataOutput

        latest_outputs = []
        for output in DataOutput.objects.filter(plugin=PLUGIN_SLUG).order_by("-pk")[:5]:
            latest_outputs.append(
                {
                    "pk": output.pk,
                    "created": output.created,
                    "complete": output.complete,
                    "url": _output_url(output),
                }
            )

        from django.utils import timezone

        from .models import StockEntryReportRun
        from .stock_entries import previous_month_window

        output_ids = [
            output_id
            for output_id in StockEntryReportRun.objects.exclude(output_id=None).values_list(
                "output_id", flat=True
            )[:20]
        ]
        output_urls = {
            output.pk: _output_url(output)
            for output in DataOutput.objects.filter(pk__in=output_ids)
        }
        stock_report_runs = [
            {
                "pk": run.pk,
                "kind": run.get_kind_display(),
                "period_start": run.period_start,
                "period_end": run.period_end,
                "status": run.get_status_display(),
                "status_code": run.status,
                "recipient": run.recipient,
                "created": run.created,
                "sent_at": run.sent_at,
                "url": output_urls.get(run.output_id, ""),
                "error": run.error,
                "acknowledged_at": run.acknowledged_at,
                "acknowledged_by": str(run.acknowledged_by or ""),
                "accounting_reference": run.accounting_reference,
                "acknowledgement_notes": run.acknowledgement_notes,
            }
            for run in StockEntryReportRun.objects.select_related("acknowledged_by")[:12]
        ]
        default_start, default_end = previous_month_window(timezone.localdate())

        context = {
            "plugin_title": plugin.TITLE,
            "plugin_version": plugin.VERSION,
            "is_staff": request.user.is_staff,
            "default_minimum_stock": plugin._setting("DEFAULT_MINIMUM_STOCK", 2),
            "low_buffer_multiplier": plugin._setting("LOW_BUFFER_MULTIPLIER", 2),
            "automation_enabled": plugin.automation_enabled(),
            "automation_interval_days": plugin.automation_interval_days(),
            "email_recipient": plugin.email_recipient(),
            "email_subject": plugin.email_subject(),
            "monthly_stock_report_enabled": plugin.monthly_stock_report_enabled(),
            "stock_entry_email_subject": plugin.stock_entry_email_subject(),
            "email_configured": email_delivery_available(),
            "schedule_integration_enabled": _schedule_integration_enabled(),
            "latest_outputs": latest_outputs,
            "stock_report_runs": stock_report_runs,
            "stock_report_default_start": default_start.isoformat(),
            "stock_report_default_end": default_end.isoformat(),
        }
        return render(request, "inventory_manager/control_panel.html", context)

    return authenticated_view(request)


def report_status(request, plugin, output_id: int):
    """Wait for a report job, then download it and return to Reporting."""

    from common.models import DataOutput
    from django.contrib import messages
    from django.contrib.auth.decorators import login_required
    from django.shortcuts import get_object_or_404, redirect, render

    @login_required
    def authenticated_view(request):
        outputs = DataOutput.objects.filter(pk=output_id, plugin=PLUGIN_SLUG)
        if not request.user.is_staff:
            outputs = outputs.filter(user=request.user)

        output = get_object_or_404(outputs)

        if error := _output_error(output):
            messages.error(request, f"Report generation failed: {error}")
            return redirect(plugin.control_panel_url)

        if output.complete:
            if url := _output_url(output):
                return render(
                    request,
                    "inventory_manager/report_complete.html",
                    {
                        "download_url": url,
                        "control_panel_url": plugin.control_panel_url,
                    },
                )
            messages.error(request, "The report completed without a downloadable file.")
            return redirect(plugin.control_panel_url)

        return render(
            request,
            "inventory_manager/report_status.html",
            {
                "plugin_title": plugin.TITLE,
                "output_id": output.pk,
                "progress": output.progress,
                "total": output.total,
                "control_panel_url": plugin.control_panel_url,
            },
        )

    return authenticated_view(request)
