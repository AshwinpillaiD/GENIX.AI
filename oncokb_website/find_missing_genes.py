import pandas as pd

# Input files
INPUT_EXCEL = "Data/gene_panel.xlsx"
SCRAPED_CSV = "Data/oncokb_genes_2026-06-22.csv"

# Column names
INPUT_COL = "Hugo Symbol"
SCRAPED_COL = "Gene"

# Read files
input_df = pd.read_excel(INPUT_EXCEL)
scraped_df = pd.read_csv(SCRAPED_CSV)

# Normalize values
input_genes = (
    input_df[INPUT_COL]
    .dropna()
    .astype(str)
    .str.strip()
    .str.upper()
)

scraped_genes = (
    scraped_df[SCRAPED_COL]
    .dropna()
    .astype(str)
    .str.strip()
    .str.upper()
)

missing_genes = sorted(
    set(input_genes) - set(scraped_genes)
)

missing_df = pd.DataFrame(
    {"Missing_Gene": missing_genes}
)

missing_df.to_csv(
    "Data/missing_genes.csv",
    index=False
)

print(f"Total Input Genes    : {len(set(input_genes))}")
print(f"Total Scraped Genes  : {len(set(scraped_genes))}")
print(f"Missing Genes        : {len(missing_genes)}")
print("Saved -> Data/missing_genes.csv")