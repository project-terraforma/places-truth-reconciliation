import duckdb

PARQUET_PATH = "../data/raw/project_a_samples.parquet"
OUTPUT_PATH = "../data/sampled_from_raw/project_a_names_sample_1.csv"

# Sampling strategy:
# - deterministic hash-based shuffle
# - population: name conflicts after basic normalization (lowercase + strip whitespace)
#   so casing-only and whitespace-only conflicts are excluded from conflict pool
# - salt: names_golden_candidates_v1
# - sample size: 160 conflicts, 40 matches
#
# Why 80/20 split (vs 60/40 for phones):
#   Structure analysis showed 85% of name conflicts have no detectable noise pattern
#   (yet, we're trying to figure that out right now).
#   Unlike phones where normalization resolved the majority, most name conflicts are
#   commonly expressing genuinely different values. Labeling effort should focus there.
#
# Context columns included (names, addresses, categories):
#   Name conflicts are often ambiguous without context.
#   Address and category help the labeler identify which side is factually correct.
#   e.g. "Chick-fil-A" vs "Chick-fil-A Grand Parkway North" — address tells you
#   if this is a specific location or a data error.

N_CONFLICTS = 160
N_MATCHES = 40
SALT = "names_golden_candidates_v1"


def main():
    con = duckdb.connect(database=":memory:")

    # Extract primary name from JSON wrapper for both sides
    # Names are encoded as {"primary": "Business Name", ...}
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW name_pairs AS
        SELECT
            id,

            -- extracted primary names for readability
            CASE
                WHEN names IS NULL THEN NULL
                WHEN json_valid(names)
                THEN json_extract_string(names, '$.primary')
                ELSE names
            END AS alt_name,

            CASE
                WHEN base_names IS NULL THEN NULL
                WHEN json_valid(base_names)
                THEN json_extract_string(base_names, '$.primary')
                ELSE base_names
            END AS base_name,

            -- raw JSON preserved for reference
            names    AS alt_names_raw,
            base_names AS base_names_raw,

            -- address freeform for labeling context
            CASE
                WHEN json_valid(addresses)
                THEN json_extract_string(addresses, '$[0].freeform')
                ELSE NULL
            END AS alt_address,

            CASE
                WHEN json_valid(base_addresses)
                THEN json_extract_string(base_addresses, '$[0].freeform')
                ELSE NULL
            END AS base_address,

            -- city and state for additional context
            CASE
                WHEN json_valid(addresses)
                THEN json_extract_string(addresses, '$[0].locality')
                ELSE NULL
            END AS city,

            CASE
                WHEN json_valid(addresses)
                THEN json_extract_string(addresses, '$[0].region')
                ELSE NULL
            END AS state,

            -- categories for labeling context
            CASE
                WHEN json_valid(categories)
                THEN json_extract_string(categories, '$.primary')
                ELSE categories
            END AS alt_category,

            CASE
                WHEN json_valid(base_categories)
                THEN json_extract_string(base_categories, '$.primary')
                ELSE base_categories
            END AS base_category,

            -- confidence for reference (row-level signal)
            confidence      AS alt_confidence,
            base_confidence AS base_confidence

        FROM '{PARQUET_PATH}'
        WHERE names IS NOT NULL AND base_names IS NOT NULL;
    """)

    # Normalized name for conflict detection
    # Exclude casing-only and whitespace-only conflicts from the conflict pool
    # so the sample contains genuine disagreements only
    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW name_pairs_norm AS
        SELECT *,
            lower(trim(regexp_replace(alt_name,  '\s+', ' ', 'g'))) AS alt_norm,
            lower(trim(regexp_replace(base_name, '\s+', ' ', 'g'))) AS base_norm
        FROM name_pairs;
    """)

    con.execute(f"""
        COPY (
            -- CONFLICT sample: names differ even after lowercase + whitespace normalization
            (
                SELECT
                    id,
                    alt_name,
                    base_name,
                    alt_address,
                    base_address,
                    city,
                    state,
                    alt_category,
                    base_category,
                    alt_confidence,
                    base_confidence,
                    'conflict' AS sample_type,
                    ''         AS label,
                    ''         AS reason
                FROM name_pairs_norm
                WHERE alt_norm != base_norm
                ORDER BY hash(id || '{SALT}')
                LIMIT {N_CONFLICTS}
            )
            UNION ALL
            -- MATCH sample: names are identical after normalization
            (
                SELECT
                    id,
                    alt_name,
                    base_name,
                    alt_address,
                    base_address,
                    city,
                    state,
                    alt_category,
                    base_category,
                    alt_confidence,
                    base_confidence,
                    'match'    AS sample_type,
                    ''         AS label,
                    ''         AS reason
                FROM name_pairs_norm
                WHERE alt_norm = base_norm
                ORDER BY hash(id || '{SALT}')
                LIMIT {N_MATCHES}
            )
        )
        TO '{OUTPUT_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    con.close()
    print(f"Name sample (pending manual labeling) written to {OUTPUT_PATH}")
    print(f"  Conflicts: {N_CONFLICTS}")
    print(f"  Matches:   {N_MATCHES}")
    print(f"  Total:     {N_CONFLICTS + N_MATCHES}")
    print(f"  Note: conflicts exclude casing-only and whitespace-only differences")


if __name__ == "__main__":
    main()