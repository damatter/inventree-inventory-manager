"""Inventory-inflow reporting from InvenTree's immutable stock history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

# Values are stable InvenTree StockHistoryCode identifiers. Keeping the pure
# helpers numeric lets their tests run without importing Django / InvenTree.
CREATED = 1
STOCK_ADD = 11
BUILD_OUTPUT_COMPLETED = 55
RECEIVED_AGAINST_PURCHASE_ORDER = 70
INBOUND_TRACKING_TYPES = (
    CREATED,
    STOCK_ADD,
    BUILD_OUTPUT_COMPLETED,
    RECEIVED_AGAINST_PURCHASE_ORDER,
)

SOURCE_LABELS = {
    CREATED: "Manual stock item created",
    STOCK_ADD: "Manual stock added",
    BUILD_OUTPUT_COMPLETED: "Build output completed",
    RECEIVED_AGAINST_PURCHASE_ORDER: "Purchase order received",
}


def previous_month_window(today: date | None = None) -> tuple[date, date]:
    """Return the complete prior calendar month as an inclusive date range."""

    current = today or date.today()
    first_this_month = current.replace(day=1)
    last_previous_month = first_this_month - timedelta(days=1)
    return last_previous_month.replace(day=1), last_previous_month


def scheduled_stock_entry_window(
    today: date | None = None, interval_days: int = 30
) -> tuple[date, date]:
    """Return the most recent complete interval, ending yesterday."""

    current = today or date.today()
    days = min(max(int(interval_days), 1), 365)
    end = current - timedelta(days=1)
    return end - timedelta(days=days - 1), end


def tracking_quantity(tracking_type: int, deltas: object) -> Decimal:
    """Extract the quantity that entered inventory for one history event."""

    values = deltas if isinstance(deltas, dict) else {}
    key = "added" if tracking_type == STOCK_ADD else "quantity"
    try:
        quantity = Decimal(str(values.get(key, "0")))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return max(quantity, Decimal("0"))


@dataclass(frozen=True)
class StockEntry:
    """One auditable inventory inflow."""

    event_id: int
    entered_at: datetime
    part_id: int | None
    part_name: str
    source: str
    quantity: Decimal
    unit_value: Decimal | None = None
    currency: str = ""
    total_value: Decimal | None = None
    user_name: str = ""
    location: str = ""
    notes: str = ""
    lowest_sale_price: Decimal | None = None
    highest_sale_price: Decimal | None = None
    pricing_error: str = ""

    def as_context(self) -> dict[str, object]:
        return asdict(self)


def summarize_stock_entries(entries: Iterable[StockEntry]) -> dict[str, object]:
    """Build event and per-currency material-value totals.

    ``total_quantity`` remains in the context for backwards compatibility with
    existing integrations, but the PDF no longer presents it as a useful
    accounting metric.
    """

    rows = list(entries)
    total_quantity = sum((row.quantity for row in rows), Decimal("0"))
    totals: dict[str, Decimal] = {}
    unvalued_count = 0

    for row in rows:
        if row.total_value is None or not row.currency:
            unvalued_count += 1
            continue
        totals[row.currency] = totals.get(row.currency, Decimal("0")) + row.total_value

    return {
        "event_count": len(rows),
        "total_quantity": total_quantity,
        "valuation_totals": [
            {"currency": currency, "total": total}
            for currency, total in sorted(totals.items())
        ],
        "unvalued_count": unvalued_count,
        "pricing_error_count": sum(bool(row.pricing_error) for row in rows),
    }


def _blank_pricing_values(part_ids: Iterable[int], error: str) -> dict[int, dict[str, Any]]:
    """Return a complete, safely blank pricing result for every part."""

    return {
        int(part_id): {
            "currency": "",
            "unit_material_cost": None,
            "lowest_sale_price": None,
            "highest_sale_price": None,
            "error": error,
        }
        for part_id in dict.fromkeys(int(value) for value in part_ids)
    }


def load_customer_pricing_values(part_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """Load one Customer Pricing snapshot for all requested parts.

    Customer Pricing is an optional companion plugin. A missing, older, or
    temporarily unavailable installation must leave explicit blanks in this
    report instead of preventing stock reporting from working.
    """

    normalized_ids = tuple(dict.fromkeys(int(part_id) for part_id in part_ids))
    if not normalized_ids:
        return {}

    try:
        from inventree_customer_pricing.reporting import reporting_values_for_parts
    except (ImportError, ModuleNotFoundError):
        return _blank_pricing_values(
            normalized_ids,
            "Customer Pricing 0.6.1 or newer is required for pricing values.",
        )

    try:
        values = reporting_values_for_parts(normalized_ids)
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        return _blank_pricing_values(
            normalized_ids,
            f"Customer Pricing values are temporarily unavailable: {detail}",
        )

    result: dict[int, dict[str, Any]] = {}
    for part_id in normalized_ids:
        value = values.get(part_id)
        if value is None:
            result.update(
                _blank_pricing_values(
                    [part_id], "Customer Pricing returned no result for this part."
                )
            )
            continue

        result[part_id] = {
            "currency": str(_pricing_field(value, "currency", "") or ""),
            "unit_material_cost": _pricing_field(value, "unit_material_cost"),
            "lowest_sale_price": _pricing_field(value, "lowest_sale_price"),
            "highest_sale_price": _pricing_field(value, "highest_sale_price"),
            "error": str(_pricing_field(value, "error", "") or ""),
        }

    return result


def user_can_view_stock_entry_pricing(user: object) -> bool:
    """Apply Customer Pricing's access policy when that API is installed.

    Older or absent companion versions cannot provide monetary values, so the
    pre-existing stock-history report remains available with blank pricing.
    Once the pricing API is present, any policy error fails closed.
    """

    try:
        from inventree_customer_pricing.reporting import (
            user_can_view_reporting_values,
        )
    except (ImportError, ModuleNotFoundError):
        return True

    try:
        return bool(user_can_view_reporting_values(user))
    except Exception:
        return False


def _decimal_or_none(value: object) -> Decimal | None:
    """Normalize an optional monetary value returned by Customer Pricing."""

    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _pricing_field(value: object, name: str, default: Any = None) -> Any:
    """Read one field from either a public pricing dataclass or dictionary."""

    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def stock_entries_from_inventree(start: date, end: date) -> list[StockEntry]:
    """Load inbound stock history for an inclusive local-date window."""

    from django.utils import timezone
    from stock.models import StockItemTracking

    from .reports import compact_stock_location

    start_at = timezone.make_aware(datetime.combine(start, time.min))
    end_at = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
    queryset = (
        StockItemTracking.objects.filter(
            tracking_type__in=INBOUND_TRACKING_TYPES,
            date__gte=start_at,
            date__lt=end_at,
        )
        .select_related("part", "item", "item__location", "user")
        .order_by("date", "pk")
    )

    inbound_events = []
    for event in queryset.iterator():
        quantity = tracking_quantity(event.tracking_type, event.deltas)
        if quantity <= 0:
            continue

        inbound_events.append((event, quantity))

    part_ids = [
        int(event.part.pk)
        for event, _quantity in inbound_events
        if event.part is not None and getattr(event.part, "pk", None) is not None
    ]
    pricing_values = load_customer_pricing_values(part_ids)

    entries = []
    for event, quantity in inbound_events:
        item = event.item
        part = event.part
        part_id = getattr(part, "pk", None)
        pricing = pricing_values.get(int(part_id), {}) if part_id is not None else {}
        unit_value = _decimal_or_none(pricing.get("unit_material_cost"))
        lowest_sale_price = _decimal_or_none(pricing.get("lowest_sale_price"))
        highest_sale_price = _decimal_or_none(pricing.get("highest_sale_price"))
        currency = str(pricing.get("currency", "") or "")
        total_value = unit_value * quantity if unit_value is not None else None
        part_name = str(getattr(part, "full_name", "") or part or "Deleted part")
        user_name = ""
        if event.user:
            user_name = event.user.get_full_name().strip() or event.user.get_username()

        entries.append(
            StockEntry(
                event_id=event.pk,
                entered_at=event.date,
                part_id=part_id,
                part_name=part_name,
                source=SOURCE_LABELS.get(event.tracking_type, "Stock entered"),
                quantity=quantity,
                unit_value=unit_value,
                currency=currency,
                total_value=total_value,
                user_name=user_name,
                location=compact_stock_location(getattr(item, "location", None)),
                notes=str(event.notes or ""),
                lowest_sale_price=lowest_sale_price,
                highest_sale_price=highest_sale_price,
                pricing_error=str(pricing.get("error", "") or ""),
            )
        )

    return entries


def build_stock_entry_context(
    start: date,
    end: date,
    entries: Iterable[StockEntry] | None = None,
) -> dict[str, object]:
    """Build the context used by scheduled and manual stock-entry exports."""

    rows = list(stock_entries_from_inventree(start, end) if entries is None else entries)
    pricing_errors = tuple(
        dict.fromkeys(row.pricing_error for row in rows if row.pricing_error)
    )
    return {
        "stock_entry_period_start": start,
        "stock_entry_period_end": end,
        "stock_entry_items": [row.as_context() for row in rows],
        "stock_entry_summary": summarize_stock_entries(rows),
        "stock_entry_pricing_errors": pricing_errors,
    }
