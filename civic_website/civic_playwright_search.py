import os
import csv
import pandas as pd
from playwright.sync_api import sync_playwright
from datetime import datetime
INPUT_FILE   = "Data/25_genes.xlsx"
SYMBOL_COL   = "Hugo Symbol"

today = datetime.now().strftime(
    "%Y-%m-%d"
)

os.makedirs("civic_website/Data", exist_ok=True)
OUTPUT_CSV   = f"Data/variants_output{today}.csv"
MISSING_CSV  = f"Data/missing_genes{today}.csv"
# OUTPUT_XLSX  = "variants_output.xlsx"
# MISSING_XLSX = "missing_genes.xlsx"

CSV_FIELDS = [
    "URL",
    "Gene",
    "Gene Full Name",
    "Variant Name",
    "Variant Type",
    "MANE Select Transcript",
    "My Variant Info ID",
    "ClinVar ID (MyVariant)",
    "dbSNP RSID",
    "COSMIC ID",
    "SNPEff Effect",
    "SNPEff Impact",
    "ACMG/AMP BP4",
    "ACMG/AMP PP3",
    "Diseases",
    "Therapies",
]

def clean(value):
    if value is None:
        return ""
    v = str(value).strip()
    if v in ("--", "-", "null", "None", "N/A", "n/a"):
        return ""
    return v


# ── ONLY ONE extract_variant_data ────────────────────────────────
def extract_variant_data(page, variant_url, csv_writer, gene_full_name=""):
    print(f"\n  Extracting: {variant_url}")
    page.goto(variant_url, wait_until="networkidle")
    page.wait_for_timeout(3000)

    data = {field: "" for field in CSV_FIELDS}
    data["URL"]            = variant_url
    data["Gene Full Name"] = gene_full_name

    # ── Page validity check ──────────────────────────────────────
    try:
        page.wait_for_selector("cvc-feature-tag", timeout=8000)
    except:
        print(f"  Invalid page — saving empty row: {variant_url}")
        csv_writer.writerow(data)
        return data

    # ── Basic Info ───────────────────────────────────────────────
    try:
        data["Gene"] = clean(page.locator("cvc-feature-tag nz-tag").first.inner_text())
    except:
        pass

    try:
        variant_name = page.locator("#relations-summary span[nz-typography] strong").first.inner_text()
        data["Variant Name"] = clean(variant_name)
        print(f"  Variant Name: {data['Variant Name']}")
    except:
        data["Variant Name"] = ""
        print(f"  Variant Name: not found")

    try:
        data["Variant Type"] = clean(page.locator("cvc-variant-type-tag nz-tag").first.inner_text())
    except:
        pass

    try:
        mane_row = page.locator("tr.ant-descriptions-row").filter(has_text="MANE Select Transcript")
        data["MANE Select Transcript"] = clean(
            mane_row.locator("td.ant-descriptions-item-content nz-tag").first.inner_text()
        )
    except:
        pass

    # ── My Variant Info Tab ──────────────────────────────────────
    try:
        mv_tab = page.locator("button[role='tab']").filter(has_text="My Variant Info")
        mv_tab.click()
        page.wait_for_timeout(2000)
    except:
        pass

    try:
        overview_tab = page.locator("button[role='tab']").filter(has_text="Overview")
        overview_tab.first.click()
        page.wait_for_timeout(1500)
    except:
        pass

    try:
        mv_table = page.locator("cvc-my-variant-info nz-descriptions").first
        rows = mv_table.locator("tr.ant-descriptions-row")
        for i in range(rows.count()):
            row    = rows.nth(i)
            labels = row.locator("td.ant-descriptions-item-label")
            values = row.locator("td.ant-descriptions-item-content")
            for j in range(labels.count()):
                try:
                    label = labels.nth(j).inner_text().strip().replace("\xa0", " ")
                    value = clean(values.nth(j).inner_text())
                    if "My Variant Info ID" in label:
                        data["My Variant Info ID"] = value
                    elif "ClinVar ID" in label:
                        data["ClinVar ID (MyVariant)"] = value
                    elif "dbSNP" in label:
                        data["dbSNP RSID"] = value
                    elif "COSMIC" in label:
                        data["COSMIC ID"] = value
                    elif "SNPEff Effect" in label:
                        data["SNPEff Effect"] = value
                    elif "SNPEff Impact" in label:
                        data["SNPEff Impact"] = value
                except:
                    pass
    except Exception as e:
        print(f"  MyVariant error: {e}")

    # ── OpenCRAVAT ACMG/AMP Tab ──────────────────────────────────
    try:
        acmg_tab = page.locator("button[role='tab']").filter(has_text="OpenCRAVAT ACMG/AMP Classifications")
        acmg_tab.click()
        page.wait_for_timeout(1000)
        page.wait_for_selector("cvc-open-cravat-annotations", timeout=1000)

        acmg_component = page.locator(
            "cvc-open-cravat-annotations nz-descriptions .ant-descriptions-view table tbody"
        )
        rows = acmg_component.locator("tr.ant-descriptions-row")
        current_label = None
        for i in range(rows.count()):
            row = rows.nth(i)
            label_cells = row.locator("td.ant-descriptions-item-label")
            if label_cells.count() > 0:
                current_label = label_cells.first.inner_text().strip()
            value_cells = row.locator("td.ant-descriptions-item-content")
            if value_cells.count() > 0 and current_label:
                divs   = value_cells.first.locator("div[nz-tooltip]")
                values = []
                for d in range(divs.count()):
                    txt = clean(divs.nth(d).inner_text())
                    if txt:
                        values.append(txt)
                combined = ", ".join(values)
                if "BP4" in current_label:
                    data["ACMG/AMP BP4"] = combined
                elif "PP3" in current_label:
                    data["ACMG/AMP PP3"] = combined
                current_label = None
    except Exception as e:
        print(f"  ACMG error: {e}")

    # ── Diseases & Therapies ─────────────────────────────────────
    try:
        diseases     = []
        disease_urls = []
        therapies    = []
        therapy_urls = []

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

        all_disease_tags = page.locator("tbody.ant-table-tbody tr.data-row cvc-disease-tag a")
        for d in range(all_disease_tags.count()):
            tag  = all_disease_tags.nth(d)
            name = clean(tag.inner_text())
            href = tag.get_attribute("href") or ""
            if href.startswith("/"):
                href = "https://civicdb.org" + href
            if name and href not in disease_urls:
                diseases.append(name)
                disease_urls.append(href)

        all_therapy_tags = page.locator("tbody.ant-table-tbody tr.data-row cvc-therapy-tag a")
        for t in range(all_therapy_tags.count()):
            tag  = all_therapy_tags.nth(t)
            name = clean(tag.inner_text())
            href = tag.get_attribute("href") or ""
            if href.startswith("/"):
                href = "https://civicdb.org" + href
            if name and href not in therapy_urls:
                therapies.append(name)
                therapy_urls.append(href)

        overflow_tags  = page.locator("tbody.ant-table-tbody tr.data-row nz-tag.overflow-tag")
        overflow_count = overflow_tags.count()
        print(f"  Overflow tags: {overflow_count}")

        for o in range(overflow_count):
            try:
                overflow = page.locator("tbody.ant-table-tbody tr.data-row nz-tag.overflow-tag").nth(o)
                overflow.click()
                page.wait_for_timeout(1500)

                popover_d = page.locator(".ant-popover-inner cvc-disease-tag a")
                for d in range(popover_d.count()):
                    tag  = popover_d.nth(d)
                    name = clean(tag.inner_text())
                    href = tag.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = "https://civicdb.org" + href
                    if name and href not in disease_urls:
                        diseases.append(name)
                        disease_urls.append(href)

                popover_t = page.locator(".ant-popover-inner cvc-therapy-tag a")
                for t in range(popover_t.count()):
                    tag  = popover_t.nth(t)
                    name = clean(tag.inner_text())
                    href = tag.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = "https://civicdb.org" + href
                    if name and href not in therapy_urls:
                        therapies.append(name)
                        therapy_urls.append(href)

                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

            except Exception as oe:
                print(f"  Overflow error: {oe}")
                page.keyboard.press("Escape")

        data["Diseases"]  = " , ".join(diseases)
        data["Therapies"] = " , ".join(therapies)

        print(f"  Diseases  ({len(diseases)}): {data['Diseases']}")
        print(f"  Therapies ({len(therapies)}): {data['Therapies']}")

    except Exception as e:
        print(f"  Diseases/Therapies error: {e}")

    # ── Print + Save ─────────────────────────────────────────────
    print("  --- Extracted ---")
    for k, v in data.items():
        print(f"    {k}: {v}")

    csv_writer.writerow(data)
    return data


def search_gene_exact(page, gene):
    try:
        page.goto("https://civicdb.org", wait_until="networkidle")
        page.wait_for_timeout(2000)

        search_box = page.locator("input.ant-select-selection-search-input")
        search_box.wait_for(timeout=15000)
        search_box.click()
        search_box.fill("")
        page.wait_for_timeout(500)
        search_box.fill(gene)
        page.wait_for_timeout(3000)

        options = page.locator(".ant-select-item-option")
        matched = False

        for i in range(options.count()):
            opt      = options.nth(i)
            opt_text = opt.inner_text().strip()
            if opt_text.lower() == gene.lower():
                opt.click()
                matched = True
                print(f"  Exact match found: '{opt_text}'")
                break

        if not matched:
            print(f"  No exact match for '{gene}' in dropdown")
            pd.DataFrame(
                [{
                    "Gene": gene,
                    # "Reason": "No exact match"
                }]
            ).to_csv(
                "missing_genes.csv",
                mode="a",
                header=not os.path.exists(
                    "missing_genes.csv"
                ),
                index=False
            )
            page.keyboard.press("Escape")
            return False

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        return True

    except Exception as e:
        print(f"  Search error for '{gene}': {e}")
        return False


def get_variant_urls_for_gene(page, gene):
    print(f"\n{'='*50}")
    print(f"Gene: {gene}")
    print(f"{'='*50}")

    found = search_gene_exact(page, gene)
    if not found:
        return set(), False, ""

    gene_full_name = ""
    try:
        subtitle = page.locator("nz-page-header-subtitle")
        subtitle.wait_for(timeout=5000)
        gene_full_name = clean(subtitle.inner_text())
        print(f"  Full name: {gene_full_name}")
    except Exception as e:
        print(f"  Full name not found: {e}")

    try:
        page.get_by_role("tab", name="Variants").click()
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"  Variants tab error: {e}")
        return set(), True, gene_full_name

    # Load More Loop
    while True:
        before = page.locator('a[href*="/variants/"]').count()
        try:
            buttons = page.locator("#load-more-btn button")
            clicked = False
            for i in range(buttons.count()):
                btn = buttons.nth(i)
                try:
                    if btn.is_visible():
                        btn.click(force=True)
                        clicked = True
                        page.wait_for_timeout(5000)
                        break
                except:
                    pass
            if not clicked:
                break
            after = page.locator('a[href*="/variants/"]').count()
            if after <= before:
                break
        except:
            break

    # Collect URLs
    variant_urls = set()
    links = page.locator('a[href*="/variants/"]')
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href")
        if not href:
            continue
        if any(x in href for x in ("/comments", "/flags", "/revisions")):
            continue
        if href.startswith("/"):
            href = "https://civicdb.org" + href
        variant_urls.add(href)

    print(f"  Found {len(variant_urls)} variants for '{gene}'")
    return variant_urls, True, gene_full_name


# ── MAIN ─────────────────────────────────────────────────────────
if not os.path.exists(INPUT_FILE):
    print(f"'{INPUT_FILE}' not found!")
    exit()

df_input = pd.read_excel(INPUT_FILE)
if SYMBOL_COL not in df_input.columns:
    print(f"Column '{SYMBOL_COL}' not found!")
    print(f"Available: {df_input.columns.tolist()}")
    exit()

symbols        = df_input[SYMBOL_COL].dropna().astype(str).str.strip().unique().tolist()
missing_genes  = []
found_genes    = []
total_variants = 0

print(f"{len(symbols)} genes loaded from Excel")
print(f"Genes: {symbols}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page    = browser.new_page()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        csv_writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDS)
        csv_writer.writeheader()
        print(f"\nCSV created: {OUTPUT_CSV}")

        for gene_idx, gene in enumerate(symbols, 1):
            print(f"\n[Gene {gene_idx}/{len(symbols)}] → {gene}")

            variant_urls, was_found, gene_full_name = get_variant_urls_for_gene(page, gene)

            if not was_found:
                missing_genes.append(gene)
                print(f"  '{gene}' NOT found in CIViC")
                continue

            if not variant_urls:
                print(f"  '{gene}' found but no variants")
                found_genes.append(gene)
                continue

            found_genes.append(gene)

            for var_idx, variant_url in enumerate(sorted(variant_urls), 1):
                # print(f"\n  [Variant {var_idx}/{len(variant_urls)}]")
                try:
                    extract_variant_data(page, variant_url, csv_writer, gene_full_name)
                    total_variants += 1
                except Exception as e:
                    print(f"  Error: {e}")
                csvfile.flush()

    print(f"\nTotal variants extracted: {total_variants}")

    # ── Save Missing Genes ────────────────────────────────────────
    if missing_genes:
        print(f"\n{len(missing_genes)} genes NOT found in CIViC:")
        for g in missing_genes:
            print(f"  - {g}")

        with open(MISSING_CSV, "w", newline="", encoding="utf-8") as mf:
            writer = csv.writer(mf)
            writer.writerow(["Gene", "Status"])
            for g in missing_genes:
                writer.writerow([g, "Not found in CIViC"])

        df_missing = pd.DataFrame({
            "Gene":   missing_genes,
            "Status": ["Not found in CIViC"] * len(missing_genes)
        })
        # with pd.ExcelWriter(MISSING_XLSX, engine="openpyxl") as writer:
        #     df_missing.to_excel(writer, index=False, sheet_name="Missing Genes")
        #     ws = writer.sheets["Missing Genes"]
        #     from openpyxl.styles import PatternFill, Font
        #     fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
        #     font = Font(color="FFFFFF", bold=True)
        #     for cell in ws[1]:
        #         cell.fill = fill
        #         cell.font = font
        #     ws.column_dimensions["A"].width = 20
        #     ws.column_dimensions["B"].width = 30
        # print(f"Missing genes saved: {MISSING_XLSX}")
    else:
        print(f"\nAll genes found in CIViC!")

    # ── Final Summary ─────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"FINAL SUMMARY")
    print(f"{'='*50}")
    print(f"  Total genes in Excel : {len(symbols)}")
    print(f"  Found in CIViC       : {len(found_genes)}")
    print(f"  NOT found in CIViC   : {len(missing_genes)}")
    print(f"  Total variants saved : {total_variants}")
    # print(f"  Output CSV           : {OUTPUT_CSV}")
    # print(f"  Missing genes file   : {MISSING_XLSX}")
    print(f"{'='*50}")

    input("\nPress Enter to close...")
    browser.close()