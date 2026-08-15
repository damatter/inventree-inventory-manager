"""Durable report-delivery and accounting acknowledgement records."""

from django.conf import settings
from django.db import models


class StockEntryReportRun(models.Model):
    """Track one generated stock-entry report through accounting acknowledgement."""

    class Kind(models.TextChoices):
        MANUAL = "manual", "Manual date range"
        MONTHLY = "monthly", "Monthly delivery"

    class Status(models.TextChoices):
        GENERATED = "generated", "Generated"
        EMAILED = "emailed", "Emailed"
        ACKNOWLEDGED = "acknowledged", "Recorded in accounting"
        FAILED = "failed", "Failed"

    class Meta:
        ordering = ["-period_end", "-created"]
        verbose_name = "Stock Entry Report Run"
        verbose_name_plural = "Stock Entry Report Runs"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    period_key = models.CharField(max_length=7, unique=True, null=True, blank=True)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.GENERATED,
    )
    output_id = models.PositiveIntegerField(null=True, blank=True)
    recipient = models.EmailField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    accounting_reference = models.CharField(max_length=120, blank=True, default="")
    acknowledgement_notes = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Stock entries {self.period_start} to {self.period_end}"
