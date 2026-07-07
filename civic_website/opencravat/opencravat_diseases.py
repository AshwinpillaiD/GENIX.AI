import csv
import time
import os
import pandas as pd
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EXCEL_FILE  = "Gene_oncokb_website_1240.xlsx"
OUTPUT_CSV  = "opencravat_diseases.csv"

FIELDNAMES = ["civic_id", "url", "Diseases"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean(text):
    return text.strip().replace("\xa0", " ") if text else ""


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------
def load_targets(excel_path):
    """
    Read civic_id + OpenCravat Report url from the Excel file.
    Skips rows where the OpenCravat Report url is missing/blank.
    """
    df = pd.read_excel(excel_path)
    targets = []
    seen = set()
    for _, r in df.iterrows():
        civic_id = r.get("civic_id")
        oc_url = r.get("OpenCravat Report")

        if pd.isna(civic_id) or pd.isna(oc_url):
            continue
        oc_url = str(oc_url).strip()
        if not oc_url.lower().startswith("http"):
            continue

        cid = int(civic_id)
        if cid in seen:
            continue
        seen.add(cid)
        targets.append({"civic_id": cid, "url": oc_url})

    print(f"Loaded {len(targets)} OpenCravat URLs from {excel_path}")
    return targets


def load_already_scraped(csv_path, id_field="civic_id"):
    if not os.path.exists(csv_path):
        return set()
    done = set()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                done.add(int(row[id_field]))
            except (KeyError, ValueError):
                pass
    return done


def append_row_to_csv(row, csv_path, fieldnames):
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------
def scrape_diseases(page, oc_url):
    """
    Open the OpenCravat variant report page and read the 'Diseases' table:

        <table id="newtable">
          <thead><tr><th>Diseases</th></tr></thead>
          <tbody>
            <tr><td><p>Chronic Myeloid Leukemia</p></td></tr>
            ...
          </tbody>
        </table>

    There can be several table#newtable elements on the report (one per
    annotation category), so we find the one whose header text is
    exactly "Diseases" and read every row out of its tbody.
    """
    page.goto(oc_url, wait_until="networkidle", timeout=90000)

    # OpenCravat renders the report client-side after the page loads —
    # give it time and wait for at least one results table to show up.
    try:
        page.wait_for_selector("table#newtable", timeout=60000)
    except Exception:
        return ""

    page.wait_for_timeout(1500)

    diseases = []
    try:
        tables = page.locator("table#newtable")
        for i in range(tables.count()):
            tbl = tables.nth(i)
            header_cells = tbl.locator("thead th")
            if header_cells.count() == 0:
                continue
            header = clean(header_cells.first.inner_text())
            if header.strip().lower() != "diseases":
                continue

            rows = tbl.locator("tbody tr")
            for r in range(rows.count()):
                txt = clean(rows.nth(r).inner_text())
                if txt:
                    diseases.append(txt)
            break
    except Exception:
        pass

    return " | ".join(diseases)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    targets      = load_targets(EXCEL_FILE)
    already_done = load_already_scraped(OUTPUT_CSV)

    if already_done:
        print(f"Resuming — {len(already_done)} already scraped, skipping them.")

    pending = [t for t in targets if t["civic_id"] not in already_done]
    print(f"Rows to scrape: {len(pending)}")

    if not pending:
        print("All rows already scraped!")
        return

    failed = []
    total  = len(pending)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        for idx, t in enumerate(pending, 1):
            cid = t["civic_id"]
            oc_url = t["url"]
            print(f"[{idx}/{total}] Scraping civic_id {cid} ...")
            try:
                diseases = scrape_diseases(page, oc_url)
                row = {"civic_id": cid, "url": oc_url, "Diseases": diseases}
                append_row_to_csv(row, OUTPUT_CSV, FIELDNAMES)
                print(f"  ✓ Diseases: {diseases or 'not found'}")

            except Exception as e:
                print(f"  ✗ Failed for {cid}: {e}")
                failed.append(cid)

            time.sleep(1)

        browser.close()

    print(f"\nDone! Saved to {OUTPUT_CSV}")
    if failed:
        print(f"Failed IDs ({len(failed)}): {failed}")


if __name__ == "__main__":
    main()