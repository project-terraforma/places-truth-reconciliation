import duckdb

PARQUET_PATH = "../data/raw/project_a_samples.parquet"
OUTPUT_PATH = "../analysis/phones/phone_missingness_summary.csv"
OUTPUT_NULL_IMPACT_PATH = "../analysis/phones/phone_null_normalization_impact.csv"


def main():
    """
    Purpose:
        Audit all "missing-like" phone encodings in the dataset and measure
        how many apparent conflicts null normalization resolves.

    Why this matters:
        The dataset does NOT only contain SQL NULL.
        It also contains string-encoded nulls and empty-array wrappers like:
            - [null]
            - [""]
            - ["NULL"]

        If we do not explicitly measure these, reconciliation logic
        will misclassify missingness as disagreement.

    This script counts:
        - true SQL NULL
        - bracket-wrapped null markers
        - bracket-wrapped empty strings
        - uppercase/lowercase null markers
        - any string containing 'null'

    It also measures the impact of null normalization:
        - How many rows have apparent conflicts (different raw strings)
          that become agreements after null unification?
        - How many rows change from "string vs string" conflict to
          correctly classified "one-sided" or "both null"?
    """

    con = duckdb.connect(database=":memory:")

    # ── Output 1: Per-side null encoding audit (unchanged) ─────
    con.execute(f"""
        COPY (
            SELECT
                source,
                COUNT(*) AS total_rows,

                COUNT(*) FILTER (WHERE raw_phone IS NULL) AS sql_null,

                COUNT(*) FILTER (WHERE raw_phone = '[null]') AS bracket_null,

                COUNT(*) FILTER (WHERE raw_phone = '[""]') AS bracket_empty_string,

                COUNT(*) FILTER (WHERE raw_phone = '["NULL"]') AS bracket_null_caps,

                COUNT(*) FILTER (WHERE raw_phone = '["null"]') AS bracket_null_lower,

                COUNT(*) FILTER (
                    WHERE raw_phone IS NOT NULL
                    AND lower(raw_phone) LIKE '%null%'
                ) AS contains_null_text

            FROM (
                SELECT 'alt' AS source, phones AS raw_phone
                FROM '{PARQUET_PATH}'
                UNION ALL
                SELECT 'base' AS source, base_phones AS raw_phone
                FROM '{PARQUET_PATH}'
            )
            GROUP BY source
            ORDER BY source
        )
        TO '{OUTPUT_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    # ── Output 2: Null normalization impact ────────────────────
    #
    # Compare row-level conflict status BEFORE and AFTER null unification.
    #
    # "Before": raw phone strings compared directly.
    # "After":  null-like values ([null], [""], ["NULL"], SQL NULL) unified
    #           to NULL, then compared.
    #
    # A row is a "false conflict" if the raw strings differ but both sides
    # are null-like (so after unification, both become NULL = agreement).

    con.execute(f"""
        COPY (
            WITH raw AS (
                SELECT
                    phones      AS raw_alt,
                    base_phones AS raw_base,

                    -- Null-normalize: unify all null-like values to actual NULL
                    CASE
                        WHEN phones IS NULL THEN NULL
                        WHEN phones IN ('[null]', '[""]', '["NULL"]', '["null"]') THEN NULL
                        ELSE phones
                    END AS norm_alt,

                    CASE
                        WHEN base_phones IS NULL THEN NULL
                        WHEN base_phones IN ('[null]', '[""]', '["NULL"]', '["null"]') THEN NULL
                        ELSE base_phones
                    END AS norm_base

                FROM '{PARQUET_PATH}'
            ),
            classified AS (
                SELECT
                    -- Before null normalization
                    CASE
                        WHEN raw_alt IS NULL AND raw_base IS NULL    THEN 'both_null'
                        WHEN raw_alt IS NULL AND raw_base IS NOT NULL THEN 'base_only'
                        WHEN raw_alt IS NOT NULL AND raw_base IS NULL THEN 'alt_only'
                        WHEN raw_alt = raw_base                       THEN 'raw_agree'
                        ELSE 'raw_conflict'
                    END AS before_status,

                    -- After null normalization
                    CASE
                        WHEN norm_alt IS NULL AND norm_base IS NULL    THEN 'both_null'
                        WHEN norm_alt IS NULL AND norm_base IS NOT NULL THEN 'base_only'
                        WHEN norm_alt IS NOT NULL AND norm_base IS NULL THEN 'alt_only'
                        WHEN norm_alt = norm_base                       THEN 'norm_agree'
                        ELSE 'norm_conflict'
                    END AS after_status

                FROM raw
            )
            SELECT
                before_status,
                after_status,
                COUNT(*) AS row_count,
                ROUND(COUNT(*)::DOUBLE / 2000 * 100, 2) AS pct_of_total
            FROM classified
            GROUP BY before_status, after_status
            ORDER BY row_count DESC
        )
        TO '{OUTPUT_NULL_IMPACT_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    con.close()
    print(f"Phone missingness audit written to {OUTPUT_PATH}")
    print(f"Null normalization impact written to {OUTPUT_NULL_IMPACT_PATH}")
    print()
    print("The impact file shows how row-level conflict status changes")
    print("before vs after null unification. Rows that transition from")
    print("'raw_conflict' to 'both_null' or '*_only' are false conflicts")
    print("that null normalization resolves.")


if __name__ == "__main__":
    main()