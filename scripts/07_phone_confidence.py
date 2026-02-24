import duckdb

PARQUET_PATH = "../../data/raw/project_a_samples.parquet"

OUTPUT_SUMMARY_PATH      = "../../analysis/phones/phone_true_conflict_confidence_summary.csv"
OUTPUT_DETAIL_PATH       = "../../analysis/phones/phone_true_conflict_confidence_detail.csv"
OUTPUT_DISTRIBUTION_PATH  = "../../analysis/phones/phone_confidence_distribution.csv"
OUTPUT_DIST_BUCKETED_PATH = "../../analysis/phones/phone_confidence_distribution_bucketed.csv"

NULL_SENTINELS = ('[null]', '[""]', '["NULL"]', '["null"]', '')


def main():
    """
    Purpose:
        Test whether confidence scores are a useful signal for resolving
        remaining phone conflicts after normalization.

    Runs the full normalization classification pipeline once and writes
    three output tables:

        phone_true_conflict_confidence_summary.csv
            One row per conflict class. Aggregate confidence stats per side:
            averages, median gap, which side scores higher and how often.

        phone_true_conflict_confidence_detail.csv
            One row per unresolved conflict (true_conflict, alt_only, base_only).
            Per-row confidence values, gap, and which side scores higher.

        phone_confidence_distribution.csv
            Confidence value histogram per side per conflict class.
            Directly backs claims like "98% of base scores are 1.0 or 0.77."

    Note: confidence is row-level — it reflects upstream aggregation certainty
    for the whole place record, not phone-specific confidence. Per the Overture
    schema, it measures place existence, not attribute quality.

    Classification logic must match 06_phone_normalization.py exactly.
    """

    con = duckdb.connect(database=":memory:")

    con.execute("CREATE OR REPLACE TEMP TABLE null_sentinels (val VARCHAR)")
    for s in NULL_SENTINELS:
        con.execute("INSERT INTO null_sentinels VALUES (?)", [s])

    # ── Step 1: normalize nulls ────────────────────────────────────────

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW phone_raw AS
        SELECT
            id,
            confidence AS alt_confidence,
            base_confidence,
            CASE WHEN phones IS NULL OR phones IN (SELECT val FROM null_sentinels)
                THEN NULL ELSE phones END AS alt_raw,
            CASE WHEN base_phones IS NULL OR base_phones IN (SELECT val FROM null_sentinels)
                THEN NULL ELSE base_phones END AS base_raw
        FROM '{PARQUET_PATH}';
    """)

    # ── Step 2: extract digits ─────────────────────────────────────────

    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW phone_digits AS
        SELECT *,
            regexp_replace(coalesce(alt_raw, ''), '\D', '', 'g') AS alt_digits,
            regexp_replace(coalesce(base_raw, ''), '\D', '', 'g') AS base_digits
        FROM phone_raw;
    """)

    # ── Step 3: equivalence flags ──────────────────────────────────────

    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW phone_flags AS
        SELECT *,
            (length(alt_digits) > 0) AS alt_usable,
            (length(base_digits) > 0) AS base_usable,
            (length(alt_digits) > 0 AND length(base_digits) > 0) AS both_usable,
            (alt_digits = base_digits) AS eq_exact,
            (
              (length(alt_digits) = length(base_digits) + 1 AND substr(alt_digits, 2) = base_digits)
              OR (length(base_digits) = length(alt_digits) + 1 AND substr(base_digits, 2) = alt_digits)
            ) AS eq_1cc,
            (
              (substr(base_digits, 1, 1) = '0' AND length(alt_digits) = length(base_digits) + 1
               AND substr(alt_digits, 3) = substr(base_digits, 2))
              OR (substr(alt_digits, 1, 1) = '0' AND length(base_digits) = length(alt_digits) + 1
               AND substr(base_digits, 3) = substr(alt_digits, 2))
            ) AS eq_trunk0_cc2,
            (
              (substr(base_digits, 1, 1) = '0' AND length(alt_digits) = length(base_digits) + 2
               AND substr(alt_digits, 4) = substr(base_digits, 2))
              OR (substr(alt_digits, 1, 1) = '0' AND length(base_digits) = length(alt_digits) + 2
               AND substr(base_digits, 4) = substr(alt_digits, 2))
            ) AS eq_trunk0_cc3,
            (
              (length(alt_digits) >= 2 AND length(alt_digits) = length(base_digits) + 2
               AND substr(alt_digits, 3) = base_digits)
              OR (length(base_digits) >= 2 AND length(base_digits) = length(alt_digits) + 2
               AND substr(base_digits, 3) = alt_digits)
            ) AS eq_cc2_national,
            (
              (length(alt_digits) >= 3 AND length(alt_digits) = length(base_digits) + 3
               AND substr(alt_digits, 4) = base_digits)
              OR (length(base_digits) >= 3 AND length(base_digits) = length(alt_digits) + 3
               AND substr(base_digits, 4) = alt_digits)
            ) AS eq_cc3_national,
            (
              (length(alt_digits) >= 3 AND length(alt_digits) = length(base_digits) + 1
               AND substr(alt_digits, 1, 2) = substr(base_digits, 1, 2)
               AND substr(alt_digits, 3, 1) = '0' AND substr(alt_digits, 4) = substr(base_digits, 3))
              OR (length(base_digits) >= 3 AND length(base_digits) = length(alt_digits) + 1
               AND substr(base_digits, 1, 2) = substr(alt_digits, 1, 2)
               AND substr(base_digits, 3, 1) = '0' AND substr(base_digits, 4) = substr(alt_digits, 3))
            ) AS eq_cc2_extra0,
            (
              (length(alt_digits) = length(base_digits)
               AND substr(alt_digits, 1, 1) = '7' AND substr(base_digits, 1, 1) = '8'
               AND substr(alt_digits, 2) = substr(base_digits, 2))
              OR (length(alt_digits) = length(base_digits)
               AND substr(alt_digits, 1, 1) = '8' AND substr(base_digits, 1, 1) = '7'
               AND substr(alt_digits, 2) = substr(base_digits, 2))
            ) AS eq_ru_trunk8
        FROM phone_digits;
    """)

    # ── Step 4: classify rows ──────────────────────────────────────────

    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW phone_classified AS
        SELECT *,
            CASE
                WHEN NOT alt_usable AND NOT base_usable THEN 'both_missing'
                WHEN alt_usable AND NOT base_usable     THEN 'alt_only'
                WHEN NOT alt_usable AND base_usable     THEN 'base_only'
                WHEN both_usable AND (
                    eq_exact OR eq_1cc OR eq_trunk0_cc2 OR eq_trunk0_cc3
                    OR eq_cc2_national OR eq_cc3_national OR eq_cc2_extra0 OR eq_ru_trunk8
                ) THEN 'resolved_by_normalization'
                ELSE 'true_conflict'
            END AS conflict_class
        FROM phone_flags;
    """)

    # ── Output 1: summary per conflict class ───────────────────────────

    con.execute(f"""
        COPY (
            WITH by_class AS (
                SELECT
                    conflict_class,
                    COUNT(*) AS row_count,
                    ROUND(AVG(alt_confidence), 4)  AS avg_alt_confidence,
                    ROUND(AVG(base_confidence), 4) AS avg_base_confidence,
                    ROUND(AVG(alt_confidence - base_confidence), 4)        AS avg_confidence_diff,
                    ROUND(MEDIAN(ABS(alt_confidence - base_confidence)), 4) AS median_confidence_gap,
                    SUM(CASE WHEN alt_confidence  > base_confidence THEN 1 ELSE 0 END) AS alt_conf_higher,
                    SUM(CASE WHEN base_confidence > alt_confidence  THEN 1 ELSE 0 END) AS base_conf_higher,
                    SUM(CASE WHEN alt_confidence  = base_confidence THEN 1 ELSE 0 END) AS conf_tied
                FROM phone_classified
                GROUP BY conflict_class
            )
            SELECT *,
                ROUND(alt_conf_higher::DOUBLE  / row_count * 100, 1) AS pct_alt_higher,
                ROUND(base_conf_higher::DOUBLE / row_count * 100, 1) AS pct_base_higher,
                ROUND(conf_tied::DOUBLE        / row_count * 100, 1) AS pct_tied
            FROM by_class
            ORDER BY conflict_class
        )
        TO '{OUTPUT_SUMMARY_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    # ── Output 2: per-row detail for unresolved conflicts ──────────────

    con.execute(f"""
        COPY (
            SELECT
                id, conflict_class, alt_raw, base_raw, alt_digits, base_digits,
                length(alt_digits)  AS alt_digit_len,
                length(base_digits) AS base_digit_len,
                ROUND(alt_confidence, 4)  AS alt_confidence,
                ROUND(base_confidence, 4) AS base_confidence,
                ROUND(alt_confidence - base_confidence, 4)       AS confidence_diff,
                ROUND(ABS(alt_confidence - base_confidence), 4)  AS confidence_gap,
                CASE
                    WHEN alt_confidence  > base_confidence THEN 'alt'
                    WHEN base_confidence > alt_confidence  THEN 'base'
                    ELSE 'tied'
                END AS higher_confidence_side
            FROM phone_classified
            WHERE conflict_class IN ('true_conflict', 'alt_only', 'base_only')
            ORDER BY conflict_class, confidence_gap DESC, id
        )
        TO '{OUTPUT_DETAIL_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    # ── Output 3: confidence value histogram per side per class ────────

    con.execute(f"""
        COPY (
            WITH class_totals AS (
                SELECT conflict_class, COUNT(*) AS class_total
                FROM phone_classified GROUP BY conflict_class
            ),
            alt_dist AS (
                SELECT 'alt' AS side, conflict_class,
                    ROUND(alt_confidence, 2) AS confidence_value, COUNT(*) AS row_count
                FROM phone_classified
                GROUP BY conflict_class, ROUND(alt_confidence, 2)
            ),
            base_dist AS (
                SELECT 'base' AS side, conflict_class,
                    ROUND(base_confidence, 2) AS confidence_value, COUNT(*) AS row_count
                FROM phone_classified
                GROUP BY conflict_class, ROUND(base_confidence, 2)
            ),
            combined AS (SELECT * FROM alt_dist UNION ALL SELECT * FROM base_dist)
            SELECT
                combined.side, combined.conflict_class, combined.confidence_value,
                combined.row_count,
                ROUND(combined.row_count::DOUBLE / ct.class_total * 100, 2) AS pct_of_class
            FROM combined
            JOIN class_totals ct ON combined.conflict_class = ct.conflict_class
            ORDER BY combined.side, combined.conflict_class, combined.row_count DESC
        )
        TO '{OUTPUT_DISTRIBUTION_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    # ── Output 4: bucketed confidence distribution ────────────────────
    # Anchor values 1.0 and 0.77 get their own rows; everything else
    # is grouped into bands of ~0.03 for readability.

    con.execute(f"""
        COPY (
            WITH raw AS (
                SELECT side, conflict_class, confidence_value, row_count
                FROM (
                    SELECT 'alt'  AS side, conflict_class,
                        ROUND(alt_confidence, 2)  AS confidence_value, COUNT(*) AS row_count
                    FROM phone_classified
                    GROUP BY conflict_class, ROUND(alt_confidence, 2)
                    UNION ALL
                    SELECT 'base' AS side, conflict_class,
                        ROUND(base_confidence, 2) AS confidence_value, COUNT(*) AS row_count
                    FROM phone_classified
                    GROUP BY conflict_class, ROUND(base_confidence, 2)
                )
            ),
            bucketed AS (
                SELECT
                    side,
                    conflict_class,
                    CASE
                        WHEN confidence_value = 1.00 THEN '1.00'
                        WHEN confidence_value = 0.99 THEN '0.99'
                        WHEN confidence_value = 0.98 THEN '0.98'
                        WHEN confidence_value >= 0.95 THEN '0.97 – 0.95'
                        WHEN confidence_value >= 0.92 THEN '0.94 – 0.92'
                        WHEN confidence_value >= 0.89 THEN '0.91 – 0.89'
                        WHEN confidence_value >= 0.86 THEN '0.88 – 0.86'
                        WHEN confidence_value >= 0.78 THEN '0.85 – 0.78'
                        WHEN confidence_value = 0.77  THEN '0.77'
                        WHEN confidence_value >= 0.60 THEN '0.76 – 0.60'
                        ELSE '0.59 – 0.00'
                    END AS bucket,
                    CASE
                        WHEN confidence_value = 1.00 THEN 1
                        WHEN confidence_value = 0.99 THEN 2
                        WHEN confidence_value = 0.98 THEN 3
                        WHEN confidence_value >= 0.95 THEN 4
                        WHEN confidence_value >= 0.92 THEN 5
                        WHEN confidence_value >= 0.89 THEN 6
                        WHEN confidence_value >= 0.86 THEN 7
                        WHEN confidence_value >= 0.78 THEN 8
                        WHEN confidence_value = 0.77  THEN 9
                        WHEN confidence_value >= 0.60 THEN 10
                        ELSE 11
                    END AS bucket_order,
                    SUM(row_count) AS row_count
                FROM raw
                GROUP BY side, conflict_class, bucket, bucket_order
            ),
            totals AS (
                SELECT conflict_class, side, SUM(row_count) AS class_total
                FROM bucketed GROUP BY conflict_class, side
            )
            SELECT
                b.side, b.conflict_class, b.bucket,
                b.row_count,
                ROUND(b.row_count::DOUBLE / t.class_total * 100, 1) AS pct_of_class
            FROM bucketed b
            JOIN totals t ON b.conflict_class = t.conflict_class AND b.side = t.side
            ORDER BY b.side, b.conflict_class, b.bucket_order
        )
        TO '{OUTPUT_DIST_BUCKETED_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    con.close()
    print(f"Wrote: {OUTPUT_SUMMARY_PATH}")
    print(f"Wrote: {OUTPUT_DETAIL_PATH}")
    print(f"Wrote: {OUTPUT_DISTRIBUTION_PATH}")
    print(f"Wrote: {OUTPUT_DIST_BUCKETED_PATH}")


if __name__ == "__main__":
    main()