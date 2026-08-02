"""Adapters between InvenTree models and the pure inventory calculations."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from .inventory import InventoryPolicy, PartStock, build_replenishment_report

REPORT_NAME = "inventory replenishment report"
REPORT_DESCRIPTION_MARKER = "[inventory-manager:replenishment]"


def is_replenishment_report_template(report_instance: object) -> bool:
    """Return whether an InvenTree template opts into replenishment context."""

    name = str(getattr(report_instance, "name", "")).strip().casefold()
    description = str(getattr(report_instance, "description", "")).casefold()
    return name == REPORT_NAME or REPORT_DESCRIPTION_MARKER in description


def snapshots_from_inventree() -> list[PartStock]:
    """Load active physical parts and combine their in-stock StockItem quantities.

    Imports are local so the business rules and their unit tests do not need a
    complete InvenTree / Django runtime.
    """

    from part.models import Part
    from stock.models import StockItem

    parts = list(
        Part.objects.filter(active=True, virtual=False)
        .select_related("default_location")
        .only(
            "id",
            "name",
            "description",
            "IPN",
            "revision",
            "minimum_stock",
            "default_location",
        )
    )

    quantities: defaultdict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    locations: defaultdict[int, set[str]] = defaultdict(set)
    part_ids = [part.pk for part in parts]

    stock_items = (
        StockItem.objects.filter(StockItem.IN_STOCK_FILTER, part_id__in=part_ids)
        .select_related("location")
        .only("part_id", "quantity", "location")
    )

    for stock_item in stock_items.iterator():
        quantities[stock_item.part_id] += Decimal(stock_item.quantity)
        if stock_item.location is not None:
            locations[stock_item.part_id].add(str(stock_item.location))

    snapshots = []

    for part in parts:
        part_locations = locations[part.pk]
        if not part_locations and part.default_location is not None:
            part_locations.add(str(part.default_location))

        snapshots.append(
            PartStock(
                part_id=part.pk,
                name=part.full_name,
                description=part.description or "",
                available=quantities[part.pk],
                configured_minimum=part.minimum_stock,
                locations=tuple(part_locations),
            )
        )

    return snapshots


def build_report_context(
    snapshots: Iterable[PartStock] | None = None,
    policy: InventoryPolicy | None = None,
) -> dict[str, object]:
    """Build the complete context extension for an InvenTree report."""

    if snapshots is None:
        snapshots = snapshots_from_inventree()

    return build_replenishment_report(snapshots, policy=policy).as_context()

