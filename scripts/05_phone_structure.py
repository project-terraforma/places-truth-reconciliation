import duckdb

PARQUET_PATH = "../data/raw/project_a_samples.parquet"

OUTPUT_METRICS_PATH = "../analysis/phones/phone_structure_summary.csv"
OUTPUT_DISTRIBUTION_PATH = "../analysis/phones/phone_digit_length_distribution.csv"


def main():
    """
    Purpose:
        Structural phone format audit (usable values only).

    Missingness is handled separately in:
        04_phone_missingness.py

    This script only evaluates:
        - formatting features
        - digit-length validity
        - structural consistency
    """

    con = duckdb.connect(database=":memory:")

    # Long table
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW phone_long AS
        SELECT id, 'alt' AS source, phones AS raw_phone
        FROM '{PARQUET_PATH}'
        UNION ALL
        SELECT id, 'base' AS source, base_phones AS raw_phone
        FROM '{PARQUET_PATH}';
    """)

    # Extract usable rows only (has at least 1 digit)
    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW phone_features AS
        SELECT
            id,
            source,
            raw_phone,

            regexp_replace(raw_phone, '\D', '', 'g') AS digits_only,

            length(regexp_replace(raw_phone, '\D', '', 'g')) AS digit_length,

            (strpos(raw_phone, '+') > 0) AS has_plus,
            (strpos(raw_phone, '(') > 0 OR strpos(raw_phone, ')') > 0) AS has_parentheses,
            (strpos(raw_phone, '-') > 0) AS has_hyphen,
            regexp_matches(
                regexp_replace(raw_phone, '^\[\s*"?(.*?)"?\s*\]$', '\1'),
                '^\d+$'
            ) AS is_pure_numeric

        FROM phone_long
        WHERE raw_phone IS NOT NULL
          AND length(regexp_replace(raw_phone, '\D', '', 'g')) > 0
    """)

    # Metrics summary
    con.execute(f"""
        COPY (
            SELECT
                source,
                COUNT(*) AS usable_rows,

                SUM(CASE WHEN has_plus THEN 1 ELSE 0 END) AS has_plus_count,
                ROUND(AVG(CASE WHEN has_plus THEN 1 ELSE 0 END) * 100, 2) AS has_plus_pct,

                SUM(CASE WHEN has_parentheses THEN 1 ELSE 0 END) AS has_parentheses_count,
                ROUND(AVG(CASE WHEN has_parentheses THEN 1 ELSE 0 END) * 100, 2) AS has_parentheses_pct,

                SUM(CASE WHEN has_hyphen THEN 1 ELSE 0 END) AS has_hyphen_count,
                ROUND(AVG(CASE WHEN has_hyphen THEN 1 ELSE 0 END) * 100, 2) AS has_hyphen_pct,

                SUM(CASE WHEN is_pure_numeric THEN 1 ELSE 0 END) AS pure_numeric_count,
                ROUND(AVG(CASE WHEN is_pure_numeric THEN 1 ELSE 0 END) * 100, 2) AS pure_numeric_pct,

                SUM(CASE WHEN digit_length < 7 THEN 1 ELSE 0 END) AS too_short_count,
                SUM(CASE WHEN digit_length > 15 THEN 1 ELSE 0 END) AS too_long_count

            FROM phone_features
            GROUP BY source
            ORDER BY source
        )
        TO '{OUTPUT_METRICS_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    # Digit length distribution (usable only)
    con.execute(f"""
        COPY (
            SELECT
                source,
                CASE
                    WHEN digit_length < 7 THEN '<7'
                    WHEN digit_length BETWEEN 7 AND 9 THEN '7-9'
                    WHEN digit_length = 10 THEN '10'
                    WHEN digit_length = 11 THEN '11'
                    WHEN digit_length BETWEEN 12 AND 15 THEN '12-15'
                    ELSE '>15'
                END AS digit_length_bucket,
                COUNT(*) AS count,
                ROUND(
                    COUNT(*)::DOUBLE
                    / SUM(COUNT(*)) OVER (PARTITION BY source) * 100,
                    2
                ) AS pct
            FROM phone_features
            GROUP BY 1,2
            ORDER BY source, digit_length_bucket
        )
        TO '{OUTPUT_DISTRIBUTION_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    con.close()


if __name__ == "__main__":
    main()