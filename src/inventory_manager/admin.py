"""Reload-safe admin registration for report history."""

from django.contrib import admin

from .models import StockEntryReportRun


class StockEntryReportRunAdmin(admin.ModelAdmin):
    list_display = (
        "period_start",
        "period_end",
        "kind",
        "status",
        "recipient",
        "acknowledged_at",
    )
    list_filter = ("kind", "status")
    search_fields = ("recipient", "accounting_reference", "acknowledgement_notes")


if not admin.site.is_registered(StockEntryReportRun):
    admin.site.register(StockEntryReportRun, StockEntryReportRunAdmin)
