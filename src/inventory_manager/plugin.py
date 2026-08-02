"""InvenTree plugin entry point."""

from plugin import InvenTreePlugin
from plugin.mixins import ReportMixin

from .reports import build_report_context, is_replenishment_report_template


class InventoryManagerPlugin(ReportMixin, InvenTreePlugin):
    """Add Inventory Manager calculations to opted-in report templates."""

    NAME = "InventoryManager"
    SLUG = "inventory-manager"
    TITLE = "Inventory Manager"
    DESCRIPTION = "Stock-level reporting and replenishment planning"
    VERSION = "0.1.0"
    AUTHOR = "Matt Dick"
    MIN_VERSION = "1.0.0"
    LICENSE = "MIT"

    def add_report_context(
        self, report_instance, model_instance, request, context
    ) -> None:
        """Inject replenishment rows and summary totals at report render time."""

        del model_instance, request

        if not is_replenishment_report_template(report_instance):
            return

        context.update(build_report_context())

