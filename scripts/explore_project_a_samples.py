import duckdb
import pandas as pd

PARQUET_PATH = "../data/raw/project_a_samples.parquet"

# Exploratory analysis for aggregation-level attribute disagreement.
# Produces durable CSV artifacts for coverage, conflict, abstention,
# confidence signal behavior, and high-risk rows.

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

# High-impact attributes for deeper inspection
CORE_ATTRIBUTES = ["addresses", "categories", "phones", "websites"]


def main():
    con = duckdb.connect(database=':memory:')

    # ------------------------------------------------------------
    # Global row count
    # ------------------------------------------------------------
    total_rows = con.execute(f"""
        SELECT COUNT(*) FROM '{PARQUET_PATH}'
    """).fetchone()[0]

    # ------------------------------------------------------------
    # Attribute-level coverage, conflict, and abstention summary
    # ------------------------------------------------------------
    summary_rows = []

    for attr in ATTRIBUTES:
        base_attr = f"base_{attr}"

        result = con.execute(f"""
            SELECT
                SUM({attr} IS NOT NULL) AS attr_present,
                SUM({base_attr} IS NOT NULL) AS base_attr_present,
                SUM({attr} IS NOT NULL AND {base_attr} IS NOT NULL AND {attr} != {base_attr}) AS conflicts,
                SUM({attr} IS NOT NULL AND {base_attr} IS NULL) AS alt_only,
                SUM({attr} IS NULL AND {base_attr} IS NOT NULL) AS base_only
            FROM '{PARQUET_PATH}'
        """).fetchone()

        attr_present, base_present, conflicts, alt_only, base_only = result
        abstention_pressure = conflicts + alt_only + base_only

        summary_rows.append({
            "attribute": attr,

            # Raw counts
            "attr_present": attr_present,
            "base_attr_present": base_present,

            # Coverage
            "alt_coverage_pct": round(attr_present / total_rows * 100, 2),
            "base_coverage_pct": round(base_present / total_rows * 100, 2),

            # Conflict
            "conflict_count": conflicts,
            "conflict_rate_pct": round(conflicts / total_rows * 100, 2),

            # Abstention (decision pressure)
            "abstention_rate_pct": round(abstention_pressure / total_rows * 100, 2),
        })

    pd.DataFrame(summary_rows) \
        .sort_values(by=["conflict_count", "attribute"], ascending=[False, True]) \
        .to_csv("../analysis/attribute_conflict_summary.csv", index=False)

    # ------------------------------------------------------------
    # Conflict-type breakdowns for high-impact attributes
    # ------------------------------------------------------------
    breakdown_rows = []

    for attr in CORE_ATTRIBUTES:
        base_attr = f"base_{attr}"

        result = con.execute(f"""
            SELECT
                SUM({attr} IS NOT NULL AND {base_attr} IS NOT NULL AND {attr} != {base_attr}),
                SUM({attr} IS NOT NULL AND {base_attr} IS NULL),
                SUM({attr} IS NULL AND {base_attr} IS NOT NULL),
                SUM({attr} IS NULL AND {base_attr} IS NULL)
            FROM '{PARQUET_PATH}'
        """).fetchone()

        breakdown_rows.append({
            "attribute": attr,
            "both_present_conflict": result[0],
            "alt_only": result[1],
            "base_only": result[2],
            "neither": result[3],
        })

    pd.DataFrame(breakdown_rows) \
        .to_csv("../analysis/attribute_conflict_breakdown.csv", index=False)

    # ------------------------------------------------------------
    # Confidence signal behavior (conflict vs match)
    # ------------------------------------------------------------
    confidence_rows = []

    for attr in CORE_ATTRIBUTES:
        base_attr = f"base_{attr}"

        result = con.execute(f"""
            SELECT
                AVG(CASE WHEN {attr} != {base_attr} THEN confidence END),
                AVG(CASE WHEN {attr} != {base_attr} THEN base_confidence END),
                AVG(CASE WHEN {attr} = {base_attr} THEN confidence END),
                AVG(CASE WHEN {attr} = {base_attr} THEN base_confidence END)
            FROM '{PARQUET_PATH}'
            WHERE {attr} IS NOT NULL AND {base_attr} IS NOT NULL
        """).fetchone()

        confidence_rows.append({
            "attribute": attr,
            "avg_conflict_confidence": round(result[0], 3),
            "avg_conflict_base_confidence": round(result[1], 3),
            "avg_match_confidence": round(result[2], 3),
            "avg_match_base_confidence": round(result[3], 3),
        })

    pd.DataFrame(confidence_rows) \
        .to_csv("../analysis/attribute_confidence_behavior.csv", index=False)

    # ------------------------------------------------------------
    # High-risk rows (low confidence + conflict) — row-level
    # ------------------------------------------------------------
    high_risk_rows = con.execute(f"""
        SELECT
            id,
            phones,
            base_phones,
            confidence,
            base_confidence
        FROM '{PARQUET_PATH}'
        WHERE
            phones IS NOT NULL
            AND base_phones IS NOT NULL
            AND phones != base_phones
            AND confidence < 0.6
            AND base_confidence < 0.6
    """).fetchdf()

    high_risk_rows.to_csv(
        "../analysis/high_risk_phone_conflicts.csv",
        index=False
    )

    high_risk_address_rows = con.execute(f"""
        SELECT
            id,
            addresses,
            base_addresses,
            confidence,
            base_confidence
        FROM '{PARQUET_PATH}'
        WHERE
            addresses IS NOT NULL
            AND base_addresses IS NOT NULL
            AND addresses != base_addresses
            AND confidence < 0.6
            AND base_confidence < 0.6
    """).fetchdf()

    high_risk_address_rows.to_csv(
        "../analysis/high_risk_address_conflicts.csv",
        index=False
    )

    high_risk_website_rows = con.execute(f"""
        SELECT
            id,
            websites,
            base_websites,
            confidence,
            base_confidence
        FROM '{PARQUET_PATH}'
        WHERE
            websites IS NOT NULL
            AND base_websites IS NOT NULL
            AND websites != base_websites
            AND confidence < 0.6
            AND base_confidence < 0.6
    """).fetchdf()

    high_risk_website_rows.to_csv(
        "../analysis/high_risk_website_conflicts.csv",
        index=False
    )

    con.close()

if __name__ == "__main__":
    main()