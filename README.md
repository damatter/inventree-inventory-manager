# InvenTree Inventory Manager

Inventory Manager adds calculated stock-level data to an InvenTree report
template. It provides:

- one combined row per active, non-virtual part;
- a configurable assumed minimum when `minimum_stock` is not configured;
- `critical`, `reorder`, `low_buffer`, and `healthy` classifications;
- healthy parts omitted from the actionable report;
- a configurable replenishment target;
- a simple screen for settings and one-click PDF generation; and
- optional scheduled PDF delivery by email through InvenTree's background
  worker.

## Stock rules

| Status | Rule |
| --- | --- |
| Critical | Available quantity is zero or less |
| Reorder | Available quantity is greater than zero but below minimum |
| Low buffer | Available quantity is at least minimum but below the configured multiplier |
| Healthy | Available quantity is at or above the configured multiplier |

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
6. Leave **Merge** disabled. The selected part only acts as the report anchor;
   the plugin evaluates every active, non-virtual part.

The plugin only performs the inventory query for a report carrying the name or
description marker above, so ordinary InvenTree reports are unaffected.

## Inventory Manager screen

Enable InvenTree's **Plugin URL Integration**, **Plugin UI Integration**, and
**Plugin Schedule Integration**, then reload the plugins. An **Inventory
Manager** item will appear in the main navigation. The same page is available
directly at `/plugin/inventory-manager/`.

The large report button is available to authenticated users. Administrators
can also change the default minimum, low-buffer multiplier, automation toggle,
and automatic report interval. Automatic reports are retained in the Recent
Reports list on the same screen.

## Automatic email reporting

Before using email delivery, configure and verify InvenTree's outgoing email
settings. Then open the **Reporting** screen and:

1. Enter one recipient email address and, optionally, customize the email
   subject.
2. Save the settings.
3. Select **Send Test Report Now** and confirm that the PDF arrives as an email
   attachment.
4. Enable automatic reporting, choose the interval in days, and save the
   settings again.

Each scheduled job creates a new replenishment PDF, retains it in Recent
Reports, and emails it to the saved recipient as an attachment. The first run
is scheduled when the automation settings are saved; later runs repeat at the
configured interval.
