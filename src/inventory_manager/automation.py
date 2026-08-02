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


def queue_replenishment_report(user: Any | None = None):
    """Create a DataOutput and queue normal InvenTree PDF generation."""

    from common.models import DataOutput
    from InvenTree.tasks import offload_task
    import report.tasks

    template = find_replenishment_template()
    anchor = report_anchor(template)
    authenticated_user = user if getattr(user, "is_authenticated", False) else None

    if authenticated_user:
        from django.core.exceptions import PermissionDenied
        from users.permissions import check_user_permission

        if not check_user_permission(authenticated_user, template.get_model(), "view"):
            raise PermissionDenied(
                "You do not have permission to view the report template model."
            )

    output = DataOutput.objects.create(
        user=authenticated_user,
        total=1,
        progress=0,
        complete=False,
        output_type=DataOutput.DataOutputTypes.REPORT,
        template_name=template.name,
        plugin=PLUGIN_SLUG,
        output=None,
    )

    offload_task(
        report.tasks.print_reports,
        template.pk,
        [anchor.pk],
        output.pk,
        authenticated_user.pk if authenticated_user else None,
    )

    output.refresh_from_db()
    return output
