import pandas as pd

# Input files
GENE_FILE = "Data/gene_panel.xlsx"
DATA_FILE = "Data/oncokb_genes.csv"

# Read files
gene_df = pd.read_excel(GENE_FILE)
data_df = pd.read_csv(DATA_FILE)

# Standardize gene names
gene_df["Hugo Symbol"] = (
    gene_df["Hugo Symbol"]
    .astype(str)
    .str.strip()
    .str.upper()
)

data_df["Gene"] = (
    data_df["Gene"]
    .astype(str)
    .str.strip()
    .str.upper()
)

# Create lookup dictionary
gene_type_map = dict(
    zip(
        data_df["Gene"],
        data_df["Gene_Type"]
    )
)

# Create/Update GeneType column
gene_df["GeneType"] = (
    gene_df["Hugo Symbol"]
    .map(gene_type_map)
    .fillna("")
)

# Save back to the SAME Excel file
gene_df.to_excel(
    GENE_FILE,
    index=False
)

print("GeneType column updated successfully.")