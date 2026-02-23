import duckdb

PARQUET_PATH = "../data/raw/project_a_samples.parquet"
OUTPUT_PATH = "../analysis/phones/phone_normalization_impact_staged.csv"
OUTPUT_CONFLICTS_PATH = "../analysis/phones/phone_remaining_conflicts.csv"

# Null-like sentinel values to normalize to true NULL
NULL_SENTINELS = ('[null]', '[""]', '["NULL"]', '["null"]', '')


def main():
    """
    Purpose:
      Measure how conflict drops as we apply progressively stronger, *dataset-driven* normalizations.

    Stages (monotonic: each stage keeps previous logic and adds one more equivalence rule):

      S0 null_normalization:
        unify [null], [""], ["NULL"], ["null"], SQL NULL, '' -> true NULL
        (this stage only affects usability; conflict_count is not meaningful here)

      S1 raw_string:
        alt_raw != base_raw (string compare) on both-usable rows

      S2 digits_only:
        strip ALL non-digits, compare digits exactly

      S3 us_11v10_leading1:
        keep S2, plus treat equal if one side is 11 digits starting with '1' and the other is 10 digits,
        and dropping the leading '1' from the 11-digit side makes them match

      S4 generic_1digit_cc:
        keep S3, plus treat equal if one side is exactly 1 digit longer than the other,
        and dropping the leading digit from the longer side makes them match.
        (Incremental impact is non-US 1-digit CCs like +7)

      S5 trunk0_vs_cc2:
        keep S4, plus treat equal if one side starts with '0' and the other has a 2-digit prefix,
        and comparing: drop leading '0' from the trunk side AND drop first 2 digits from the other side

      S6 trunk0_vs_cc3:
        keep S5, plus same idea but with a 3-digit prefix, i.e., drop '0' vs drop first 3 digits

      S7 cc2_vs_national:
        keep S6, plus treat equal if one side is exactly 2 digits longer and dropping the first 2 digits matches

      S8 cc3_vs_national:
        keep S7, plus treat equal if one side is exactly 3 digits longer and dropping the first 3 digits matches

    Notes:
      - Conflicts/rates are restricted to rows where BOTH sides are usable:
          usable := at least 1 digit after stripping non-digits
      - This is intentionally region-agnostic (no default country assumptions).
    """

    con = duckdb.connect(database=":memory:")

    # Register sentinel list as a DuckDB table for clean SQL
    con.execute("CREATE OR REPLACE TEMP TABLE null_sentinels (val VARCHAR)")
    for s in NULL_SENTINELS:
        con.execute("INSERT INTO null_sentinels VALUES (?)", [s])

    # ── S0: unify null-like encodings ──────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW phone_pairs_raw AS
        SELECT
            id,
            phones AS alt_raw_original,
            base_phones AS base_raw_original,

            CASE
                WHEN phones IS NULL OR phones IN (SELECT val FROM null_sentinels)
                THEN NULL ELSE phones
            END AS alt_raw,

            CASE
                WHEN base_phones IS NULL OR base_phones IN (SELECT val FROM null_sentinels)
                THEN NULL ELSE base_phones
            END AS base_raw
        FROM '{PARQUET_PATH}';
    """)

    # Usability before/after null normalization (denominator context)
    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW s0_counts AS
        SELECT
            COUNT(*) AS total_rows,

            SUM(CASE WHEN alt_raw_original IS NOT NULL
                      AND length(regexp_replace(coalesce(alt_raw_original, ''), '\D', '', 'g')) > 0
                      AND base_raw_original IS NOT NULL
                      AND length(regexp_replace(coalesce(base_raw_original, ''), '\D', '', 'g')) > 0
                 THEN 1 ELSE 0 END) AS both_usable_before_null_norm,

            SUM(CASE WHEN alt_raw IS NOT NULL
                      AND length(regexp_replace(coalesce(alt_raw, ''), '\D', '', 'g')) > 0
                      AND base_raw IS NOT NULL
                      AND length(regexp_replace(coalesce(base_raw, ''), '\D', '', 'g')) > 0
                 THEN 1 ELSE 0 END) AS both_usable_after_null_norm
        FROM phone_pairs_raw;
    """)

    # ── Base extraction: raw and digits-only ───────────────────────────
    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW phone_pairs AS
        SELECT
            id,
            alt_raw,
            base_raw,
            regexp_replace(coalesce(alt_raw, ''), '\D', '', 'g') AS alt_digits,
            regexp_replace(coalesce(base_raw, ''), '\D', '', 'g') AS base_digits
        FROM phone_pairs_raw;
    """)

    # ── Flags + equality tests (per-stage add-ons) ─────────────────────
    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW phone_pairs_flags AS
        SELECT
            *,
            (length(alt_digits) > 0) AS alt_usable,
            (length(base_digits) > 0) AS base_usable,
            (length(alt_digits) > 0 AND length(base_digits) > 0) AS both_usable,

            -- S2: digits-only exact equality
            (alt_digits = base_digits) AS eq_s2_digits_exact,

            -- S3: US-style 11-digit leading '1' vs 10-digit
            (
              (length(alt_digits) = 11 AND substr(alt_digits, 1, 1) = '1'
               AND length(base_digits) = 10 AND substr(alt_digits, 2) = base_digits)
              OR
              (length(base_digits) = 11 AND substr(base_digits, 1, 1) = '1'
               AND length(alt_digits) = 10 AND substr(base_digits, 2) = alt_digits)
            ) AS eq_s3_us_11v10,

            -- S4: generic 1-digit CC (one side exactly 1 digit longer; drop leading digit matches)
            (
              (length(alt_digits) = length(base_digits) + 1 AND substr(alt_digits, 2) = base_digits)
              OR
              (length(base_digits) = length(alt_digits) + 1 AND substr(base_digits, 2) = alt_digits)
            ) AS eq_s4_generic_1cc,

            -- S5: trunk '0' vs 2-digit prefix
            (
              (length(alt_digits) >= 3 AND length(base_digits) >= 2
               AND substr(base_digits, 1, 1) = '0'
               AND length(alt_digits) = length(base_digits) + 1
               AND substr(alt_digits, 3) = substr(base_digits, 2))
              OR
              (length(base_digits) >= 3 AND length(alt_digits) >= 2
               AND substr(alt_digits, 1, 1) = '0'
               AND length(base_digits) = length(alt_digits) + 1
               AND substr(base_digits, 3) = substr(alt_digits, 2))
            ) AS eq_s5_trunk0_vs_cc2,

            -- S6: trunk '0' vs 3-digit prefix
            (
              (length(alt_digits) >= 4 AND length(base_digits) >= 2
               AND substr(base_digits, 1, 1) = '0'
               AND length(alt_digits) = length(base_digits) + 2
               AND substr(alt_digits, 4) = substr(base_digits, 2))
              OR
              (length(base_digits) >= 4 AND length(alt_digits) >= 2
               AND substr(alt_digits, 1, 1) = '0'
               AND length(base_digits) = length(alt_digits) + 2
               AND substr(base_digits, 4) = substr(alt_digits, 2))
            ) AS eq_s6_trunk0_vs_cc3,

            -- S7: cc2 vs national (NOT trunk-gated): drop first 2 digits from longer side
            (
              (length(alt_digits) >= 3 AND length(base_digits) >= 1
               AND length(alt_digits) = length(base_digits) + 2
               AND substr(alt_digits, 3) = base_digits)
              OR
              (length(base_digits) >= 3 AND length(alt_digits) >= 1
               AND length(base_digits) = length(alt_digits) + 2
               AND substr(base_digits, 3) = alt_digits)
            ) AS eq_s7_cc2_vs_national,

            -- S8: cc3 vs national (NOT trunk-gated): drop first 3 digits from longer side
            (
              (length(alt_digits) >= 4 AND length(base_digits) >= 1
               AND length(alt_digits) = length(base_digits) + 3
               AND substr(alt_digits, 4) = base_digits)
              OR
              (length(base_digits) >= 4 AND length(alt_digits) >= 1
               AND length(base_digits) = length(alt_digits) + 3
               AND substr(base_digits, 4) = alt_digits)
            ) AS eq_s8_cc3_vs_national,
            
            -- S9: cc2+0+national vs cc2+national (extra 0 right after CC2)
            (
              (length(alt_digits) = length(base_digits) + 1
               AND substr(alt_digits, 3, 1) = '0'
               AND substr(alt_digits, 1, 2) = substr(base_digits, 1, 2)
               AND substr(alt_digits, 4) = substr(base_digits, 3))
              OR
              (length(base_digits) = length(alt_digits) + 1
               AND substr(base_digits, 3, 1) = '0'
               AND substr(base_digits, 1, 2) = substr(alt_digits, 1, 2)
               AND substr(base_digits, 4) = substr(alt_digits, 3))
            ) AS eq_s9_cc2_then0_vs_cc2,
        FROM phone_pairs;
    """)

    # ── Progressive equalities (monotonic) ─────────────────────────────
    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW phone_pairs_staged AS
        SELECT
            *,
            eq_s2_digits_exact AS eq_stage2,
            (eq_s2_digits_exact OR eq_s3_us_11v10) AS eq_stage3,
            (eq_s2_digits_exact OR eq_s3_us_11v10 OR eq_s4_generic_1cc) AS eq_stage4,
            (eq_s2_digits_exact OR eq_s3_us_11v10 OR eq_s4_generic_1cc OR eq_s5_trunk0_vs_cc2) AS eq_stage5,
            (eq_s2_digits_exact OR eq_s3_us_11v10 OR eq_s4_generic_1cc OR eq_s5_trunk0_vs_cc2 OR eq_s6_trunk0_vs_cc3) AS eq_stage6,
            (eq_s2_digits_exact OR eq_s3_us_11v10 OR eq_s4_generic_1cc OR eq_s5_trunk0_vs_cc2 OR eq_s6_trunk0_vs_cc3 OR eq_s7_cc2_vs_national) AS eq_stage7,
            (eq_s2_digits_exact OR eq_s3_us_11v10 OR eq_s4_generic_1cc OR eq_s5_trunk0_vs_cc2 OR eq_s6_trunk0_vs_cc3 OR eq_s7_cc2_vs_national OR eq_s8_cc3_vs_national) AS eq_stage8,
            (eq_s2_digits_exact OR eq_s3_us_11v10 OR eq_s4_generic_1cc OR eq_s5_trunk0_vs_cc2 OR eq_s6_trunk0_vs_cc3 OR eq_s7_cc2_vs_national OR eq_s8_cc3_vs_national OR eq_s9_cc2_then0_vs_cc2) AS eq_stage9
        FROM phone_pairs_flags;
    """)

    # ── Output: staged impact summary ──────────────────────────────────
    con.execute(f"""
        COPY (
            WITH s0 AS (
                SELECT * FROM s0_counts
            ),
            base AS (
                SELECT
                    SUM(CASE WHEN both_usable THEN 1 ELSE 0 END) AS both_usable_count,

                    -- S1: raw conflict (strings) measured only where both usable
                    SUM(CASE WHEN both_usable AND alt_raw != base_raw THEN 1 ELSE 0 END) AS conflict_s1_raw,

                    -- S2+: conflicts are "NOT equal under stage rule"
                    SUM(CASE WHEN both_usable AND NOT eq_stage2 THEN 1 ELSE 0 END) AS conflict_s2,
                    SUM(CASE WHEN both_usable AND NOT eq_stage3 THEN 1 ELSE 0 END) AS conflict_s3,
                    SUM(CASE WHEN both_usable AND NOT eq_stage4 THEN 1 ELSE 0 END) AS conflict_s4,
                    SUM(CASE WHEN both_usable AND NOT eq_stage5 THEN 1 ELSE 0 END) AS conflict_s5,
                    SUM(CASE WHEN both_usable AND NOT eq_stage6 THEN 1 ELSE 0 END) AS conflict_s6,
                    SUM(CASE WHEN both_usable AND NOT eq_stage7 THEN 1 ELSE 0 END) AS conflict_s7,
                    SUM(CASE WHEN both_usable AND NOT eq_stage8 THEN 1 ELSE 0 END) AS conflict_s8,
                    SUM(CASE WHEN both_usable AND NOT eq_stage9 THEN 1 ELSE 0 END) AS conflict_s9
                FROM phone_pairs_staged
            ),
            stages AS (
                SELECT
                    'S0_null_normalization' AS stage,
                    'unify [null], [""], ["NULL"], ["null"], SQL NULL, "" -> NULL; report usable before/after' AS definition,
                    both_usable_after_null_norm AS both_usable_count,
                    NULL::BIGINT AS conflict_count,
                FROM s0

                UNION ALL
                SELECT
                    'S1_raw_string',
                    'raw string compare (alt_raw != base_raw)',
                    both_usable_count,
                    conflict_s1_raw,
                FROM base

                UNION ALL
                SELECT
                    'S2_digits_only',
                    'strip non-digits; exact digits match',
                    both_usable_count,
                    conflict_s2,
                FROM base

                UNION ALL
                SELECT
                    'S3_us_11v10_leading1',
                    'S2 + treat equal if 11 digits starting 1 vs 10 digits (drop leading 1)',
                    both_usable_count,
                    conflict_s3,
                FROM base

                UNION ALL
                SELECT
                    'S4_generic_1digit_cc',
                    'S3 + generic: one side 1 digit longer, drop leading digit matches',
                    both_usable_count,
                    conflict_s4,
                FROM base

                UNION ALL
                SELECT
                    'S5_trunk0_vs_cc2',
                    'S4 + if one starts 0 and other has 2-digit prefix: compare drop0 vs drop2',
                    both_usable_count,
                    conflict_s5,
                FROM base

                UNION ALL
                SELECT
                    'S6_trunk0_vs_cc3',
                    'S5 + if one starts 0 and other has 3-digit prefix: compare drop0 vs drop3',
                    both_usable_count,
                    conflict_s6,
                FROM base

                UNION ALL
                SELECT
                    'S7_cc2_vs_national',
                    'S6 + drop 2-digit prefix from longer side; compare remaining to shorter (no trunk gating)',
                    both_usable_count,
                    conflict_s7,
                FROM base

                UNION ALL
                SELECT
                    'S8_cc3_vs_national',
                    'S7 + drop 3-digit prefix from longer side; compare remaining to shorter (no trunk gating)',
                    both_usable_count,
                    conflict_s8,
                FROM base
                
                UNION ALL
                SELECT
                  'S9_cc2_then0_vs_cc2',
                  'S8 + if one is CC2+0+national and other is CC2+national (extra 0 after CC2)',
                  both_usable_count,
                  conflict_s9
                FROM base
            )
            SELECT
                stage,
                definition,
                both_usable_count,
                conflict_count,
                ROUND(
                    CASE
                        WHEN both_usable_count = 0 OR conflict_count IS NULL THEN NULL
                        ELSE conflict_count::DOUBLE / both_usable_count * 100
                    END
                , 2) AS conflict_rate_pct,
                ROUND(
                    CASE
                        WHEN lag(conflict_count) OVER (ORDER BY stage) IS NULL THEN NULL
                        WHEN conflict_count IS NULL THEN NULL
                        WHEN lag(conflict_count) OVER (ORDER BY stage) = 0 THEN 0
                        ELSE (lag(conflict_count) OVER (ORDER BY stage) - conflict_count)::DOUBLE
                             / lag(conflict_count) OVER (ORDER BY stage) * 100
                    END
                , 2) AS improvement_vs_prev_pct
            FROM stages
            ORDER BY stage
        )
        TO '{OUTPUT_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    # ── Output: remaining conflicts after final stage (S9) ─────────────
    con.execute(f"""
        COPY (
            SELECT
                id,
                CASE
                    WHEN alt_usable AND base_usable THEN 'both_present'
                    WHEN alt_usable AND NOT base_usable THEN 'alt_only'
                    WHEN NOT alt_usable AND base_usable THEN 'base_only'
                END AS conflict_type,
                alt_raw,
                base_raw,
                alt_digits,
                base_digits,
                length(alt_digits) AS alt_digit_len,
                length(base_digits) AS base_digit_len
            FROM phone_pairs_staged
            WHERE
                -- both present but genuinely different after all normalization
                (both_usable AND NOT eq_stage9)
                -- one-sided: one has data, other is missing
                OR (alt_usable AND NOT base_usable)
                OR (base_usable AND NOT alt_usable)
            ORDER BY conflict_type, alt_digit_len, base_digit_len, id
        )
        TO '{OUTPUT_CONFLICTS_PATH}'
        WITH (HEADER, DELIMITER ',')
    """)

    con.close()
    print(f"Wrote staged normalization impact to {OUTPUT_PATH}")
    print(f"Wrote remaining conflicts to {OUTPUT_CONFLICTS_PATH}")


if __name__ == "__main__":
    main()