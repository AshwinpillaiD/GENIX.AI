import csv
import time
import re
import os
import pandas as pd
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EXCEL_FILE  = "vme.xlsx"
OUTPUT_CSV  = "civic_variant_type.csv"

FIELDNAMES = ["civic_id", "Variant Name", "Full Name", "url"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean(text):
    return text.strip().replace("\xa0", " ") if text else ""


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------
def load_variant_ids(excel_path):
    df = pd.read_excel(excel_path)
    ids = []
    for url in df["variants"].dropna():
        match = re.search(r"/variants/(\d+)", str(url))
        if match:
            ids.append(int(match.group(1)))
    seen = set()
    unique_ids = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            unique_ids.append(i)
    print(f"Loaded {len(unique_ids)} unique variant IDs from {excel_path}")
    return unique_ids


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
# Core scraper — ONLY Variant Type + url (everything else removed)
# ---------------------------------------------------------------------------
def get_gene_full_name(page):
    """
    The Gene tag (cvc-feature-tag nz-tag) has an nz-popover that only
    renders its content (Full Name, Aliases, Variants, etc.) once you
    hover over it. So: hover the gene tag, wait for the popover to
    appear, then read the 'Full Name' row out of it.
    """
    full_name = ""
    try:
        gene_tag = page.locator("cvc-feature-tag nz-tag").first
        gene_tag.hover()

        # popover renders into an overlay appended elsewhere in the DOM,
        # not inside the cell — wait for it to show up
        page.wait_for_selector(".ant-popover:not(.ant-popover-hidden)", timeout=5000)
        page.wait_for_timeout(500)

        popover = page.locator(".ant-popover:not(.ant-popover-hidden)").last
        rows = popover.locator("tr.ant-descriptions-row")
        for i in range(rows.count()):
            row = rows.nth(i)
            label_cells = row.locator("td.ant-descriptions-item-label")
            value_cells = row.locator("td.ant-descriptions-item-content")
            for j in range(label_cells.count()):
                label = clean(label_cells.nth(j).inner_text()).strip().lower()
                if label == "full name":
                    if j < value_cells.count():
                        full_name = clean(value_cells.nth(j).inner_text())
                    break
            if full_name:
                break
    except Exception:
        pass
    return full_name


def scrape_variant(page, variant_id):
    url = f"https://civicdb.org/variants/{variant_id}/summary"
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_selector("text=Aliases", timeout=30000)
    page.wait_for_timeout(1000)

    row = {"civic_id": variant_id, "url": url, "Variant Name": "", "Full Name": ""}

    try:
        variant_name = page.locator(
            "#relations-summary span[nz-typography] strong"
        ).first.inner_text()
        row["Variant Name"] = clean(variant_name)
        print(f"  Variant Name: {row['Variant Name']}")
    except Exception:
        row["Variant Name"] = ""
        print(f"  Variant Name: not found")

    row["Full Name"] = get_gene_full_name(page)
    print(f"  Full Name: {row['Full Name'] or 'not found'}")

    return row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    variant_ids  = load_variant_ids(EXCEL_FILE)
    already_done = load_already_scraped(OUTPUT_CSV)

    if already_done:
        print(f"Resuming — {len(already_done)} already scraped, skipping them.")

    pending = [v for v in variant_ids if v not in already_done]
    print(f"Variants to scrape: {len(pending)}")

    if not pending:
        print("All variants already scraped!")
        return

    failed = []
    total  = len(pending)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        for idx, vid in enumerate(pending, 1):
            print(f"[{idx}/{total}] Scraping variant {vid} ...")
            try:
                row = scrape_variant(page, vid)
                append_row_to_csv(row, OUTPUT_CSV, FIELDNAMES)
                print(f"  ✓ Variant Name: {row.get('Variant Name','')}  "
                      f"Full Name: {row.get('Full Name','')}")

            except Exception as e:
                print(f"  ✗ Failed for {vid}: {e}")
                failed.append(vid)

            time.sleep(1)

        browser.close()

    print(f"\nDone! Saved to {OUTPUT_CSV}")
    if failed:
        print(f"Failed IDs ({len(failed)}): {failed}")


if __name__ == "__main__":
    main()