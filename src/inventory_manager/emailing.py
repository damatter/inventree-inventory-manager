"""Email delivery for generated replenishment reports."""

from __future__ import annotations

import re
from contextlib import suppress
from datetime import date
from typing import Any

from .automation import generate_replenishment_report

DEFAULT_EMAIL_SUBJECT = "DiCor Inventory Replenishment Report"
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ReportEmailError(RuntimeError):
    """Raised when a replenishment report email cannot be delivered."""


def normalize_recipient(value: object) -> str:
    """Return one validated recipient email address."""

    recipient = str(value or "").strip()
    if not recipient:
        raise ReportEmailError("Enter a recipient email address first.")
    if not _EMAIL_PATTERN.fullmatch(recipient):
        raise ReportEmailError("Enter a valid recipient email address.")
    return recipient


def email_delivery_available() -> bool:
    """Return whether InvenTree has an outgoing email backend configured."""

    try:
        from InvenTree.helpers_email import is_email_configured

        return bool(is_email_configured())
    except Exception:
        return False


def _read_report_pdf(output: Any) -> bytes:
    """Read a generated DataOutput through its configured storage backend."""

    if not getattr(output, "complete", False):
        raise ReportEmailError("The generated report did not finish successfully.")
    if getattr(output, "errors", None):
        raise ReportEmailError("The generated report contains an error.")

    report_file = getattr(output, "output", None)
    if not report_file:
        raise ReportEmailError("The generated report does not contain a PDF file.")

    try:
        report_file.open("rb")
        content = report_file.read()
    except Exception as error:
        raise ReportEmailError("The generated PDF could not be read.") from error
    finally:
        with suppress(Exception):
            report_file.close()

    if not content:
        raise ReportEmailError("The generated PDF file is empty.")
    return content


def send_replenishment_report_email(
    output: Any,
    recipient: object,
    subject: object = DEFAULT_EMAIL_SUBJECT,
) -> int:
    """Email a generated DataOutput PDF through InvenTree's mail backend."""

    address = normalize_recipient(recipient)
    email_subject = str(subject or "").strip() or DEFAULT_EMAIL_SUBJECT

    if not email_delivery_available():
        raise ReportEmailError(
            "InvenTree's outgoing email server is not configured."
        )

    from django.conf import settings
    from django.core.mail import EmailMessage

    sender = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if not sender:
        raise ReportEmailError("InvenTree does not have a default sender address.")

    attachment = _read_report_pdf(output)
    filename = f"inventory-replenishment-{date.today().isoformat()}.pdf"
    body = (
        "Attached is the current Inventory Replenishment Report.\n\n"
        "INTERNAL - DiCor Engineering"
    )
    message = EmailMessage(
        subject=email_subject,
        body=body,
        from_email=sender,
        to=[address],
    )
    message.attach(filename, attachment, "application/pdf")

    try:
        sent = int(message.send(fail_silently=False) or 0)
    except Exception as error:
        raise ReportEmailError(f"InvenTree could not send the email: {error}") from error

    if sent < 1:
        raise ReportEmailError("InvenTree's email backend did not send the message.")
    return sent


def send_stock_entry_report_email(
    output: Any,
    recipient: object,
    start: date,
    end: date,
    subject: object = "DiCor Monthly Stock Entry Report",
) -> int:
    """Email an inventory-inflow PDF with an accounting acknowledgement reminder."""

    address = normalize_recipient(recipient)
    email_subject = str(subject or "").strip() or "DiCor Monthly Stock Entry Report"
    if not email_delivery_available():
        raise ReportEmailError("InvenTree's outgoing email server is not configured.")

    from django.conf import settings
    from django.core.mail import EmailMessage

    sender = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if not sender:
        raise ReportEmailError("InvenTree does not have a default sender address.")

    message = EmailMessage(
        subject=f"{email_subject} - {start:%B %Y}",
        body=(
            f"Attached are inventory inflows recorded from {start} through {end}.\n\n"
            "After posting the totals, open Reporting in InvenTree and mark this period "
            "as recorded with the accounting reference.\n\n"
            "INTERNAL - DiCor Engineering"
        ),
        from_email=sender,
        to=[address],
    )
    message.attach(
        f"stock-entries-{start.isoformat()}-to-{end.isoformat()}.pdf",
        _read_report_pdf(output),
        "application/pdf",
    )
    try:
        sent = int(message.send(fail_silently=False) or 0)
    except Exception as error:
        raise ReportEmailError(f"InvenTree could not send the email: {error}") from error
    if sent < 1:
        raise ReportEmailError("InvenTree's email backend did not send the message.")
    return sent


def generate_and_email_replenishment_report(
    recipient: object,
    subject: object = DEFAULT_EMAIL_SUBJECT,
):
    """Generate the current PDF and email it from an existing worker task."""

    output = generate_replenishment_report()
    send_replenishment_report_email(output, recipient, subject)
    return output


def queue_replenishment_report_email(
    plugin_slug: object,
    recipient: object,
):
    """Queue the plugin's configured email job on InvenTree's worker."""

    slug = str(plugin_slug or "").strip()
    if not slug:
        raise ReportEmailError("The Inventory Manager plugin is not available.")

    normalize_recipient(recipient)
    if not email_delivery_available():
        raise ReportEmailError(
            "InvenTree's outgoing email server is not configured."
        )

    from InvenTree.tasks import offload_task

    try:
        task = offload_task(
            "plugin.registry.call_plugin_function",
            slug,
            "send_configured_report_email",
            group="inventory-manager-email",
        )
    except Exception as error:
        raise ReportEmailError(
            f"InvenTree could not queue the report email: {error}"
        ) from error

    if not task:
        raise ReportEmailError("InvenTree could not queue the report email.")
    return task
