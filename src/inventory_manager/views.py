"""Server-rendered Inventory Manager control panel."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .automation import PLUGIN_SLUG, ReportSetupError, queue_replenishment_report


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

    return (
        {
            "DEFAULT_MINIMUM_STOCK": default_minimum,
            "LOW_BUFFER_MULTIPLIER": float(low_buffer),
            "AUTOMATION_ENABLED": post_data.get("automation_enabled") == "on",
            "AUTOMATION_INTERVAL_DAYS": interval,
        },
        errors,
    )


def _output_url(output) -> str:
    """Return a generated file URL without failing for incomplete jobs."""

    try:
        return output.output.url if output.output else ""
    except (AttributeError, ValueError):
        return ""


def control_panel(request, plugin):
    """Handle settings updates and manual report generation."""

    from django.contrib import messages
    from django.contrib.auth.decorators import login_required
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import redirect, render
    from django.urls import reverse

    @login_required
    def authenticated_view(request):
        queued_output = None

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
                    return redirect(plugin.base_url)

            elif action == "generate-report":
                try:
                    queued_output = queue_replenishment_report(request.user)
                except ReportSetupError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(
                        request,
                        "The report is being generated. It will open automatically.",
                    )

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

        context = {
            "plugin_title": plugin.TITLE,
            "plugin_version": plugin.VERSION,
            "is_staff": request.user.is_staff,
            "default_minimum_stock": plugin._setting("DEFAULT_MINIMUM_STOCK", 2),
            "low_buffer_multiplier": plugin._setting("LOW_BUFFER_MULTIPLIER", 2),
            "automation_enabled": plugin.automation_enabled(),
            "automation_interval_days": plugin.automation_interval_days(),
            "latest_outputs": latest_outputs,
            "queued_output_id": getattr(queued_output, "pk", None),
            "queued_output_api": (
                reverse("api-data-output-detail", kwargs={"pk": queued_output.pk})
                if queued_output
                else ""
            ),
        }
        return render(request, "inventory_manager/control_panel.html", context)

    return authenticated_view(request)
