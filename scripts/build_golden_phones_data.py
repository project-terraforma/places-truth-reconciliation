import duckdb

PARQUET_PATH = "../data/raw/project_a_samples.parquet"
OUTPUT_PATH = "../data/labeled_golden/project_a_labeled_golden_candidates.csv"

# Sampling strategy:
# - deterministic hash-based shuffle
# - population: phone conflicts
# - salt: labeled_golden_candidates_v1
# - sample size: 60 conflicts, 40 matches
N_CONFLICTS = 60
N_MATCHES = 40
SALT = "labeled_golden_candidates_v1"

def main():
    con = duckdb.connect(database=":memory:")

    con.execute(f"""
        COPY (
            (
                SELECT
                    id,
                    phones,
                    base_phones,
                    confidence,
                    base_confidence,
                    '' AS label,
                    '' AS reason
                FROM '{PARQUET_PATH}'
                WHERE
                    phones IS NOT NULL
                    AND base_phones IS NOT NULL
                    AND phones != base_phones
                ORDER BY hash(id || '{SALT}')
                LIMIT {N_CONFLICTS}
            )
            UNION ALL
            (
                SELECT
                    id,
                    phones,
                    base_phones,
                    confidence,
                    base_confidence,
                    '' AS label,
                    '' AS reason
                FROM '{PARQUET_PATH}'
                WHERE
                    phones IS NOT NULL
                    AND base_phones IS NOT NULL
                    AND phones = base_phones
                ORDER BY hash(id || '{SALT}')
                LIMIT {N_MATCHES}
            )
        )
        TO '{OUTPUT_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    con.close()
    print(f"Golden dataset (pending manual labeling) written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()