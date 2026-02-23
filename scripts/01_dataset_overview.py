import duckdb

PARQUET_PATH = "../data/raw/project_a_samples.parquet"
OUTPUT_PATH  = "../analysis/general/dataset_overview.csv"


def main():
    """
    Purpose:
        Produce a single at-a-glance summary of the raw dataset before any analysis.

    What it measures:
        For each column in the parquet file:
            - which "side" it belongs to (base or alt)
            - total rows
            - how many rows have a non-null, non-empty value (present_count)
            - coverage % (present_count / total_rows)

    Null detection:
        The dataset encodes missingness in multiple ways. This script treats a
        value as absent if it is:
            - SQL NULL
            - The string '[null]'
            - The string '[""]'
            - An empty string ''

        This matches the missingness handling used throughout the rest of the analysis.

    Output:
        One row per column. Sorted: general columns first, then paired
        attribute columns together (alt side before base side).
    """

    con = duckdb.connect(database=":memory:")

    schema = con.execute(f"DESCRIBE SELECT * FROM '{PARQUET_PATH}'").fetchdf()
    columns = schema["column_name"].tolist()

    rows = []
    total = con.execute(f"SELECT COUNT(*) FROM '{PARQUET_PATH}'").fetchone()[0]

    for col in columns:
        # Cast to VARCHAR so string-encoded nulls ([null], [""]) can be
        # detected regardless of the column's native type (e.g. confidence is DOUBLE).
        present = con.execute(f"""
            SELECT COUNT(*) FROM '{PARQUET_PATH}'
            WHERE {col} IS NOT NULL
              AND CAST({col} AS VARCHAR) != '[null]'
              AND CAST({col} AS VARCHAR) != '[""]'
              AND CAST({col} AS VARCHAR) != ''
        """).fetchone()[0]

        side = "base" if col.startswith("base_") else "alt"
        attr = col.removeprefix("base_")

        rows.append({
            "column":        col,
            "attribute":     attr,
            "side":          side,
            "total_rows":    total,
            "present_count": present,
            "coverage_pct":  round(present / total * 100, 2),
        })

    import csv
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["column", "attribute", "side", "total_rows", "present_count", "coverage_pct"])
        writer.writeheader()
        writer.writerows(rows)

    con.close()
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()