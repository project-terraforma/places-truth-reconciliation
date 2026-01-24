import duckdb
import pandas as pd

# Show everything (no truncation)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.width", None)
pd.set_option("display.max_colwidth", None)

PARQUET_PATH = "../data/raw/project_a_samples.parquet"

# Attributes that represent reconcilable place properties
ATTRIBUTES = [
    "addresses",
    "categories",
    "phones",
    "websites",
    "names",
    "socials",
    "brand",
    "emails",
    "confidence",
    "sources",
]

CORE_ATTRIBUTES = ["addresses", "categories", "phones", "websites"]


def main():
    con = duckdb.connect()

    print("\n================ SCHEMA ================\n")
    print(con.execute(f"""
        DESCRIBE SELECT * FROM '{PARQUET_PATH}'
    """).fetchdf())

    print("\n================ SAMPLE ROWS ================\n")
    print(con.execute(f"""
        SELECT * FROM '{PARQUET_PATH}' LIMIT 3
    """).fetchdf())

    print("\n================ ROW COUNT ================\n")
    total_rows = con.execute(f"""
        SELECT COUNT(*) FROM '{PARQUET_PATH}'
    """).fetchone()[0]
    print(f"Total rows: {total_rows}")

    print("\n================ COVERAGE & CONFLICTS ================\n")
    rows = []

    for attr in ATTRIBUTES:
        base_attr = f"base_{attr}"

        result = con.execute(f"""
            SELECT
                COUNT(*) AS total_rows,
                SUM({attr} IS NOT NULL) AS attr_present,
                SUM({base_attr} IS NOT NULL) AS base_attr_present,
                SUM(
                    {attr} IS NOT NULL
                    AND {base_attr} IS NOT NULL
                    AND {attr} != {base_attr}
                ) AS conflicts
            FROM '{PARQUET_PATH}'
        """).fetchone()

        rows.append({
            "attribute": attr,
            "attr_present": result[1],
            "base_attr_present": result[2],
            "conflict_count": result[3],
            "conflict_rate_pct": (result[3] / total_rows) * 100,
        })

    summary = pd.DataFrame(rows).sort_values(
        by="conflict_count", ascending=False
    )
    print(summary)

    # ---- High-leverage inspections below ---- #

    for attr in CORE_ATTRIBUTES:
        base_attr = f"base_{attr}"

        print(f"\n=== Conflict Type Breakdown: {attr.upper()} ===\n")
        print(con.execute(f"""
            SELECT
                SUM({attr} IS NOT NULL AND {base_attr} IS NOT NULL AND {attr} != {base_attr}) AS both_present_conflict,
                SUM({attr} IS NOT NULL AND {base_attr} IS NULL) AS alt_only,
                SUM({attr} IS NULL AND {base_attr} IS NOT NULL) AS base_only,
                SUM({attr} IS NULL AND {base_attr} IS NULL) AS neither
            FROM '{PARQUET_PATH}'
        """).fetchdf())

    print("\n=== Confidence vs Conflict (Phones) ===\n")
    print(con.execute(f"""
        SELECT
            CASE
                WHEN phones != base_phones THEN 'conflict'
                ELSE 'no_conflict'
            END AS status,
            AVG(confidence) AS avg_confidence,
            AVG(base_confidence) AS avg_base_confidence
        FROM '{PARQUET_PATH}'
        WHERE phones IS NOT NULL AND base_phones IS NOT NULL
        GROUP BY status
    """).fetchdf())

    print("\n=== High-Risk Rows (Low Confidence + Conflict) ===\n")
    print(con.execute(f"""
        SELECT COUNT(*) AS high_risk_rows
        FROM '{PARQUET_PATH}'
        WHERE
            phones IS NOT NULL
            AND base_phones IS NOT NULL
            AND phones != base_phones
            AND confidence < 0.6
            AND base_confidence < 0.6
    """).fetchdf())


if __name__ == "__main__":
    main()