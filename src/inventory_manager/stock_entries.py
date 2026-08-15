"""Inventory-inflow reporting from InvenTree's immutable stock history."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

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

    def as_context(self) -> dict[str, object]:
        return asdict(self)


def summarize_stock_entries(entries: Iterable[StockEntry]) -> dict[str, object]:
    """Build event, quantity and per-currency valuation totals."""

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
    }


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

    entries = []
    for event in queryset.iterator():
        quantity = tracking_quantity(event.tracking_type, event.deltas)
        if quantity <= 0:
            continue

        item = event.item
        price = getattr(item, "purchase_price", None) if item else None
        amount = getattr(price, "amount", None)
        currency = getattr(getattr(price, "currency", None), "code", "")
        unit_value = Decimal(str(amount)) if amount is not None else None
        total_value = unit_value * quantity if unit_value is not None else None
        part = event.part
        part_name = str(getattr(part, "full_name", "") or part or "Deleted part")
        user_name = ""
        if event.user:
            user_name = event.user.get_full_name().strip() or event.user.get_username()

        entries.append(
            StockEntry(
                event_id=event.pk,
                entered_at=event.date,
                part_id=getattr(part, "pk", None),
                part_name=part_name,
                source=SOURCE_LABELS.get(event.tracking_type, "Stock entered"),
                quantity=quantity,
                unit_value=unit_value,
                currency=currency,
                total_value=total_value,
                user_name=user_name,
                location=compact_stock_location(getattr(item, "location", None)),
                notes=str(event.notes or ""),
            )
        )

    return entries


def build_stock_entry_context(
    start: date,
    end: date,
    entries: Iterable[StockEntry] | None = None,
) -> dict[str, object]:
    """Build the context used by the monthly and manual stock-entry PDF."""

    rows = list(stock_entries_from_inventree(start, end) if entries is None else entries)
    return {
        "stock_entry_period_start": start,
        "stock_entry_period_end": end,
        "stock_entry_items": [row.as_context() for row in rows],
        "stock_entry_summary": summarize_stock_entries(rows),
    }
