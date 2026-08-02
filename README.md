# InvenTree Inventory Manager

Inventory Manager adds calculated stock-level data to an InvenTree report
template. The first milestone provides an inventory replenishment report with:

- one combined row per active, non-virtual part;
- an assumed minimum of `2` when `minimum_stock` is not configured;
- `critical`, `reorder`, `low_buffer`, and `healthy` classifications;
- healthy parts omitted from the actionable report;
- a suggested replenishment quantity which restores stock to twice the
  effective minimum; and
- accurate summary counts calculated in Python.

Email delivery and weekly scheduling are intentionally deferred until the
report calculations have been tested against a real InvenTree installation.

## Stock rules

| Status | Rule |
| --- | --- |
| Critical | Available quantity is zero or less |
| Reorder | Available quantity is greater than zero but below minimum |
| Low buffer | Available quantity is at least minimum but below 2 x minimum |
| Healthy | Available quantity is at least 2 x minimum |

`Available` currently means the sum of all InvenTree stock items which match
InvenTree's built-in `IN_STOCK_FILTER`, grouped by their exact part. Stock held
against a parent template's variants is not counted twice.

## Development

The pure calculation code has no InvenTree dependency, so its tests can run in
a normal Python environment:

```console
python -m unittest discover -s tests -v
```

To install the package in an InvenTree development environment:

```console
python -m pip install --editable .
```

The package exposes `InventoryManagerPlugin` through the required
`inventree_plugins` entry-point group. It targets InvenTree 1.0.0 and newer.

## InvenTree report setup

1. Install the package and restart both the InvenTree server and background
   worker.
2. Enable **Inventory Manager** in Admin Center > Plugins.
3. Create a report template targeting the **Part** model.
4. Name it exactly **Inventory Replenishment Report**, or place
   `[inventory-manager:replenishment]` in its description.
5. Upload
   `src/inventory_manager/templates/inventory_manager/replenishment_report.html`.
6. Leave **Merge** disabled and print the template against one part. The
   selected part only acts as the report anchor; the plugin evaluates every
   active, non-virtual part.

The plugin only performs the inventory query for a report carrying the name or
description marker above, so ordinary InvenTree reports are unaffected.

