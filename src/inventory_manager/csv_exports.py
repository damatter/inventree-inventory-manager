"""CSV exports for both Inventory Manager report types."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any


def _text(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _csv_bytes(headers: list[str], rows: Iterable[Iterable[object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows([_text(value) for value in row] for row in rows)
    return buffer.getvalue().encode("utf-8-sig")


def replenishment_csv(context: Mapping[str, Any]) -> bytes:
    """Serialize the actionable replenishment rows."""

    items = context.get("replenishment_items", [])
    return _csv_bytes(
        [
            "Part ID",
            "Part",
            "Description",
            "Locations",
            "Available",
            "Configured Minimum",
            "Effective Minimum",
            "Minimum Assumed",
            "Target",
            "Suggested Order",
            "Status",
        ],
        (
            (
                row.get("part_id"),
                row.get("part_name"),
                row.get("description"),
                row.get("location_display"),
                row.get("available"),
                row.get("configured_minimum"),
                row.get("minimum"),
                "Yes" if row.get("minimum_assumed") else "No",
                row.get("target"),
                row.get("suggested_order"),
                row.get("status"),
            )
            for row in items
        ),
    )


def stock_entry_csv(context: Mapping[str, Any]) -> bytes:
    """Serialize every stock-entry event in an explicit date window."""

    items = context.get("stock_entry_items", [])
    return _csv_bytes(
        [
            "Event ID",
            "Entered At",
            "Part ID",
            "Part",
            "Source",
            "Quantity",
            "Unit Value",
            "Currency",
            "Total Value",
            "Location",
            "User",
            "Notes",
        ],
        (
            (
                row.get("event_id"),
                row.get("entered_at"),
                row.get("part_id"),
                row.get("part_name"),
                row.get("source"),
                row.get("quantity"),
                row.get("unit_value"),
                row.get("currency"),
                row.get("total_value"),
                row.get("location"),
                row.get("user_name"),
                row.get("notes"),
            )
            for row in items
        ),
    )
