import os
import csv
import pandas as pd
from playwright.sync_api import sync_playwright
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = "Data/gene_panel.xlsx"
SYMBOL_COL = "Hugo Symbol"

today = datetime.now().strftime("%Y-%m-%d")

os.makedirs("Data", exist_ok=True)

OUTPUT_CSV = f"Data/oncokb_genes_{today}.csv"
MISSING_CSV = f"Data/missing_genes_{today}.csv"

CSV_FIELDS = [
    "Gene",
    "Gene_Type",
    "URL"
]

# ============================================================
# READ INPUT FILE
# ============================================================

df = pd.read_excel(INPUT_FILE)

genes = (
    df[SYMBOL_COL]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)

print(f"Total genes found: {len(genes)}")

# ============================================================
# SCRAPE ONCOKB
# ============================================================

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )

    page = browser.new_page()

    with open(
        OUTPUT_CSV,
        "w",
        newline="",
        encoding="utf-8"
    ) as outfile, open(
        MISSING_CSV,
        "w",
        newline="",
        encoding="utf-8"
    ) as missfile:

        writer = csv.DictWriter(
            outfile,
            fieldnames=CSV_FIELDS
        )
        writer.writeheader()

        missing_writer = csv.writer(missfile)
        missing_writer.writerow([
            "Gene",
            "Reason"
        ])

        for index, gene in enumerate(genes, start=1):

            print(f"\n[{index}/{len(genes)}] Processing: {gene}")

            try:

                url = f"https://www.oncokb.org/gene/{gene}/somatic"

                response = page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=30000
                )

                # Handle 404 pages
                if response and response.status == 404:
                    missing_writer.writerow([
                        gene,
                        "404 Not Found"
                    ])
                    print(f" {gene} -> 404 Not Found")
                    continue

                # Wait for gene header
                page.wait_for_selector(
                    "span.h2",
                    timeout=10000
                )

                # Gene Name
                gene_name = (
                    page.locator("span.h2")
                    .first
                    .inner_text()
                    .strip()
                )

                # Gene Type
                gene_type = (
                    page.locator("h5.mt-2")
                    .first
                    .inner_text()
                    .strip()
                )

                writer.writerow({
                    "Gene": gene_name,
                    "Gene_Type": gene_type,
                    "URL": url
                })

                print(
                    f" Saved: "
                    f"{gene_name} | {gene_type}"
                )

            except Exception as e:

                missing_writer.writerow([
                    gene,
                    str(e)
                ])

                print(
                    f" Failed: {gene}\n"
                    f"Reason: {e}"
                )

    print("\n===================================")
    print(f"Output File : {OUTPUT_CSV}")
    print(f"Missing File: {MISSING_CSV}")
    print("===================================\n")

    input("Press Enter to close browser...")

    browser.close()