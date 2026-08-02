"""Pure inventory replenishment calculations.

This module deliberately has no Django or InvenTree imports. Keeping the
business rules independent makes them fast to test and reusable by future
report, email, scheduler, and dashboard integrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Iterable

ZERO = Decimal("0")


def as_decimal(value: Decimal | int | str) -> Decimal:
    """Convert a supported numeric input to an exact ``Decimal`` value."""

    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class StockStatus(StrEnum):
    """Stock health classifications in descending urgency."""

    CRITICAL = "critical"
    REORDER = "reorder"
    LOW_BUFFER = "low_buffer"
    HEALTHY = "healthy"


STATUS_ORDER = {
    StockStatus.CRITICAL: 0,
    StockStatus.REORDER: 1,
    StockStatus.LOW_BUFFER: 2,
    StockStatus.HEALTHY: 3,
}


@dataclass(frozen=True, slots=True)
class InventoryPolicy:
    """Configuration for stock classification and replenishment targets."""

    assumed_minimum: Decimal = Decimal("2")
    target_multiplier: Decimal = Decimal("2")

    def __post_init__(self) -> None:
        object.__setattr__(self, "assumed_minimum", as_decimal(self.assumed_minimum))
        object.__setattr__(self, "target_multiplier", as_decimal(self.target_multiplier))

        if self.assumed_minimum <= ZERO:
            raise ValueError("assumed_minimum must be greater than zero")
        if self.target_multiplier < Decimal("1"):
            raise ValueError("target_multiplier must be at least one")


@dataclass(frozen=True, slots=True)
class PartStock:
    """The stock data required to evaluate one InvenTree part."""

    part_id: int
    name: str
    description: str
    available: Decimal
    configured_minimum: Decimal
    locations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "available", as_decimal(self.available))
        object.__setattr__(
            self, "configured_minimum", as_decimal(self.configured_minimum)
        )
        object.__setattr__(self, "locations", tuple(sorted(set(self.locations))))


@dataclass(frozen=True, slots=True)
class ReplenishmentRow:
    """Calculated report data for one part."""

    part_id: int
    part_name: str
    description: str
    locations: tuple[str, ...]
    available: Decimal
    configured_minimum: Decimal
    minimum: Decimal
    minimum_assumed: bool
    target: Decimal
    suggested_order: Decimal
    status: StockStatus

    @property
    def location_display(self) -> str:
        """Return a printable, deterministic location list."""

        return ", ".join(self.locations)

    def as_context(self) -> dict[str, object]:
        """Return this row in a Django-template-friendly form."""

        return {
            "part_id": self.part_id,
            "part_name": self.part_name,
            "description": self.description,
            "locations": self.locations,
            "location_display": self.location_display,
            "available": self.available,
            "configured_minimum": self.configured_minimum,
            "minimum": self.minimum,
            "minimum_assumed": self.minimum_assumed,
            "target": self.target,
            "suggested_order": self.suggested_order,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class ReplenishmentReport:
    """Complete calculated report, including healthy parts in its summary."""

    rows: tuple[ReplenishmentRow, ...]
    critical_count: int
    reorder_count: int
    low_buffer_count: int
    healthy_count: int
    parts_evaluated: int
    policy: InventoryPolicy

    @property
    def review_count(self) -> int:
        """Return the number of actionable, non-healthy parts."""

        return self.critical_count + self.reorder_count + self.low_buffer_count

    def as_context(self) -> dict[str, object]:
        """Return context keys consumed by the bundled report template."""

        summary = {
            "critical_count": self.critical_count,
            "reorder_count": self.reorder_count,
            "low_buffer_count": self.low_buffer_count,
            "healthy_count": self.healthy_count,
            "review_count": self.review_count,
            "parts_evaluated": self.parts_evaluated,
        }

        return {
            "replenishment_items": [row.as_context() for row in self.rows],
            "inventory_summary": summary,
            "inventory_policy": {
                "assumed_minimum": self.policy.assumed_minimum,
                "target_multiplier": self.policy.target_multiplier,
            },
            **summary,
        }


def classify_stock(available: Decimal, minimum: Decimal, target: Decimal) -> StockStatus:
    """Classify a stock quantity using the agreed threshold boundaries."""

    if available <= ZERO:
        return StockStatus.CRITICAL
    if available < minimum:
        return StockStatus.REORDER
    if available < target:
        return StockStatus.LOW_BUFFER
    return StockStatus.HEALTHY


def evaluate_part(
    part: PartStock, policy: InventoryPolicy | None = None
) -> ReplenishmentRow:
    """Calculate the effective minimum, status, and suggested order for a part."""

    policy = policy or InventoryPolicy()
    minimum_assumed = part.configured_minimum <= ZERO
    minimum = policy.assumed_minimum if minimum_assumed else part.configured_minimum
    target = minimum * policy.target_multiplier
    status = classify_stock(part.available, minimum, target)
    suggested_order = max(target - part.available, ZERO)

    return ReplenishmentRow(
        part_id=part.part_id,
        part_name=part.name,
        description=part.description,
        locations=part.locations,
        available=part.available,
        configured_minimum=part.configured_minimum,
        minimum=minimum,
        minimum_assumed=minimum_assumed,
        target=target,
        suggested_order=suggested_order,
        status=status,
    )


def build_replenishment_report(
    parts: Iterable[PartStock], policy: InventoryPolicy | None = None
) -> ReplenishmentReport:
    """Build a sorted actionable report and summary from part stock snapshots."""

    policy = policy or InventoryPolicy()
    evaluated = [evaluate_part(part, policy) for part in parts]
    counts = {status: 0 for status in StockStatus}

    for row in evaluated:
        counts[row.status] += 1

    actionable = [row for row in evaluated if row.status is not StockStatus.HEALTHY]
    actionable.sort(
        key=lambda row: (
            STATUS_ORDER[row.status],
            row.part_name.casefold(),
            row.part_id,
        )
    )

    return ReplenishmentReport(
        rows=tuple(actionable),
        critical_count=counts[StockStatus.CRITICAL],
        reorder_count=counts[StockStatus.REORDER],
        low_buffer_count=counts[StockStatus.LOW_BUFFER],
        healthy_count=counts[StockStatus.HEALTHY],
        parts_evaluated=len(evaluated),
        policy=policy,
    )

