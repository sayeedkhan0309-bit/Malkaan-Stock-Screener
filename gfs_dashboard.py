#!/usr/bin/env python3
"""
GFS Dashboard runner for six public Chartink screeners.

Usage:
    python gfs_dashboard.py

Requirements:
    python -m pip install playwright pandas requests
    python -m playwright install chromium

The runner opens each public saved screener in Chromium, captures the
screener's dynamic network responses, and tries to extract the current
result records. It does not require a Chartink password/cookies.

It writes:
    gfs_dashboard_latest.xlsx
    gfs_dashboard_latest.json
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from playwright.async_api import async_playwright

SCREENS = [
    ("AdvanceGFSCashStocks", "https://chartink.com/screener/advancegfscashstocks"),
    ("AdvanceGFSStocksFuture", "https://chartink.com/screener/advancegfsstocksfuture"),
    ("ValueBuyStocksCash", "https://chartink.com/screener/vlauebuystockscash"),
    ("GFSSTOCKCASH", "https://chartink.com/screener/gfsstockcash"),
    ("GFSFSTOCKSFUTURE", "https://chartink.com/screener/gfswithsector"),
    ("SECTORINDICES", "https://chartink.com/screener/gfs-60610539"),
]

FIXED_COLUMNS = [
    "Sr",
    "Symbol",
    "Stock/Index Name",
    "BSE Code",
    "% Change",
    "Close",
    "Volume",
]

OUT_XLSX = Path("gfs_dashboard_latest.xlsx")
OUT_JSON = Path("gfs_dashboard_latest.json")


def normalize_record(record):
    if not isinstance(record, dict):
        return {}
    # Keep the original fields; only map common Chartink field names for the
    # fixed dashboard view.
    return record


def pick(rec, *keys):
    for k in keys:
        if k in rec and rec[k] not in (None, ""):
            return rec[k]
    return ""


def fixed_view(records):
    rows = []
    for i, r in enumerate(records, 1):
        rows.append({
            "Sr": i,
            "Symbol": pick(r, "nsecode", "symbol", "code", "NSECode"),
            "Stock/Index Name": pick(r, "name", "stock_name", "company_name"),
            "BSE Code": pick(r, "bsecode", "bse_code", "BSECode"),
            "% Change": pick(r, "per_chg", "percent_change", "pchange", "% Change"),
            "Close": pick(r, "close", "Close", "price"),
            "Volume": pick(r, "volume", "Volume"),
        })
    return rows


async def run_screen(page, title, url):
    captured = []

    async def on_response(response):
        try:
            if response.request.method.upper() != "POST":
                return
            u = response.url.lower()
            if "screener/process" not in u:
                return
            ctype = (response.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                return
            body = await response.json()
            if isinstance(body, dict) and isinstance(body.get("data"), list):
                captured.append(body)
        except Exception:
            pass

    page.on("response", on_response)
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # Let Chartink's client-side scanner execute and render.
    await page.wait_for_timeout(12000)

    # A few scanners can take longer during busy market periods.
    for _ in range(6):
        if captured:
            break
        await page.wait_for_timeout(5000)

    if not captured:
        return {
            "title": title,
            "url": url,
            "status": "NO_LIVE_RESPONSE_CAPTURED",
            "records": [],
            "raw_fields": [],
        }

    # Prefer the last response because it is normally the final/current scan.
    payload = captured[-1]
    records = [normalize_record(x) for x in payload.get("data", []) if isinstance(x, dict)]

    fields = []
    seen = set()
    for r in records:
        for k in r:
            if k not in seen:
                seen.add(k)
                fields.append(k)

    return {
        "title": title,
        "url": url,
        "status": "OK",
        "records": records,
        "raw_fields": fields,
    }


async def main():
    extracted_at = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        results = []
        for title, url in SCREENS:
            print(f"Running: {title} ...", flush=True)
            result = await run_screen(page, title, url)
            result["extracted_at"] = extracted_at
            results.append(result)
            print(
                f"  {result['status']} | rows={len(result['records'])} "
                f"| fields={len(result['raw_fields'])}",
                flush=True,
            )

        await browser.close()

    # Excel dashboard: one sheet per screener + metadata.
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        meta = pd.DataFrame({
            "Field": ["Extracted at", "Timezone", "Screeners", "Mode"],
            "Value": [
                extracted_at,
                "Asia/Kolkata",
                len(results),
                "Live browser/network capture",
            ],
        })
        meta.to_excel(writer, sheet_name="Dashboard", index=False)

        for result in results:
            rows = fixed_view(result["records"])
            df = pd.DataFrame(rows, columns=FIXED_COLUMNS)
            safe_name = re.sub(r"[:\\/?*\[\]]", "_", result["title"])[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)

            # Add raw returned fields on a separate sheet so no Chartink field
            # is lost even if it is not part of the fixed dashboard.
            raw = pd.DataFrame(result["records"])
            raw_name = (safe_name[:25] + "_raw")[:31]
            raw.to_excel(writer, sheet_name=raw_name, index=False)

    payload = {
        "extracted_at": extracted_at,
        "timezone": "Asia/Kolkata",
        "screeners": results,
        "fixed_columns": FIXED_COLUMNS,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== GFS DASHBOARD ===")
    print(f"Extracted: {extracted_at}")
    for result in results:
        print(f"\n## {result['title']} — {result['status']}")
        df = pd.DataFrame(fixed_view(result["records"]), columns=FIXED_COLUMNS)
        if df.empty:
            print("(No live rows captured)")
        else:
            print(df.to_string(index=False))

    print(f"\nSaved: {OUT_XLSX.resolve()}")
    print(f"Saved: {OUT_JSON.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
