# InvenTree Inventory Manager

Inventory Manager adds calculated stock-level data to an InvenTree report
template. It provides:

- one combined row per active, non-virtual part;
- a configurable assumed minimum when `minimum_stock` is not configured;
- `critical`, `reorder`, `low_buffer`, and `healthy` classifications;
- healthy parts omitted from the actionable report;
- a configurable replenishment target;
- a responsive reporting dashboard with separate replenishment and stock-entry workflows;
- optional scheduled PDF delivery by email through InvenTree's background
  worker; and
- manual date-window and automatic prior-calendar-month stock-entry reports;
- a durable accounting register with report delivery and acknowledgement records; and
- an authenticated native dashboard for compatible versions of the InvenTree
  mobile app, without passing the user's API token to a browser.

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
`inventree_plugins` entry-point group. Version 0.5.0 targets InvenTree 1.3.x;
the stock-history contract should be reviewed before enabling it on a future
InvenTree 1.4 release.

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

Create a second report template targeting the **Part** model for stock inflows:

1. Name it exactly **Monthly Stock Entry Report**, or add
   `[inventory-manager:stock-entries]` to its description.
2. Upload `src/inventory_manager/templates/inventory_manager/stock_entry_report.html`.
3. Leave **Merge** disabled.

The stock-entry report uses InvenTree's dated stock-history records for manual
stock-item creation, manual additions, purchase-order receipts, and completed
build output. It deliberately excludes returns and stock counts. Stored StockItem
purchase prices provide valuation where available; currencies remain separate and
events without a value are explicitly counted for review.

## Inventory Manager screen

Enable InvenTree's **Plugin URL Integration**, **Plugin UI Integration**, and
**Plugin Schedule Integration**, then reload the plugins. An **Inventory
Manager** item will appear in the main navigation. The same page is available
directly at `/plugin/inventory-manager/`.

Both report workflows are available to authenticated users. Administrators can
also change the replenishment policy and delivery interval, plus the independent
stock-entry recipient, subject, enabled state, and monthly delivery day.
Automatic reports are retained in the Recent Reports list on the same screen.

Plugin settings and generated report records use InvenTree's own database
models, so the normal `invoke backup`, `invoke restore`, and `invoke update`
workflows include them. Install the same plugin version before restoring an
InvenTree database onto another server.

Version 0.4.0 added the `StockEntryReportRun` plugin table. Version 0.5.0 adds
settings only and does not alter that table. Install the current plugin before
running `invoke update`; existing run history is retained. Each run stores its
period, PDF job, recipient, delivery state, error, and optional accounting
acknowledgement.

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

Monthly stock-entry delivery has its own recipient, subject, toggle, and delivery
day from 1 through 28. It always covers the complete prior calendar month, and
its period key prevents a successful month from being sent twice. After the
recipient enters the totals in the accounting system, they return to Reporting
and use **Mark Recorded** with an accounting reference or note. Unacknowledged
periods stay visible in the register.
