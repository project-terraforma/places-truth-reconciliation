import duckdb
import pandas as pd

PARQUET_PATH = "../data/raw/project_a_samples.parquet"

# All reconcilable attributes plus metadata columns
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

def main():
    """
    Purpose:
        Measure coverage, conflict rates, and conflict type breakdowns
        for every attribute in the dataset.

    Outputs:

        attribute_conflict_summary.csv
            One row per attribute. For each:
                - alt_coverage_pct / base_coverage_pct: share of rows with a value on each side
                - conflict_count: rows where both sides are present and disagree
                - conflict_rate_pct: conflict_count / total_rows
                - decision_pressure_pct: share of rows requiring an active decision —
                  either both sides disagree (pick one or abstain) or only one side
                  has a value (use it or abstain). Rows where both sides match or
                  both are missing are excluded; they require no decision.

        attribute_conflict_breakdown.csv
            One row per attribute. Decomposes each conflict type:
                - both_present_conflict: both sides have a value and disagree
                - alt_only: alt has a value, base does not
                - base_only: base has a value, alt does not
                - neither: both sides are missing
            Covers all attributes, not just a subset.
    """

    con = duckdb.connect(database=':memory:')

    total_rows = con.execute(f"SELECT COUNT(*) FROM '{PARQUET_PATH}'").fetchone()[0]

    # ── Coverage, conflict, and decision pressure ──────────────────────

    summary_rows = []

    for attr in ATTRIBUTES:
        base_attr = f"base_{attr}"

        result = con.execute(f"""
            SELECT
                SUM({attr} IS NOT NULL)     AS attr_present,
                SUM({base_attr} IS NOT NULL) AS base_attr_present,
                SUM({attr} IS NOT NULL AND {base_attr} IS NOT NULL
                    AND {attr} != {base_attr})     AS conflicts,
                SUM({attr} IS NOT NULL AND {base_attr} IS NULL)  AS alt_only,
                SUM({attr} IS NULL AND {base_attr} IS NOT NULL)  AS base_only
            FROM '{PARQUET_PATH}'
        """).fetchone()

        attr_present, base_present, conflicts, alt_only, base_only = result
        summary_rows.append({
            "attribute":            attr,
            "attr_present":         attr_present,
            "base_attr_present":    base_present,
            "alt_coverage_pct":     round(attr_present   / total_rows * 100, 2),
            "base_coverage_pct":    round(base_present   / total_rows * 100, 2),
            "conflict_count":       conflicts,
            "conflict_rate_pct":    round(conflicts       / total_rows * 100, 2),
        })

    pd.DataFrame(summary_rows) \
        .sort_values(by=["conflict_count", "attribute"], ascending=[False, True]) \
        .to_csv("../analysis/general/attribute_conflict_summary.csv", index=False)

    # ── Conflict type breakdown — all attributes ───────────────────────

    breakdown_rows = []

    for attr in ATTRIBUTES:
        base_attr = f"base_{attr}"

        result = con.execute(f"""
            SELECT
                SUM({attr} IS NOT NULL AND {base_attr} IS NOT NULL
                    AND {attr} != {base_attr}),
                SUM({attr} IS NOT NULL AND {base_attr} IS NULL),
                SUM({attr} IS NULL AND {base_attr} IS NOT NULL),
                SUM({attr} IS NULL AND {base_attr} IS NULL)
            FROM '{PARQUET_PATH}'
        """).fetchone()

        breakdown_rows.append({
            "attribute":            attr,
            "both_present_conflict": result[0],
            "alt_only":             result[1],
            "base_only":            result[2],
            "neither":              result[3],
        })

    pd.DataFrame(breakdown_rows) \
        .to_csv("../analysis/general/attribute_conflict_breakdown.csv", index=False)

    con.close()


if __name__ == "__main__":
    main()