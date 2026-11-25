# GFS Dashboard

Live extraction runner for six public Chartink screeners.

## Screeners

1. AdvanceGFSCashStocks
2. AdvanceGFSStocksFuture
3. ValueBuyStocksCash
4. GFSSTOCKCASH
5. GFSFSTOCKSFUTURE
6. SECTORINDICES

The runner uses Playwright/Chromium to load each screener and capture the live
Chartink `/screener/process` response. It builds:

- `gfs_dashboard_latest.xlsx` — six separate result sheets plus raw fields
- `gfs_dashboard_latest.json` — machine-readable current results

## Mobile refresh

In GitHub:

1. Open the repository.
2. Open **Actions**.
3. Select **Refresh GFS Dashboard**.
4. Tap **Run workflow**.
5. Open the completed run and download the `gfs-dashboard-latest` artifact.

No Chartink password or cookies are required for these public screeners.

## Important

The six screener URLs and extraction logic are in `gfs_dashboard.py`.
Do not replace the dynamic extraction with hard-coded result rows.
