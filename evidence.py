import csv
import time
import re
import os
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EXCEL_FILE   = "vme.xlsx"
OUTPUT_CSV   = "civic_evidence_bs4.csv"

EMPTY_VALUES = {
    "none found", "none provided", "not available",
    "not specified", "none specified", "--", "-", "n/a", ""
}

FIELDNAMES = [
    "evidence_id",
    "Type",
    "Direction",
    "Significance",
    "Variant Origin",
    "Level",
    "Rating",
    "Source",
    "Source Link", 
    # "Clinical Trial",
    # "Disease",
    # "Therapies",
    # "Description",
    "url"
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean(text):
    return text.strip().replace("\xa0", " ") if text else ""


def normalize(value):
    v = clean(value)
    if "\n" in v and len(v) > 200:
        return ""
    if v.lower() in EMPTY_VALUES:
        return ""
    return v


def load_evidence_ids(excel_path):
    df = pd.read_excel(excel_path)
    ids = []
    for url in df["evidence"].dropna():
        match = re.search(r"/evidence/(\d+)", str(url))
        if match:
            ids.append(int(match.group(1)))
    seen = set()
    unique_ids = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            unique_ids.append(i)
    print(f"Loaded {len(unique_ids)} unique evidence IDs from {excel_path}")
    return unique_ids


def load_already_scraped(csv_path, id_field="evidence_id"):
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
    """Append a single row immediately after scraping — no data loss on crash."""
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def clean_row(row):
    cleaned = {}
    for k, v in row.items():
        if k == "Source Link":
            # Don't normalize URLs — keep them as-is
            cleaned[k] = str(v).strip() if v else ""
        else:
            cleaned[k] = normalize(str(v)) if v is not None else ""
    return cleaned


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------
def scrape_evidence(page, evidence_id):
    url = f"https://civicdb.org/evidence/{evidence_id}/summary"
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2000)

    html = page.content()
    soup = BeautifulSoup(html, "lxml")

    row = {"evidence_id": evidence_id, "url": url}

    # ── Extract all label→value pairs from description tables ───
    pairs = {}
    source_link = ""

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])

        if len(cells) == 2:
            label = clean(cells[0].get_text(" ", strip=True))
            value = clean(cells[1].get_text(" ", strip=True))

            # ── Source Link: grab href from <a> inside Source cell ──
            if label == "Source":
                a_tag = cells[1].find("a", href=True)
                if a_tag:
                    href = a_tag["href"].strip()
                    if href.startswith("/"):
                        href = "https://civicdb.org" + href
                    source_link = href

            if label:
                pairs[label] = normalize(value)

        elif len(cells) == 4:
            label1 = clean(cells[0].get_text(" ", strip=True))
            value1 = clean(cells[1].get_text(" ", strip=True))
            label2 = clean(cells[2].get_text(" ", strip=True))
            value2 = clean(cells[3].get_text(" ", strip=True))

            # ── Source Link in 4-cell row ────────────────────────
            if label1 == "Source":
                a_tag = cells[1].find("a", href=True)
                if a_tag:
                    href = a_tag["href"].strip()
                    if href.startswith("/"):
                        href = "https://civicdb.org" + href
                    source_link = href
            if label2 == "Source":
                a_tag = cells[3].find("a", href=True)
                if a_tag:
                    href = a_tag["href"].strip()
                    if href.startswith("/"):
                        href = "https://civicdb.org" + href
                    source_link = href

            if label1:
                pairs[label1] = normalize(value1)
            if label2:
                pairs[label2] = normalize(value2)

    # ── Fallback: search anywhere in page for source <a href="/sources/..."> 
    if not source_link:
        for a_tag in soup.find_all("a", href=re.compile(r"^/sources/\d+")):
            href = a_tag["href"].strip()
            source_link = "https://civicdb.org" + href
            break

    # ── Map to our fields ────────────────────────────────────────
    row["Type"]           = pairs.get("Type", "")
    row["Direction"]      = pairs.get("Direction", "")
    row["Significance"]   = pairs.get("Significance", "")
    row["Variant Origin"] = pairs.get("Variant Origin", "")
    row["Level"]          = pairs.get("Level", "")
    row["Rating"]         = pairs.get("Rating", "")
    row["Source"]         = pairs.get("Source", "")
    row["Source Link"]    = source_link          # ← e.g. https://civicdb.org/sources/186
    row["Clinical Trial"] = pairs.get("Clinical Trial", "")
    row["Disease"]        = pairs.get("Disease", "")
    row["Therapies"]      = pairs.get("Therapies", pairs.get("Therapy", pairs.get("Drugs", "")))

    # ── Description ──────────────────────────────────────────────
    description = ""
    try:
        desc_el = page.locator(
            "cvc-evidence-description, [data-cy='evidence-description'], .evidence-description"
        )
        if desc_el.count() > 0:
            description = normalize(desc_el.first.inner_text())

        if not description:
            for p in soup.find_all(["p", "div"]):
                txt = clean(p.get_text(" ", strip=True))
                if len(txt) > 100 and txt not in pairs.values():
                    description = txt
                    break
    except Exception as e:
        print(f"  Description error: {e}")

    row["Description"] = description

    return row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    evidence_ids  = load_evidence_ids(EXCEL_FILE)
    already_done  = load_already_scraped(OUTPUT_CSV)

    if already_done:
        print(f"Resuming — {len(already_done)} already scraped, skipping them.")

    pending = [e for e in evidence_ids if e not in already_done]
    print(f"Evidence items to scrape: {len(pending)}")

    if not pending:
        print("All evidence already scraped!")
        return

    failed = []
    total  = len(pending)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        for idx, eid in enumerate(pending, 1):
            print(f"[{idx}/{total}] Scraping evidence {eid} ...")
            try:
                row = scrape_evidence(page, eid)
                row = clean_row(row)

                # ✅ Save immediately after each evidence item
                append_row_to_csv(row, OUTPUT_CSV, FIELDNAMES)

                print(f"  ✓ Saved — Type: {row.get('Type','')}  "
                      f"Source: {row.get('Source','')[:40]}  "
                      f"Source Link: {row.get('Source Link','')}")

            except Exception as e:
                print(f"  ✗ Failed for {eid}: {e}")
                failed.append(eid)

            time.sleep(1)

        browser.close()

    print(f"\nDone! Saved to {OUTPUT_CSV}")
    if failed:
        print(f"Failed IDs ({len(failed)}): {failed}")


if __name__ == "__main__":
    main()