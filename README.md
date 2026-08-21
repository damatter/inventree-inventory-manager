# InvenTree Inventory Manager

Inventory Manager adds calculated stock-level data to an InvenTree report
template. It provides:

- one combined row per active, non-virtual part;
- a configurable assumed minimum when `minimum_stock` is not configured;
- `critical`, `reorder`, `low_buffer`, and `healthy` classifications;
- healthy parts omitted from the actionable report;
- a configurable replenishment target;
- a responsive reporting dashboard with separate replenishment and stock-entry workflows;
- optional scheduled PDF and CSV delivery to multiple email recipients through
  InvenTree's background worker;
- manual date-window and repeating-interval stock-entry reports;
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

## Install or update in InvenTree

Use this pinned source URL in the plugin installer:

```text
git+https://github.com/damatter/inventree-inventory-manager.git@0.7.0
```

The equivalent `plugins.txt` entry is:

```text
inventree-inventory-manager @ git+https://github.com/damatter/inventree-inventory-manager.git@0.7.0
```

Leave the separate version field blank because the Git tag pins the release.
After installation, run the normal `invoke update` workflow and restart the
InvenTree server and worker containers. No force recreation is required.

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
`inventree_plugins` entry-point group. Version 0.7.0 targets InvenTree 1.3.x;
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
build output. It deliberately excludes returns and stock counts. Install **Part
Pricing 0.6.1 or newer** before Inventory Manager 0.7.0. Material value is the
active material cost per unit multiplied by the quantity entered; lowest and
highest sale prices come from the actual active customer price breaks. The
companion plugin converts all figures to InvenTree's default currency. Missing
pricing or exchange rates leave explicit blanks instead of failing the report.

## Inventory Manager screen

Enable InvenTree's **Plugin URL Integration**, **Plugin UI Integration**, and
**Plugin Schedule Integration**, then reload the plugins. An **Inventory
Manager** item will appear in the main navigation. The same page is available
directly at `/plugin/inventory-manager/`.

Both report workflows are available to authenticated users. Administrators can
also change the replenishment policy and delivery interval, plus the independent
stock-entry recipients, subject, enabled state, and delivery interval.
Automatic reports are retained in the Recent Reports list on the same screen.

Because stock-entry exports contain both material costs and customer sale
prices, those PDF / CSV actions and their accounting register follow Part
Pricing's existing security boundary. A non-superuser needs membership in the
configured **Pricing access group** plus both purchase-order and sales-order
view roles. Replenishment reporting is unchanged. Scheduled stock-entry email
delivery remains an administrator-configured server task.

Plugin settings and generated report records use InvenTree's own database
models, so the normal `invoke backup`, `invoke restore`, and `invoke update`
workflows include them. Install the same plugin version before restoring an
InvenTree database onto another server.

Version 0.4.0 added the `StockEntryReportRun` plugin table. Version 0.6.1 adds a
normal database migration which expands the period key and recipient fields for
interval reports and multiple recipients. Install the current plugin before
running `invoke update`; existing run history is retained. Each run stores its
period, PDF job, recipient, delivery state, error, and optional accounting
acknowledgement.

Version 0.7.0 replaces StockItem purchase-price valuation with Part Pricing's
batched material and customer-price snapshot. It also gives both PDF workflows
a shared pending / ready / error screen. The stock-entry workflow displays its
progress page before starting the synchronous InvenTree 1.3.x renderer, so long
reports no longer leave an unexplained blank tab.

## Automatic email reporting

Before using email delivery, configure and verify InvenTree's outgoing email
settings. Then open the **Reporting** screen and:

1. Enter one or more comma-separated recipient email addresses and, optionally,
   customize the email subject.
2. Save the settings.
3. Select **Send test email** and confirm that the PDF and CSV arrive as email
   attachments.
4. Enable automatic reporting, choose the interval in days, and save the
   settings again.

Each scheduled job creates a new replenishment PDF, retains it in Recent
Reports, and emails it to the saved recipient as an attachment. The first run
is scheduled when the automation settings are saved; later runs repeat at the
configured interval.

Stock-entry delivery has its own recipients, subject, toggle, and interval in
days. Each scheduled report covers the complete period since the last successful
delivery, and its period key prevents a successful interval from being sent
twice. After the
recipient enters the totals in the accounting system, they return to Reporting
and use **Mark Recorded** with an accounting reference or note. Unacknowledged
periods stay visible in the register.
