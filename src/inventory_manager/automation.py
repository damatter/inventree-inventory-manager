"""Report generation helpers shared by manual and scheduled actions."""

from __future__ import annotations

from typing import Any

from .reports import REPORT_DESCRIPTION_MARKER, REPORT_NAME

PLUGIN_SLUG = "inventory-manager"


class ReportSetupError(RuntimeError):
    """Raised when the replenishment report cannot be generated yet."""


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
