import duckdb

PARQUET_PATH = "../data/raw/project_a_samples.parquet"

OUTPUT_PRIMARY_CONTRIBUTOR  = "../analysis/general/source_provider.csv"
OUTPUT_PAIRINGS             = "../analysis/general/source_provider_pairings.csv"
OUTPUT_PROPERTY_VALUES      = "../analysis/general/source_property_values.csv"
OUTPUT_ATTR_CONTRIBUTORS    = "../analysis/general/source_attr_contributors_per_row.csv"


def main():
    """
    Purpose:
        Audit which upstream data providers appear on each side of the dataset
        and characterize how they are used.

    Why this matters:
        Provider identity is a candidate feature for reconciliation scoring.
        If certain providers systematically produce more reliable attribute values,
        that becomes a useful signal when selecting between candidates.
        This analysis establishes the baseline distribution before that hypothesis
        can be tested against labeled data.

    The sources JSON contains a 'property' field with two distinct meanings:
        - property == ""                       -> primary contributor (provided attribute values)
        - property == "/properties/existence"  -> existence-only (confirmed the place exists,
                                                  did not contribute attribute data)
        - property missing                     -> older format, treated as primary contributor

    Before trusting provider identity as a feature, we first verify it is
    unambiguous: source_attr_contributors_per_row.csv confirms every row has
    exactly one attribute-contributing source on each side. source_property_values.csv
    shows the raw distinct values of the property field so the filtering logic
    can be independently verified.

    Outputs:

        source_provider.csv
            Which provider is the primary attribute contributor per side,
            and how often. Filters out existence-only entries.

        source_provider_pairings.csv
            Cross-tabulation of base provider vs alt provider.
            Shows which combinations actually appear in the dataset.

        source_property_values.csv
            All distinct values of the property field per side with counts.
            Used to verify the filtering logic is correct.

        source_attr_contributors_per_row.csv
            For each side, how many rows have N attribute-contributing sources.
            Confirms provider identity is unambiguous (always exactly 1 per row).
    """

    con = duckdb.connect(database=":memory:")

    # ── Explode sources arrays into long tables ────────────────────────

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW base_sources_long AS
        SELECT
            id,
            entry.dataset AS dataset,
            entry.property AS property
        FROM (
            SELECT id, unnest(
                from_json(
                    COALESCE(base_sources, '[]'),
                    '[{{"dataset": "VARCHAR", "property": "VARCHAR"}}]'
                )
            ) AS entry
            FROM '{PARQUET_PATH}'
        )
        WHERE entry.dataset IS NOT NULL
    """)

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW alt_sources_long AS
        SELECT
            id,
            entry.dataset AS dataset,
            entry.property AS property
        FROM (
            SELECT id, unnest(
                from_json(
                    COALESCE(sources, '[]'),
                    '[{{"dataset": "VARCHAR", "property": "VARCHAR"}}]'
                )
            ) AS entry
            FROM '{PARQUET_PATH}'
        )
        WHERE entry.dataset IS NOT NULL
    """)

    # ── Property values (verification) ────────────────────────────────

    con.execute(f"""
        COPY (
            SELECT side, property, COUNT(*) AS entry_count
            FROM (
                SELECT 'alt'  AS side, property FROM alt_sources_long
                UNION ALL
                SELECT 'base' AS side, property FROM base_sources_long
            )
            GROUP BY side, property
            ORDER BY side, entry_count DESC
        )
        TO '{OUTPUT_PROPERTY_VALUES}'
        WITH (HEADER, DELIMITER ',')
    """)

    # ── Attribute contributors per row (verification) ──────────────────

    con.execute(f"""
        COPY (
            SELECT side, attr_contributors, COUNT(*) AS row_count
            FROM (
                SELECT 'alt' AS side, id,
                    SUM(CASE WHEN property != '/properties/existence' OR property IS NULL
                        THEN 1 ELSE 0 END) AS attr_contributors
                FROM alt_sources_long GROUP BY id

                UNION ALL

                SELECT 'base' AS side, id,
                    SUM(CASE WHEN property != '/properties/existence' OR property IS NULL
                        THEN 1 ELSE 0 END) AS attr_contributors
                FROM base_sources_long GROUP BY id
            )
            GROUP BY side, attr_contributors
            ORDER BY side, attr_contributors
        )
        TO '{OUTPUT_ATTR_CONTRIBUTORS}'
        WITH (HEADER, DELIMITER ',')
    """)

    # ── Primary contributor per side ───────────────────────────────────

    con.execute(f"""
        COPY (
            SELECT
                side,
                dataset,
                COUNT(DISTINCT id) AS row_count,
                ROUND(COUNT(DISTINCT id) * 100.0 / (SELECT COUNT(*) FROM '{PARQUET_PATH}'), 2) AS row_pct
            FROM (
                SELECT 'base' AS side, id, dataset
                FROM base_sources_long
                WHERE property IS NULL OR property != '/properties/existence'

                UNION ALL

                SELECT 'alt' AS side, id, dataset
                FROM alt_sources_long
                WHERE property IS NULL OR property != '/properties/existence'
            )
            GROUP BY side, dataset
            ORDER BY side, row_count DESC
        )
        TO '{OUTPUT_PRIMARY_CONTRIBUTOR}'
        WITH (HEADER, DELIMITER ',')
    """)

    # ── Provider pairings ──────────────────────────────────────────────

    con.execute("""
        CREATE OR REPLACE TEMP VIEW base_primary AS
        SELECT id, dataset AS base_provider
        FROM base_sources_long
        WHERE property IS NULL OR property != '/properties/existence'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY property) = 1
    """)

    con.execute("""
        CREATE OR REPLACE TEMP VIEW alt_primary AS
        SELECT id, dataset AS alt_provider
        FROM alt_sources_long
        WHERE property IS NULL OR property != '/properties/existence'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY property) = 1
    """)

    con.execute(f"""
        COPY (
            SELECT
                COALESCE(b.base_provider, 'none') AS base_provider,
                COALESCE(a.alt_provider,  'none') AS alt_provider,
                COUNT(*) AS row_count,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM '{PARQUET_PATH}'), 2) AS row_pct
            FROM '{PARQUET_PATH}' p
            LEFT JOIN base_primary b USING (id)
            LEFT JOIN alt_primary  a USING (id)
            GROUP BY base_provider, alt_provider
            ORDER BY row_count DESC
        )
        TO '{OUTPUT_PAIRINGS}'
        WITH (HEADER, DELIMITER ',')
    """)

    con.close()
    print("Source provider analysis complete.")
    print(f"  {OUTPUT_PROPERTY_VALUES}")
    print(f"  {OUTPUT_ATTR_CONTRIBUTORS}")
    print(f"  {OUTPUT_PRIMARY_CONTRIBUTOR}")
    print(f"  {OUTPUT_PAIRINGS}")


if __name__ == "__main__":
    main()