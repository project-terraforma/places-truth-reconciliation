import duckdb

PARQUET_PATH = "../data/raw/project_a_samples.parquet"
OUTPUT_PATH = "../analysis/phones/phone_missingness_summary.csv"


def main():
    """
    Purpose:
        Audit all "missing-like" phone encodings in the dataset.

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
    """

    con = duckdb.connect(database=":memory:")

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

    con.close()
    print(f"Phone missingness audit written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()