"""Create durable monthly stock-entry report records."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="StockEntryReportRun",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("manual", "Manual date range"),
                            ("monthly", "Monthly delivery"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "period_key",
                    models.CharField(blank=True, max_length=7, null=True, unique=True),
                ),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("generated", "Generated"),
                            ("emailed", "Emailed"),
                            ("acknowledged", "Recorded in accounting"),
                            ("failed", "Failed"),
                        ],
                        default="generated",
                        max_length=20,
                    ),
                ),
                ("output_id", models.PositiveIntegerField(blank=True, null=True)),
                ("recipient", models.EmailField(blank=True, default="", max_length=254)),
                ("error", models.TextField(blank=True, default="")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                (
                    "accounting_reference",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                ("acknowledgement_notes", models.TextField(blank=True, default="")),
                (
                    "acknowledged_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "generated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Stock Entry Report Run",
                "verbose_name_plural": "Stock Entry Report Runs",
                "ordering": ["-period_end", "-created"],
            },
        )
    ]
