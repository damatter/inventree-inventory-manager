"""Allow interval stock reports and multiple email recipients."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory_manager", "0001_stock_entry_report_run")]

    operations = [
        migrations.AlterField(
            model_name="stockentryreportrun",
            name="kind",
            field=models.CharField(
                choices=[
                    ("manual", "Manual date range"),
                    ("monthly", "Monthly delivery"),
                    ("scheduled", "Scheduled delivery"),
                ],
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="stockentryreportrun",
            name="period_key",
            field=models.CharField(
                blank=True,
                max_length=32,
                null=True,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="stockentryreportrun",
            name="recipient",
            field=models.CharField(blank=True, default="", max_length=1000),
        ),
    ]
