import os
import csv
from playwright.sync_api import sync_playwright
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

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
# INPUT GENES
# ============================================================

genes = [
    "ABL1","ABCB1","ABCB2","ABCG2","ACVR1","AKT1","AKT3","ALK","AR","ARAF",
    "ARID1A","ATM","B2M","BCL2","BRAF","BRCA1","BRCA2","BTK","CASP8","CBLB",
    "CDK4","CDKN2A","CHEK2","CSF3R","CTNNB1","DDR2","DDX41","DICER1","DPYD",
    "EGFR","ERBB2","ERBB3","ERCC2","ERCC5","ERRFI1","ESR1","ETS2","EZH2",
    "FCGR2A","FCGR2B","FCGR3A","FGFR1","FGFR2","FGFR3","FLCN","FLT3",
    "FNTB","FOXL2","GADD45A","GNAQ","GNAS","GSTP1","H3-3A","HIF1A",
    "HOXB13","HRAS","IDH1","IDH2","JAK1","JAK2","KDR","KIT","KRAS",
    "MAP2K1","MAP2K7","MAPK1","MDM2","MEN1","MET","MGMT","MLH1","MSH2",
    "MSH6","MTOR","MTHFR","MYD88","MYOD1","NF2","NOTCH1","NPM1","NQO1",
    "NRAS","NTRK3","NT5C2","PAX5","PDGFRA","PIK3CA","PIK3R2","PML","POLE",
    "POLD1","PPP1R15A","PREX2","PTEN","PTPRD","RAD51D","RAC1","RAF1",
    "RB1","RET","ROS1","RUNX1","SDHB","SETBP1","SF3B1","SH2B3",
    "SLCO1B1","SMO","SRSF2","STK11","TERT","TP53","TSC1","TSC2",
    "U2AF1","UGT1A1","VHL","WEE1","XRCC1"
]

print(f"Total genes found: {len(genes)}")

# ============================================================
# SCRAPE
# ============================================================

with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

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

        writer = csv.DictWriter(outfile, fieldnames=CSV_FIELDS)
        writer.writeheader()

        missing_writer = csv.writer(missfile)
        missing_writer.writerow(["Gene", "Reason"])

        for index, gene in enumerate(genes, start=1):

            print(f"\n[{index}/{len(genes)}] Processing: {gene}")

            try:

                url = f"https://www.oncokb.org/gene/{gene}/somatic"

                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_load_state("networkidle")

                # ----------------------------
                # HTTP 404
                # ----------------------------
                if response and response.status == 404:
                    print("⚠️ 404 Not Found")

                    missing_writer.writerow([
                        gene,
                        "404 Not Found"
                    ])
                    continue

                # ----------------------------
                # Warning page
                # ----------------------------
                warning = page.locator("div.alert-warning")

                if warning.count() > 0:

                    warning_text = warning.first.inner_text().strip()

                    if "We do not have any information for this gene" in warning_text:

                        print("⚠️ No information available")

                        missing_writer.writerow([
                            gene,
                            "No information available"
                        ])

                        continue

                # ----------------------------
                # Header exists?
                # ----------------------------
                if page.locator("span.h2").count() == 0:

                    print("⚠️ Header not found")

                    missing_writer.writerow([
                        gene,
                        "Header not found"
                    ])

                    continue

                gene_type = ""

                if page.locator("h5.mt-2").count() > 0:
                    gene_type = (
                        page.locator("h5.mt-2")
                        .first
                        .inner_text()
                        .strip()
                    )

                writer.writerow({
                    "Gene": gene,      # Original input gene
                    "Gene_Type": gene_type,
                    "URL": url
                })

                print(f"✅ Saved: {gene} | {gene_type}")

            except Exception as e:

                print(f"❌ Failed: {gene}")
                print(e)

                missing_writer.writerow([
                    gene,
                    str(e)
                ])

    print("\n===================================")
    print("Finished")
    print(f"Output : {OUTPUT_CSV}")
    print(f"Missing: {MISSING_CSV}")
    print("===================================")

    input("Press Enter to close browser...")

    browser.close()