
"""
OncoKB Variant-level scraper  v3
==================================

Ovvoru Gene ku ONE TIME gene page visit panni:
  - Therapeutic tab  -> Level | Alterations | Cancer Types | Drugs | Citations
  - FDA tab          -> FDA Level of Evidence | Alteration | Cancer Type

Ovvoru Gene+Variant ku variant page visit panni:
  - Mutation Effect tile  -> Oncogenicity (+References) | Biological Effect (+References)
  - Level of Evidence tile -> Therapeutic | Diagnostic | Prognostic | FDA (+icons)

Ellam cherthu oru CSV la save pannum.

Requirements:
    pip install playwright pandas openpyxl
    playwright install chromium
"""

import os
import csv
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ============================================================
# CONFIG
# ============================================================

INPUT_FILE     = "oncokb_website/Data/Gene_oncokb_website_1240 (3).xlsx"

GENE_COL       = "Gene"
VARIANT_COL    = "Varient Name"       # excel spelling padi
CIVIC_ID_COL   = "civic_id"
GENE_FULL_COL  = "Gene full name"
GENE_TYPE_COL  = "Gene type "         # trailing space excel la irukku

HEADLESS           = False
PAGE_TIMEOUT_MS    = 30_000
TILE_TIMEOUT_MS    = 12_000
TAB_WAIT_MS        = 1_500            # FDA tab click aana piragu wait
HOVER_WAIT_MS      = 500              # tooltip hover wait

# ============================================================
# PATHS
# ============================================================

today = datetime.now().strftime("%Y-%m-%d")
os.makedirs("Data", exist_ok=True)

OUTPUT_CSV  = f"Data/oncokb_variants_{today}.csv"
MISSING_CSV = f"Data/oncokb_variants_missing_{today}.csv"

BASE_COLS = [
    "civic_id", "Gene", "Gene full name", "Gene type",
    "Varient Name", "Variant_URL", "Gene_URL",
]

# OncoKB tile fields (variant page) — fixed known columns
TILE_COLS = [
    "Oncogenicity",
    "Oncogenicity References",
    "Biological Effect",
    "Biological Effect References",
    "Therapeutic",
    "Therapeutic References",
    "Diagnostic",
    "Diagnostic References",
    "Prognostic",
    "Prognostic References",
    "FDA",
    "FDA References",
]

# Therapeutic table columns (gene page)
TX_COLS = [
    "Tx_Level", "Tx_Cancer_Types", "Tx_Drugs", "Tx_Citations",
]

# Diagnostic table columns (gene page)
DX_COLS = [
    "Dx_Level", "Dx_Cancer_Types", "Dx_Citations",
]

# Prognostic table columns (gene page)
PX_COLS = [
    "Px_Level", "Px_Cancer_Types", "Px_Citations",
]

# FDA table columns (gene page)
FDA_COLS = [
    "FDA_Level", "FDA_Cancer_Type",
]

# Final CSV column order — fixed upfront so rows saved immediately
ALL_FIELDNAMES = BASE_COLS + TILE_COLS + TX_COLS + DX_COLS + PX_COLS + FDA_COLS


# ============================================================
# URL HELPERS
# ============================================================

def gene_url(gene: str) -> str:
    return f"https://www.oncokb.org/gene/{quote(gene.strip(), safe='')}/somatic"

def variant_url(gene: str, variant: str) -> str:
    return (
        f"https://www.oncokb.org/gene/{quote(gene.strip(), safe='')}/"
        f"somatic/{quote(variant.strip(), safe='')}"
    )


# ============================================================
# CLEAR SITE DATA  (cookies + localStorage + sessionStorage)
# ============================================================

def clear_site_data(page) -> None:
    """
    Ovvoru request munnadi cookies + storage clear pannum.
    Chrome DevTools -> Application -> Clear Storage mathiri.
    """
    try:
        # 1. Cookies clear
        page.context.clear_cookies()

        # 2. localStorage + sessionStorage clear
        #    (page already oru URL la irundha mattum possible)
        if page.url.startswith("http"):
            page.evaluate(
                "() => {"
                "  try { localStorage.clear(); } catch(e) {}"
                "  try { sessionStorage.clear(); } catch(e) {}"
                "}"
            )
    except Exception:
        pass   # blank page / about:blank la storage access fail aanum — ignore


# ============================================================
# HELPER: extract level class string  -> "1" / "3A" / "R2" etc.
# ============================================================

def _level_from_icon(icon) -> str:
    cls = icon.get_attribute("class") or ""
    for part in cls.split():
        if part.startswith("level-"):
            return part.replace("level-", "")
    return ""


# ============================================================
# TOOLTIP REFERENCE URLs (hover icon -> popup -> links)
# ============================================================

def _tooltip_refs(page, icon) -> list:
    urls = []
    try:
        icon.scroll_into_view_if_needed()
        icon.hover(force=True)
        page.wait_for_timeout(HOVER_WAIT_MS)

        tooltip = page.locator(
            ".rc-tooltip:not(.rc-tooltip-hidden) .rc-tooltip-inner"
        )
        if tooltip.count() == 0:
            return urls

        links = tooltip.first.locator("a[href]")
        for k in range(links.count()):
            href = links.nth(k).get_attribute("href")
            if href and href not in urls:
                urls.append(href)

        page.mouse.move(0, 0)
        page.wait_for_timeout(150)
    except Exception:
        pass
    return urls


# ============================================================
# TILE DATA  (variant page)
# ============================================================

def scrape_tile_data(page) -> dict:
    """
    SomaticGermlineTiles alterationTileItems blocks padichu
    auto-detected headers -> values return pannum.
    Reference icons hover pannitu PMID links-um edukum.
    """
    result = {}
    containers = page.locator("div[class*='alterationTileItems']")

    for i in range(containers.count()):
        container = containers.nth(i)
        items = container.locator(":scope > div")

        for j in range(items.count()):
            item = items.nth(j)

            h4 = item.locator("h4")
            if h4.count() == 0:
                continue
            header = h4.first.inner_text().strip()
            if not header:
                continue

            val_div = item.locator(":scope > div").first

            # --- Level icons (level-1, level-R2, level-Dx2 …) ---
            level_icons = val_div.locator("i[class*='level-']")
            levels = []
            for k in range(level_icons.count()):
                lv = _level_from_icon(level_icons.nth(k))
                if lv and lv not in levels:
                    levels.append(lv)

            if levels:
                value = ", ".join(levels)
            else:
                strong = val_div.locator("strong")
                if strong.count() > 0:
                    value = strong.first.inner_text().strip()
                else:
                    value = val_div.inner_text().strip()

            if header in result and result[header]:
                if value and value not in result[header]:
                    result[header] = f"{result[header]} | {value}"
            else:
                result[header] = value

            # --- Hover reference icons ---
            ref_icons = val_div.locator(
                "i[class*='annotation-icon'], i[class*='fa-book'], "
                "i.fa-info-circle, svg"
            )
            if ref_icons.count() > 0:
                all_urls = []
                for r in range(ref_icons.count()):
                    for u in _tooltip_refs(page, ref_icons.nth(r)):
                        if u not in all_urls:
                            all_urls.append(u)
                if all_urls:
                    result[f"{header} References"] = "; ".join(all_urls)

    return result


# ============================================================
# GENE PAGE — THERAPEUTIC TABLE  (panel-Tx)
# ============================================================

def scrape_therapeutic_table(page) -> list:
    """
    Gene somatic page la Therapeutic tab (panel-Tx) open panni,
    ReactTable rows-ah scrape pannum.
    Returns list of dicts:
      Tx_Level, Tx_Alterations, Tx_Cancer_Types, Tx_Drugs
    """
    rows = []

    # Make sure Tx tab is active (it usually is by default)
    tx_tab = page.locator("#tab-Tx")
    if tx_tab.count() > 0:
        if tx_tab.get_attribute("aria-selected") != "true":
            tx_tab.click()
            page.wait_for_timeout(TAB_WAIT_MS)

    panel = page.locator("#panel-Tx")
    if panel.count() == 0:
        return rows

    # Wait for ACTUAL ROW DATA to render (not just tbody shell)
    try:
        page.wait_for_selector(
            "#panel-Tx .rt-tbody .rt-tr-group",
            state="attached",
            timeout=TILE_TIMEOUT_MS
        )
    except PWTimeout:
        return rows

    # FIX 1: scope to rt-tbody to avoid any header/hidden groups
    row_groups = panel.locator(".rt-tbody .rt-tr-group")

    for i in range(row_groups.count()):
        try:
            rg = row_groups.nth(i)

            # prevents picking up nested rt-td from expanded sub-rows
            cells = rg.locator(".rt-tr > .rt-td")
            cell_count = cells.count()

            if cell_count < 4:
                continue

            # --- Level ---
            level_icon = cells.nth(0).locator("i[class*='level-']")
            level = _level_from_icon(level_icon.first) if level_icon.count() > 0 else ""

            # --- Alterations ---
            alt_links = cells.nth(1).locator("a")
            alterations = ", ".join(
                alt_links.nth(k).inner_text().strip()
                for k in range(alt_links.count())
            ) or cells.nth(1).inner_text().strip()

            if not alterations:
                continue   # header ghost row skip pannum

            # --- Level-associated Cancer Types ---
            ct_links = cells.nth(2).locator("a")
            cancer_types = ", ".join(
                ct_links.nth(k).inner_text().strip()
                for k in range(ct_links.count())
            ) or cells.nth(2).inner_text().strip()

            # --- Drugs --- (cell index 3, plain text)
            drugs = cells.nth(3).text_content().strip()

            # --- Citations --- (cell index 4, plain number)
            # Some genes have Citations col, some don't — safe check
            citations = cells.nth(4).text_content().strip() if cell_count > 4 else ""

            rows.append({
                "Tx_Alterations" : alterations,
                "Tx_Level"       : level,
                "Tx_Cancer_Types": cancer_types,
                "Tx_Drugs"       : drugs,
                "Tx_Citations"   : citations,
            })

        except Exception as ex:
            print(f"    [Tx row {i}] skip — {ex}")
            continue

    return rows


# ============================================================
# GENE PAGE — FDA TABLE  (panel-FDA)
# ============================================================

def scrape_fda_table(page) -> list:
    """
    FDA-Recognized Content tab click panni scrape pannum.
    Returns list of dicts:
      FDA_Alteration, FDA_Level, FDA_Cancer_Type
    """
    rows = []

    fda_tab = page.locator("#tab-FDA")
    if fda_tab.count() == 0:
        return rows

    fda_tab.click()

    # Wait for panel to become active
    try:
        page.wait_for_selector(
            "#panel-FDA[aria-hidden='false']",
            timeout=TAB_WAIT_MS * 2
        )
    except PWTimeout:
        return rows

    panel = page.locator("#panel-FDA")
    if panel.count() == 0:
        return rows

    # state="visible" — hidden panel rows skip pannum
    try:
        page.wait_for_selector(
            "#panel-FDA .rt-tbody .rt-tr-group",
            state="visible",
            timeout=TILE_TIMEOUT_MS
        )
    except PWTimeout:
        return rows

    # FIX: scope to rt-tbody, use direct-child .rt-tr > .rt-td
    row_groups = panel.locator(".rt-tbody .rt-tr-group")

    for i in range(row_groups.count()):
        try:
            rg    = row_groups.nth(i)
            cells = rg.locator(".rt-tr > .rt-td")
            if cells.count() < 3:
                continue

            # --- FDA Level of Evidence  (fa-stack > strong number) ---
            strong = cells.nth(0).locator("strong")
            fda_level = (
                strong.first.inner_text().strip()
                if strong.count() > 0
                else cells.nth(0).text_content().strip()
            )

            # --- Alteration ---
            alt_link = cells.nth(1).locator("a")
            alteration = (
                alt_link.first.inner_text().strip()
                if alt_link.count() > 0
                else cells.nth(1).text_content().strip()
            )

            if not alteration:
                continue

            # --- Cancer Type ---
            ct_links = cells.nth(2).locator("a")
            cancer_type = ", ".join(
                ct_links.nth(k).inner_text().strip()
                for k in range(ct_links.count())
            ) or cells.nth(2).text_content().strip()

            rows.append({
                "FDA_Alteration" : alteration,
                "FDA_Level"      : fda_level,
                "FDA_Cancer_Type": cancer_type,
            })

        except Exception as ex:
            print(f"    [FDA row {i}] skip — {ex}")
            continue

    return rows


# ============================================================
# GENE PAGE — DIAGNOSTIC TABLE  (panel-Dx)
# ============================================================

def scrape_diagnostic_table(page) -> list:
    """
    Diagnostic tab (panel-Dx) click panni scrape pannum.
    Columns: Level | Alterations | Level-associated cancer types | Citations
    Gene la Diagnostic tab illana (BRAF mathiri genes mattum varum),
    empty list return pannum.
    """
    rows = []

    dx_tab = page.locator("#tab-Dx")
    if dx_tab.count() == 0:
        return rows   # this gene has no Diagnostic tab

    if dx_tab.get_attribute("aria-selected") != "true":
        dx_tab.click()

    # Wait for panel to become active
    try:
        page.wait_for_selector(
            "#panel-Dx[aria-hidden='false']",
            timeout=TAB_WAIT_MS * 2
        )
    except PWTimeout:
        return rows

    panel = page.locator("#panel-Dx")
    if panel.count() == 0:
        return rows

    # state="visible" — hidden panel rows skip pannum
    try:
        page.wait_for_selector(
            "#panel-Dx .rt-tbody .rt-tr-group",
            state="visible",
            timeout=TILE_TIMEOUT_MS
        )
    except PWTimeout:
        return rows

    row_groups = panel.locator(".rt-tbody .rt-tr-group")

    for i in range(row_groups.count()):
        try:
            rg    = row_groups.nth(i)
            cells = rg.locator(".rt-tr > .rt-td")
            if cells.count() < 3:
                continue

            # --- Level  (level-Dx1, level-Dx2, level-Dx3 …) ---
            level_icon = cells.nth(0).locator("i[class*='level-']")
            level = _level_from_icon(level_icon.first) if level_icon.count() > 0 else ""

            # --- Alterations ---
            alt_links = cells.nth(1).locator("a")
            alterations = ", ".join(
                alt_links.nth(k).inner_text().strip()
                for k in range(alt_links.count())
            ) or cells.nth(1).text_content().strip()

            if not alterations:
                continue

            # --- Level-associated cancer types ---
            ct_links = cells.nth(2).locator("a")
            cancer_types = ", ".join(
                ct_links.nth(k).inner_text().strip()
                for k in range(ct_links.count())
            ) or cells.nth(2).text_content().strip()

            # --- Citations (plain number span, col 3) ---
            citations = cells.nth(3).text_content().strip() if cells.count() > 3 else ""

            rows.append({
                "Dx_Alterations" : alterations,
                "Dx_Level"       : level,
                "Dx_Cancer_Types": cancer_types,
                "Dx_Citations"   : citations,
            })

        except Exception as ex:
            print(f"    [Dx row {i}] skip — {ex}")
            continue

    return rows

# ============================================================
# GENE PAGE — PROGNOSTIC TABLE  (panel-Px)
# ============================================================

def scrape_prognostic_table(page) -> list:
    """
    Prognostic tab (panel-Px) click panni scrape pannum.
    Columns: Level | Alterations | Level-associated cancer types | Citations
    Gene la Prognostic tab illana, empty list return pannum.
    """
    rows = []

    px_tab = page.locator("#tab-Px")
    if px_tab.count() == 0:
        return rows   # this gene has no Prognostic tab

    if px_tab.get_attribute("aria-selected") != "true":
        px_tab.click()
        page.wait_for_timeout(TAB_WAIT_MS)   # Dx/FDA mathiri same wait

    panel = page.locator("#panel-Px")
    if panel.count() == 0:
        return rows

    # Dx mathiri same pattern: state="attached"
    try:
        page.wait_for_selector(
            "#panel-Px .rt-tbody .rt-tr-group",
            state="attached",
            timeout=TILE_TIMEOUT_MS
        )
    except PWTimeout:
        return rows

    row_groups = panel.locator(".rt-tbody .rt-tr-group")

    for i in range(row_groups.count()):
        try:
            rg    = row_groups.nth(i)
            cells = rg.locator(".rt-tr > .rt-td")
            cell_count = cells.count()
            if cell_count < 3:
                continue

            # --- Level (level-Px1, level-Px2, level-Px3 …) ---
            level_icon = cells.nth(0).locator("i[class*='level-']")
            level = _level_from_icon(level_icon.first) if level_icon.count() > 0 else ""

            # --- Alterations ---
            alt_links = cells.nth(1).locator("a")
            alterations = ", ".join(
                alt_links.nth(k).inner_text().strip()
                for k in range(alt_links.count())
            ) or cells.nth(1).text_content().strip()

            if not alterations:
                continue

            # --- Level-associated cancer types ---
            ct_links = cells.nth(2).locator("a")
            cancer_types = ", ".join(
                ct_links.nth(k).inner_text().strip()
                for k in range(ct_links.count())
            ) or cells.nth(2).text_content().strip()

            # --- Citations (col 3) ---
            citations = cells.nth(3).text_content().strip() if cell_count > 3 else ""

            rows.append({
                "Px_Alterations" : alterations,
                "Px_Level"       : level,
                "Px_Cancer_Types": cancer_types,
                "Px_Citations"   : citations,
            })

        except Exception as ex:
            print(f"    [Px row {i}] skip — {ex}")
            continue

    return rows


# ============================================================
# MATCH + AGGREGATE helpers
# ============================================================

def _match_tx(tx_rows: list, variant: str) -> dict:
    """Therapeutic rows la variant match pannitu aggregate."""
    matched = [
        r for r in tx_rows
        if variant in [a.strip() for a in r["Tx_Alterations"].split(",")]
        or r["Tx_Alterations"].strip() == "Oncogenic Mutations"
    ]
    if not matched:
        return {c: "" for c in TX_COLS}
    return {
        "Tx_Level"       : " | ".join(r["Tx_Level"]        for r in matched if r["Tx_Level"]),
        "Tx_Cancer_Types": " | ".join(r["Tx_Cancer_Types"] for r in matched if r["Tx_Cancer_Types"]),
        "Tx_Drugs"       : " | ".join(r["Tx_Drugs"]        for r in matched if r["Tx_Drugs"]),
        "Tx_Citations"   : " | ".join(r["Tx_Citations"]    for r in matched if r["Tx_Citations"]),
    }


def _match_fda(fda_rows: list, variant: str) -> dict:
    """
    FDA table rows la variant match pannitu aggregate pannum.
    Returns FDA_COLS dict.
    """
    matched = [
        r for r in fda_rows
        if r["FDA_Alteration"].strip() == variant
    ]
    if not matched:
        return {c: "" for c in FDA_COLS}

    return {
        "FDA_Level"      : " | ".join(r["FDA_Level"]       for r in matched if r["FDA_Level"]),
        "FDA_Cancer_Type": " | ".join(r["FDA_Cancer_Type"] for r in matched if r["FDA_Cancer_Type"]),
    }


def _match_dx(dx_rows: list, variant: str) -> dict:
    """
    Diagnostic table rows la variant match pannitu aggregate pannum.
    Alterations cell la comma-separated multiple variants irukum
    (e.g. "Oncogenic Mutations" or specific like "V600E").
    Returns DX_COLS dict.
    """
    matched = [
        r for r in dx_rows
        if variant in [a.strip() for a in r["Dx_Alterations"].split(",")]
        or r["Dx_Alterations"].strip() == "Oncogenic Mutations"
    ]
    if not matched:
        return {c: "" for c in DX_COLS}

    return {
        "Dx_Level"       : " | ".join(r["Dx_Level"]        for r in matched if r["Dx_Level"]),
        "Dx_Cancer_Types": " | ".join(r["Dx_Cancer_Types"] for r in matched if r["Dx_Cancer_Types"]),
        "Dx_Citations"   : " | ".join(r["Dx_Citations"]    for r in matched if r["Dx_Citations"]),
    }


def _match_px(px_rows: list, variant: str) -> dict:
    """Prognostic rows la variant match pannitu aggregate."""
    matched = [
        r for r in px_rows
        if variant in [a.strip() for a in r["Px_Alterations"].split(",")]
        or r["Px_Alterations"].strip() == "Oncogenic Mutations"
    ]
    if not matched:
        return {c: "" for c in PX_COLS}
    return {
        "Px_Level"       : " | ".join(r["Px_Level"]        for r in matched if r["Px_Level"]),
        "Px_Cancer_Types": " | ".join(r["Px_Cancer_Types"] for r in matched if r["Px_Cancer_Types"]),
        "Px_Citations"   : " | ".join(r["Px_Citations"]    for r in matched if r["Px_Citations"]),
    }

def main():
    df = pd.read_excel(INPUT_FILE)
    df = df.dropna(subset=[GENE_COL, VARIANT_COL])

    work = df[[CIVIC_ID_COL, GENE_COL, GENE_FULL_COL, GENE_TYPE_COL, VARIANT_COL]].copy()
    work.columns = ["civic_id", "Gene", "Gene full name", "Gene type", "Varient Name"]

    print(f"Total rows   : {len(work)}")
    print(f"Unique genes : {work['Gene'].nunique()}")

    # ── Resume support ────────────────────────────────────────
    # Already-saved civic_ids skip pannidum (script crash aana
    # piragu restart pannalum, mela irunthu continue aagum)
    done_ids = set()
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                cid = r.get("civic_id", "").strip()
                vname = r.get("Varient Name", "").strip()
                if cid:
                    done_ids.add((cid, vname))
        print(f"Resuming     : {len(done_ids)} rows already done, skipping them")

    # ── Open CSV files BEFORE loop ────────────────────────────
    # Header oru thadavai mattum — file pudhutha create aana
    # (done_ids illana), resume aana append mode la open pannum
    out_mode  = "a" if done_ids else "w"
    miss_mode = "a" if os.path.exists(MISSING_CSV) else "w"

    out_file  = open(OUTPUT_CSV,  out_mode,  newline="", encoding="utf-8")
    miss_file = open(MISSING_CSV, miss_mode, newline="", encoding="utf-8")

    miss_fields = ALL_FIELDNAMES + ["Reason"]

    out_writer  = csv.DictWriter(out_file,  fieldnames=ALL_FIELDNAMES,
                                 extrasaction="ignore")
    miss_writer = csv.DictWriter(miss_file, fieldnames=miss_fields,
                                 extrasaction="ignore")

    # Header — fresh file la mattum write pannum
    if not done_ids:
        out_writer.writeheader()
    if miss_mode == "w":
        miss_writer.writeheader()

    saved_count  = len(done_ids)
    missed_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page    = browser.new_page()

        gene_tx_cache  = {}
        gene_dx_cache  = {}
        gene_px_cache  = {}
        gene_fda_cache = {}
        total = len(work)

        for idx, row in work.iterrows():
            gene    = str(row["Gene"]).strip()
            variant = str(row["Varient Name"]).strip()
            cid     = str(row["civic_id"]).strip()
            g_url   = gene_url(gene)
            v_url   = variant_url(gene, variant)

            # ── Skip already done rows ────────────────────────
            if (cid, variant) in done_ids:
                print(f"[{idx+1}/{total}] SKIP {gene}/{variant} (already saved)")
                continue

            print(f"\n[{idx+1}/{total}] {gene} / {variant}")

            base = {
                "civic_id"      : cid,
                "Gene"          : gene,
                "Gene full name": row["Gene full name"],
                "Gene type"     : row["Gene type"],
                "Varient Name"  : variant,
                "Variant_URL"   : v_url,
                "Gene_URL"      : g_url,
            }

            # ── 1. Gene page (cached per gene) ───────────────
            if gene not in gene_tx_cache:
                print(f"  [Gene page] {g_url}")
                try:
                    clear_site_data(page)
                    resp = page.goto(g_url, wait_until="networkidle",
                                     timeout=PAGE_TIMEOUT_MS)
                    if resp and resp.status == 404:
                        gene_tx_cache[gene]  = []
                        gene_dx_cache[gene]  = []
                        gene_px_cache[gene]  = []
                        gene_fda_cache[gene] = []
                        print("  Gene page -> 404")
                    else:
                        # Tab click order: Tx (default) → Dx → Px → FDA
                        gene_tx_cache[gene]  = scrape_therapeutic_table(page)
                        gene_dx_cache[gene]  = scrape_diagnostic_table(page)
                        gene_px_cache[gene]  = scrape_prognostic_table(page)
                        gene_fda_cache[gene] = scrape_fda_table(page)
                        print(
                            f"  Tx:{len(gene_tx_cache[gene])} "
                            f"Dx:{len(gene_dx_cache[gene])} "
                            f"Px:{len(gene_px_cache[gene])} "
                            f"FDA:{len(gene_fda_cache[gene])}"
                        )
                except Exception as e:
                    gene_tx_cache[gene]  = []
                    gene_dx_cache[gene]  = []
                    gene_px_cache[gene]  = []
                    gene_fda_cache[gene] = []
                    print(f"  Gene page failed: {e}")

            tx_data  = _match_tx(gene_tx_cache[gene], variant)
            dx_data  = _match_dx(gene_dx_cache[gene], variant)
            px_data  = _match_px(gene_px_cache[gene], variant)
            fda_data = _match_fda(gene_fda_cache[gene], variant)

            # ── 2. Variant page -> tile data ──────────────────
            print(f"  [Variant page] {v_url}")
            try:
                clear_site_data(page)
                resp = page.goto(v_url, wait_until="networkidle",
                                 timeout=PAGE_TIMEOUT_MS)

                if resp and resp.status == 404:
                    record = {**base, **tx_data, **dx_data, **px_data, **fda_data, "Reason": "Variant 404"}
                    miss_writer.writerow(record)
                    miss_file.flush()
                    missed_count += 1
                    print("  -> 404 (saved to missing)")
                    continue

                try:
                    page.wait_for_selector(
                        "div[class*='alterationTileItems']",
                        timeout=TILE_TIMEOUT_MS
                    )
                except PWTimeout:
                    record = {**base, **tx_data, **dx_data, **px_data, **fda_data}
                    out_writer.writerow(record)
                    out_file.flush()
                    saved_count += 1
                    print(f"  -> Saved (no tile, gene data only) [{saved_count}]")
                    continue

                tile_data = scrape_tile_data(page)
                record    = {**base, **tile_data, **tx_data, **dx_data, **px_data, **fda_data}

                out_writer.writerow(record)
                out_file.flush()
                saved_count += 1
                print(f"  -> Saved [{saved_count}] | tile: {list(tile_data.keys())}")

            except Exception as e:
                record = {**base, **tx_data, **dx_data, **px_data, **fda_data, "Reason": str(e)}
                miss_writer.writerow(record)
                miss_file.flush()
                missed_count += 1
                print(f"  -> Failed (saved to missing): {e}")

        browser.close()

    out_file.close()
    miss_file.close()

    print("\n===================================")
    print(f"Saved          : {saved_count}")
    print(f"Missing/Failed : {missed_count}")
    print(f"Output CSV     : {OUTPUT_CSV}")
    print(f"Missing CSV    : {MISSING_CSV}")
    print("===================================\n")


if __name__ == "__main__":
    main()