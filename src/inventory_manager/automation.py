"""Report generation helpers shared by manual and scheduled actions."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from .reports import (
    REPORT_DESCRIPTION_MARKER,
    REPORT_NAME,
    STOCK_ENTRY_DESCRIPTION_MARKER,
    STOCK_ENTRY_REPORT_NAME,
)

PLUGIN_SLUG = "inventory-manager"
logger = logging.getLogger(__name__)


class ReportSetupError(RuntimeError):
    """Raised when the replenishment report cannot be generated yet."""


def _background_report_request(user=None):
    """Return a real request rooted at InvenTree's configured public host."""

    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory
    from InvenTree.helpers_model import get_base_url

    configured_url = str(get_base_url() or "").strip()
    if not configured_url:
        configured_url = "http://localhost"
    elif "://" not in configured_url:
        # Django Sites commonly stores only a domain. InvenTree deployments are
        # HTTPS by default, while an explicit http:// URL remains respected.
        configured_url = f"https://{configured_url.lstrip('/')}"

    parsed_url = urlsplit(configured_url)
    host = parsed_url.netloc or "localhost"
    secure = parsed_url.scheme.casefold() == "https"

    request = RequestFactory().get(
        "/plugin/inventory-manager/",
        secure=secure,
        HTTP_HOST=host,
    )
    request.user = user if user is not None else AnonymousUser()
    return request


def find_replenishment_template():
    """Return the enabled report template configured for this plugin."""

    from report.models import ReportTemplate

    templates = ReportTemplate.objects.filter(enabled=True)
    template = templates.filter(name__iexact=REPORT_NAME).first()

    if template is None:
        template = templates.filter(
            description__icontains=REPORT_DESCRIPTION_MARKER
        ).first()

    if template is None:
        raise ReportSetupError(
            "No enabled Inventory Replenishment Report template was found."
        )

    return template


def find_stock_entry_template():
    """Return the enabled stock-entry report template configured for this plugin."""

    from report.models import ReportTemplate

    templates = ReportTemplate.objects.filter(enabled=True)
    template = templates.filter(name__iexact=STOCK_ENTRY_REPORT_NAME).first()
    if template is None:
        template = templates.filter(
            description__icontains=STOCK_ENTRY_DESCRIPTION_MARKER
        ).first()
    if template is None:
        raise ReportSetupError("No enabled Monthly Stock Entry Report template was found.")
    return template


def report_anchor(template):
    """Return one model object used to anchor the inventory-wide report."""

    model = template.get_model()
    if model is None:
        raise ReportSetupError("The report template does not have a valid model type.")

    queryset = model.objects.all()
    filters = template.get_filters()
    if filters:
        queryset = queryset.filter(**filters)

    if model.__name__ == "Part":
        queryset = queryset.filter(active=True, virtual=False)

    anchor = queryset.order_by("pk").first()
    if anchor is None:
        raise ReportSetupError("No matching part is available to generate the report.")

    return anchor


def _check_report_permission(user: Any | None, template) -> None:
    """Apply the same model-view permission check as InvenTree report printing."""

    if not user or not getattr(user, "is_authenticated", False):
        return

    from django.core.exceptions import PermissionDenied
    from users.permissions import check_user_permission

    if not check_user_permission(user, template.get_model(), "view"):
        raise PermissionDenied(
            "You do not have permission to view the report template model."
        )


def _tag_output(output):
    """Mark a generated output as belonging to Inventory Manager."""

    output.plugin = PLUGIN_SLUG
    output.save(update_fields=["plugin"])
    return output


def queue_replenishment_report(request):
    """Queue a PDF through the native print path of the installed InvenTree."""

    from common.models import DataOutput
    from report.api import ReportPrint

    template = find_replenishment_template()
    anchor = report_anchor(template)
    _check_report_permission(getattr(request, "user", None), template)

    # Calling the installed ReportPrint implementation is important here. The
    # background task signature changed between supported InvenTree releases.
    response = ReportPrint().print(template, [anchor], request)
    output_id = response.data.get("pk")

    if not output_id:
        raise ReportSetupError("InvenTree did not return a report job identifier.")

    output = DataOutput.objects.get(pk=output_id)
    return _tag_output(output)


def generate_replenishment_report():
    """Generate a PDF synchronously from an existing scheduled worker task."""

    template = find_replenishment_template()
    anchor = report_anchor(template)
    output = template.print([anchor])

    if output is None:
        raise ReportSetupError("The scheduled report did not produce an output.")

    return _tag_output(output)


def generate_stock_entry_report(start, end, request=None, context=None):
    """Synchronously generate a stock-entry PDF for an explicit date window."""

    template = find_stock_entry_template()
    anchor = report_anchor(template)
    _check_report_permission(getattr(request, "user", None), template)

    report_request = request or _background_report_request()
    report_request.inventory_manager_period_start = start
    report_request.inventory_manager_period_end = end
    if context is None:
        from .stock_entries import build_stock_entry_context

        context = build_stock_entry_context(start, end)
    report_request.inventory_manager_stock_entry_context = context

    output = template.print([anchor], request=report_request)
    if output is None:
        raise ReportSetupError("The stock-entry report did not produce an output.")
    output.inventory_manager_stock_entry_context = context
    return _tag_output(output)


def queue_stock_entry_report(start, end, request, plugin_slug=PLUGIN_SLUG):
    """Create a pollable output and render the selected window on the worker."""

    from common.models import DataOutput
    from InvenTree.tasks import offload_task

    template = find_stock_entry_template()
    anchor = report_anchor(template)
    user = getattr(request, "user", None)
    _check_report_permission(user, template)

    output = DataOutput.objects.create(
        user=user if user and getattr(user, "is_authenticated", False) else None,
        total=1,
        progress=0,
        complete=False,
        output_type=DataOutput.DataOutputTypes.REPORT,
        template_name=STOCK_ENTRY_REPORT_NAME,
        plugin=PLUGIN_SLUG,
        output=None,
    )
    task = offload_task(
        "plugin.registry.call_plugin_function",
        str(plugin_slug or PLUGIN_SLUG),
        "render_stock_entry_report_job",
        output.pk,
        template.pk,
        anchor.pk,
        start.isoformat(),
        end.isoformat(),
        getattr(user, "pk", None),
        group="inventory-manager-stock-entry-report",
    )
    if not task:
        message = "InvenTree could not queue the stock-entry report."
        output.mark_failure(error=message)
        raise ReportSetupError(message)

    output.refresh_from_db()
    return output


def render_stock_entry_report_job(
    output_id,
    template_id,
    anchor_id,
    start_value,
    end_value,
    user_id=None,
):
    """Render one queued stock-entry report while preserving its date context."""

    from common.models import DataOutput
    from django.contrib.auth import get_user_model
    from report.models import ReportTemplate

    output = DataOutput.objects.get(pk=output_id)
    try:
        template = ReportTemplate.objects.get(pk=template_id)
        anchor = template.get_model().objects.get(pk=anchor_id)
        user = (
            get_user_model().objects.filter(pk=user_id).first()
            if user_id is not None
            else None
        )
        start = date.fromisoformat(str(start_value))
        end = date.fromisoformat(str(end_value))

        from .stock_entries import build_stock_entry_context

        context = build_stock_entry_context(start, end)
        report_request = _background_report_request(user)
        report_request.inventory_manager_period_start = start
        report_request.inventory_manager_period_end = end
        report_request.inventory_manager_stock_entry_context = context
        result = template.print([anchor], request=report_request, output=output)
        result = _tag_output(result)

        try:
            from .models import StockEntryReportRun

            StockEntryReportRun.objects.create(
                kind=StockEntryReportRun.Kind.MANUAL,
                period_start=start,
                period_end=end,
                status=StockEntryReportRun.Status.GENERATED,
                output_id=output.pk,
                generated_by=user,
            )
        except Exception:
            logger.exception("Could not add stock-entry PDF to accounting register")
        return result
    except Exception as error:
        output.mark_failure(error=str(error))
        try:
            from .models import StockEntryReportRun

            StockEntryReportRun.objects.create(
                kind=StockEntryReportRun.Kind.MANUAL,
                period_start=date.fromisoformat(str(start_value)),
                period_end=date.fromisoformat(str(end_value)),
                status=StockEntryReportRun.Status.FAILED,
                output_id=output.pk,
                generated_by=(user if "user" in locals() else None),
                error=str(error),
            )
        except Exception:
            logger.exception("Could not record failed stock-entry report")
        raise
