"""
09_name_normalization.py — Monotonic staged name normalization

Purpose:
    Apply progressively stronger normalization rules to primary name conflicts
    and measure how apparent conflict drops at each stage. This is the name
    equivalent of 06_phone_normalization.py for phones.

    Unlike 08_name_structure.py (which classifies each row into a single tier),
    this script builds a cumulative pipeline: each stage includes all prior stages,
    and conflict count can only decrease (monotonic). The output is a staircase
    showing how much disagreement each normalization rule resolves.

Stages:
    S0  Raw primary name comparison (baseline)
    S1  Casing normalization (lowercase)
    S2  Unicode normalization (NFKD→NFC fullwidth, strip Latin diacritics)
    S3  Punctuation stripping (dashes, dots, quotes, nakaguro, symbols)
    S4  Space normalization (collapse and strip all whitespace)
    S5  Conjunction normalization (&/and/et/und/y/e unified)
    S6  Spelling normalization (British → American)
    S7  Script-form normalization (katakana → hiragana)
    S8  Word reorder (sorted characters, builds on S7)
    S9  Typo detection (Levenshtein ≤ 2, similarity ≥ 0.85)

    After S9, subset detection identifies rows where one normalized name
    contains the other. These are not "resolved" in the same sense as
    normalization — they are a separate class requiring policy decisions.

Architecture:
    Python handles all normalization (reusing functions from 08_name_structure.py).
    DuckDB handles parquet extraction and CSV output.

Outputs:
    name_normalization_staged.csv         Conflict count/rate at each stage
    name_remaining_conflicts.csv          Rows still conflicting after all stages,
                                          with conflict_type: normalized | subset | different
"""

import re
import unicodedata
import duckdb
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────

PARQUET_PATH = "../data/raw/project_a_samples.parquet"

OUTPUT_STAGED_PATH     = "../analysis/names/name_normalization_staged.csv"
OUTPUT_REMAINING_PATH  = "../analysis/names/name_remaining_conflicts.csv"


# ══════════════════════════════════════════════════════════════════════════════
#  NORMALIZERS (same implementations as 08_name_structure.py)
# ══════════════════════════════════════════════════════════════════════════════


def strip_fullwidth(s: str) -> str:
    """NFKD→NFC: fullwidth → halfwidth (ａ→a, U+3000→U+0020)."""
    if not isinstance(s, str):
        return s
    return unicodedata.normalize("NFC", unicodedata.normalize("NFKD", s))


def strip_accents_py(s: str) -> str:
    """Strip only Latin combining diacritical marks (U+0300..U+036F).
    Preserves Japanese dakuten, Thai tone marks, and all other script marks."""
    if not isinstance(s, str):
        return s
    filtered = []
    for c in unicodedata.normalize("NFD", s):
        if unicodedata.combining(c):
            cp = ord(c)
            if 0x0300 <= cp <= 0x036F or 0x1DC0 <= cp <= 0x1DFF:
                continue
        filtered.append(c)
    return unicodedata.normalize("NFC", "".join(filtered))


def _strip_punct_symbols(s: str) -> str:
    """Keep L (Letter), N (Number), M (Mark), whitespace. Strip P and S."""
    return ''.join(c for c in s
                   if unicodedata.category(c)[0] in ('L', 'N', 'M')
                   or c in (' ', '\t', '\n'))


def kata_to_hira(s: str) -> str:
    """Katakana → hiragana: ァ..ヶ → ぁ..ゖ."""
    if not isinstance(s, str):
        return s
    return ''.join(
        chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c
        for c in s
    )


BRITISH_AMERICAN = {
    "centre": "center", "theatre": "theater", "colour": "color",
    "honour": "honor", "favour": "favor", "neighbour": "neighbor",
    "labour": "labor", "programme": "program", "fibre": "fiber",
    "metre": "meter", "litre": "liter", "analyse": "analyze",
    "organisation": "organization", "recognise": "recognize",
    "specialise": "specialize", "defence": "defense", "licence": "license",
    "practise": "practice", "catalogue": "catalog", "cheque": "check",
    "kerb": "curb", "tyre": "tire", "ageing": "aging",
    "fulfil": "fulfill", "traveller": "traveler", "cancelled": "canceled",
    "modelling": "modeling",
}


def levenshtein(a: str, b: str) -> int:
    """Standard DP Levenshtein. O(len(a)*len(b)) time, O(len(b)) space."""
    if len(a) < len(b):
        return levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def is_typo(a: str, b: str) -> bool:
    """True if Levenshtein ≤ 2 and similarity ≥ 0.85, both ≥ 5 chars."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    if len(a) < 5 or len(b) < 5:
        return False
    dist = levenshtein(a, b)
    if dist > 2:
        return False
    return (1 - dist / max(len(a), len(b))) >= 0.85


# ══════════════════════════════════════════════════════════════════════════════
#  STAGED NORMALIZATION — each stage builds on the prior
# ══════════════════════════════════════════════════════════════════════════════
#
# Each stage function takes a string and returns the normalized form for that
# stage. Stages are cumulative: stage N applies stage N-1 first, then its own
# transformation. This guarantees monotonicity.


def s0_raw(s: str) -> str:
    """S0: Raw — no transformation."""
    return s if isinstance(s, str) else ''


def s1_casing(s: str) -> str:
    """S1: Lowercase."""
    return s0_raw(s).lower()


def s2_unicode(s: str) -> str:
    """S2: Fullwidth→ASCII, strip Latin diacritics."""
    return strip_accents_py(strip_fullwidth(s1_casing(s)))


def s3_punctuation(s: str) -> str:
    """S3: Strip punctuation and symbols (preserve letters, numbers, marks, whitespace)."""
    s = s2_unicode(s)
    s = _strip_punct_symbols(s)
    return re.sub(r'\s+', ' ', s).strip()


def s4_spacing(s: str) -> str:
    """S4: Strip all whitespace."""
    return s3_punctuation(s).replace(' ', '')


def s5_conjunction(s: str) -> str:
    """S5: Unify conjunctions before space-stripping.
    Applied on top of S3 (not S4) because conjunction detection needs word
    boundaries. Then space-stripped for comparison."""
    s = s3_punctuation(s)
    # & was already stripped by S3 punctuation, so we need to handle it
    # differently: apply conjunction normalization on the S2 form (pre-punct-strip),
    # then strip punctuation and spaces.
    return s4_spacing(s)


def s5_conjunction_form(s: str) -> str:
    """S5 actual: conjunction normalization needs to run before punct stripping.
    This is the full S5 pipeline: S2 → & → and → strip punct → strip spaces."""
    s = s2_unicode(s)
    s = re.sub(r'&', ' and ', s)
    s = _strip_punct_symbols(s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\b(and|et|und)\b', 'and', s)
    s = re.sub(r'(?<= )y(?= )', 'and', s)
    s = re.sub(r'(?<= )e(?= )', 'and', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s.replace(' ', '')


def s6_spelling_form(s: str) -> str:
    """S6 actual: conjunction → spelling → space-stripped."""
    s = s2_unicode(s)
    s = re.sub(r'&', ' and ', s)
    s = _strip_punct_symbols(s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\b(and|et|und)\b', 'and', s)
    s = re.sub(r'(?<= )y(?= )', 'and', s)
    s = re.sub(r'(?<= )e(?= )', 'and', s)
    # Spelling normalization (needs word boundaries, so before space-strip)
    for british, american in BRITISH_AMERICAN.items():
        s = re.sub(r'\b' + british + r'\b', american, s)
    return s.replace(' ', '')


def s7_hira_form(s: str) -> str:
    """S7: Katakana→hiragana BEFORE sorting.
    Must come before word-reorder so that ハナコ and はなこ are the same
    characters when sorted. Builds on S6 (all prior normalizations)."""
    s = kata_to_hira(s) if isinstance(s, str) else ''
    s = s2_unicode(s)
    s = re.sub(r'&', ' and ', s)
    s = _strip_punct_symbols(s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\b(and|et|und)\b', 'and', s)
    s = re.sub(r'(?<= )y(?= )', 'and', s)
    s = re.sub(r'(?<= )e(?= )', 'and', s)
    for british, american in BRITISH_AMERICAN.items():
        s = re.sub(r'\b' + british + r'\b', american, s)
    return s.replace(' ', '')


def s8_reorder_form(s: str) -> str:
    """S8: Sort all characters AFTER katakana→hiragana.
    Builds on S7 so that ハナコ and はなこ have already been unified
    before sorting. This ensures monotonicity — S7's hiragana gains
    are preserved, and sorting adds its own gains on top."""
    return ''.join(sorted(s7_hira_form(s)))


def _check_subset(a: str, b: str) -> bool:
    """True if one string is contained in the other (and they differ)."""
    if not a or not b or a == b or len(a) == len(b):
        return False
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return short in long


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    con = duckdb.connect(database=":memory:")

    # ── Extract primary names from parquet ─────────────────────
    raw = con.execute(f"""
        SELECT
            id,
            CASE WHEN json_valid(names)
                 THEN json_extract_string(names, '$.primary')
                 ELSE names END                                     AS alt_name,
            CASE WHEN json_valid(base_names)
                 THEN json_extract_string(base_names, '$.primary')
                 ELSE base_names END                                AS base_name,
            CASE WHEN json_valid(addresses)
                 THEN json_extract_string(addresses, '$[0].freeform')
                 ELSE NULL END                                      AS alt_address,
            CASE WHEN json_valid(base_addresses)
                 THEN json_extract_string(base_addresses, '$[0].freeform')
                 ELSE NULL END                                      AS base_address,
            CASE WHEN json_valid(addresses)
                 THEN json_extract_string(addresses, '$[0].locality')
                 ELSE NULL END                                      AS city,
            CASE WHEN json_valid(addresses)
                 THEN json_extract_string(addresses, '$[0].region')
                 ELSE NULL END                                      AS state,
            CASE WHEN json_valid(categories)
                 THEN json_extract_string(categories, '$.primary')
                 ELSE categories END                                AS alt_category,
            CASE WHEN json_valid(base_categories)
                 THEN json_extract_string(base_categories, '$.primary')
                 ELSE base_categories END                           AS base_category,
            confidence                                              AS alt_confidence,
            base_confidence                                         AS base_confidence,
            sources                                                 AS alt_sources,
            base_sources                                            AS base_sources
        FROM '{PARQUET_PATH}'
        WHERE names IS NOT NULL AND base_names IS NOT NULL
    """).df()

    total_rows = len(raw)
    print(f"Total rows with names on both sides: {total_rows}")

    # ── Apply each stage and compute normalized forms ──────────
    df = raw.copy()

    # S0: Raw
    df['s0_alt'] = df['alt_name'].apply(s0_raw)
    df['s0_base'] = df['base_name'].apply(s0_raw)

    # S1: Casing
    df['s1_alt'] = df['alt_name'].apply(s1_casing)
    df['s1_base'] = df['base_name'].apply(s1_casing)

    # S2: Unicode (fullwidth + diacritics)
    df['s2_alt'] = df['alt_name'].apply(s2_unicode)
    df['s2_base'] = df['base_name'].apply(s2_unicode)

    # S3: Punctuation
    df['s3_alt'] = df['alt_name'].apply(s3_punctuation)
    df['s3_base'] = df['base_name'].apply(s3_punctuation)

    # S4: Space-stripped
    df['s4_alt'] = df['alt_name'].apply(s4_spacing)
    df['s4_base'] = df['base_name'].apply(s4_spacing)

    # S5: Conjunction
    df['s5_alt'] = df['alt_name'].apply(s5_conjunction_form)
    df['s5_base'] = df['base_name'].apply(s5_conjunction_form)

    # S6: Spelling
    df['s6_alt'] = df['alt_name'].apply(s6_spelling_form)
    df['s6_base'] = df['base_name'].apply(s6_spelling_form)

    # S7: Word reorder (sorted characters after all normalization)
    # S7: Katakana→hiragana (must come before sorting)
    df['s7_alt'] = df['alt_name'].apply(s7_hira_form)
    df['s7_base'] = df['base_name'].apply(s7_hira_form)

    # S8: Word reorder (sorted characters, builds on S7 hiragana)
    df['s8_alt'] = df['alt_name'].apply(s8_reorder_form)
    df['s8_base'] = df['base_name'].apply(s8_reorder_form)

    # ── Count conflicts at each stage ──────────────────────────
    stages = []
    stage_defs = [
        ('S0', 'Raw primary name comparison',   's0_alt', 's0_base'),
        ('S1', 'Casing (lowercase)',             's1_alt', 's1_base'),
        ('S2', 'Unicode (fullwidth + diacritics)', 's2_alt', 's2_base'),
        ('S3', 'Punctuation stripped',           's3_alt', 's3_base'),
        ('S4', 'Spaces stripped',                's4_alt', 's4_base'),
        ('S5', 'Conjunctions unified',           's5_alt', 's5_base'),
        ('S6', 'Spelling normalized',            's6_alt', 's6_base'),
        ('S7', 'Katakana→hiragana',              's7_alt', 's7_base'),
        ('S8', 'Word reorder (sorted)',          's8_alt', 's8_base'),
    ]

    prev_conflicts = None
    for stage_name, rule, alt_col, base_col in stage_defs:
        conflicts = (df[alt_col] != df[base_col]).sum()
        conflict_rate = round(conflicts / total_rows * 100, 2)
        improvement = ''
        if prev_conflicts is not None and prev_conflicts > 0:
            improvement = round((prev_conflicts - conflicts) / prev_conflicts * 100, 2)
        stages.append({
            'stage': stage_name,
            'rule': rule,
            'conflict_count': conflicts,
            'conflict_rate_pct': conflict_rate,
            'improvement_vs_prior_pct': improvement,
        })
        prev_conflicts = conflicts

    # S9: Typo (Levenshtein) — compare on S7 forms (readable, unsorted)
    # Rows still conflicting at S8 are checked for typos on their S7 forms,
    # because Levenshtein on sorted characters is linguistically meaningless.
    # Any row matching at S8 (sorted) already matches at S7 too (monotonicity),
    # so the conflict set is the same.
    s8_conflicts_mask = df['s8_alt'] != df['s8_base']
    s8_conflict_count = s8_conflicts_mask.sum()

    typo_matches = df[s8_conflicts_mask].apply(
        lambda r: is_typo(r['s7_alt'], r['s7_base']), axis=1)
    typo_resolved = typo_matches.sum()
    s9_conflicts = s8_conflict_count - typo_resolved
    s9_rate = round(s9_conflicts / total_rows * 100, 2)
    s9_improvement = round(typo_resolved / s8_conflict_count * 100, 2) if s8_conflict_count > 0 else 0

    stages.append({
        'stage': 'S9',
        'rule': 'Typo detection (Levenshtein ≤ 2)',
        'conflict_count': s9_conflicts,
        'conflict_rate_pct': s9_rate,
        'improvement_vs_prior_pct': s9_improvement,
    })

    # ── Subset detection on remaining conflicts ────────────────
    # S8 (sorted) is used to determine normalization-equivalence.
    # S7 (hiragana, unsorted) is used for subset detection and display,
    # because sorting destroys substring containment.
    # S4 (space-stripped, no hiragana) is also checked for subset, matching
    # the 08_name_structure.py approach of checking multiple forms.

    df['final_norm_alt'] = df['s8_alt']     # for normalization match check
    df['final_norm_base'] = df['s8_base']
    df['final_readable_alt'] = df['s7_alt']  # for subset detection + display
    df['final_readable_base'] = df['s7_base']

    # Update typo matches as resolved
    df['typo_resolved'] = False
    if typo_resolved > 0:
        typo_idx = typo_matches[typo_matches].index
        df.loc[typo_idx, 'typo_resolved'] = True

    # Classify remaining conflicts (using S8 sorted for normalization check)
    still_conflict = (df['final_norm_alt'] != df['final_norm_base']) & (~df['typo_resolved'])

    df['conflict_type'] = 'agreement'
    df.loc[still_conflict, 'conflict_type'] = 'different'

    # Check subsets on READABLE forms (S7 hiragana, unsorted) and
    # space-stripped forms (S4) — sorted forms destroy containment
    def _check_any_subset(r):
        """Check substring containment on multiple normalized forms."""
        if _check_subset(r['final_readable_alt'], r['final_readable_base']):
            return True
        if _check_subset(r['s4_alt'], r['s4_base']):
            return True
        return False

    subset_mask = still_conflict & df.apply(_check_any_subset, axis=1)
    df.loc[subset_mask, 'conflict_type'] = 'subset'

    # Rows resolved by normalization (were conflict at S0, now match or typo)
    was_conflict = df['s0_alt'] != df['s0_base']
    normalized_away = was_conflict & ~still_conflict
    df.loc[normalized_away, 'conflict_type'] = 'normalized'

    # Count subsets and remaining different
    subset_count = subset_mask.sum()
    different_count = (df['conflict_type'] == 'different').sum()

    stages.append({
        'stage': 'Subset',
        'rule': 'One normalized name contained in the other',
        'conflict_count': different_count,
        'conflict_rate_pct': round(different_count / total_rows * 100, 2),
        'improvement_vs_prior_pct': round(subset_count / s9_conflicts * 100, 2) if s9_conflicts > 0 else 0,
    })

    # ── Output 1: Staged summary ───────────────────────────────
    staged_df = pd.DataFrame(stages)
    staged_df.to_csv(OUTPUT_STAGED_PATH, index=False)
    print(f"\nWrote: {OUTPUT_STAGED_PATH}")
    print(f"\nStaged normalization results:")
    print(f"{'Stage':<8} {'Rule':<42} {'Conflicts':>10} {'Rate':>8} {'Improv':>8}")
    print("-" * 80)
    for _, row in staged_df.iterrows():
        imp = f"{row['improvement_vs_prior_pct']}%" if row['improvement_vs_prior_pct'] != '' else '—'
        print(f"{row['stage']:<8} {row['rule']:<42} {row['conflict_count']:>10} {row['conflict_rate_pct']:>7}% {imp:>8}")

    # ── Output 2: Remaining conflicts ──────────────────────────
    # Export all rows that were conflicts at S0, with their final status
    remaining = df[was_conflict].copy()

    # Coerce for DuckDB
    for col in remaining.select_dtypes(include=['object', 'str']).columns:
        remaining[col] = remaining[col].astype(pd.StringDtype())

    con.execute("CREATE TABLE remaining AS SELECT * FROM remaining")
    con.execute(f"""
        COPY (
            SELECT
                conflict_type,
                id,
                alt_name,
                base_name,
                s7_alt  AS normalized_alt,
                s7_base AS normalized_base,
                alt_address,
                base_address,
                city,
                state,
                alt_category,
                base_category,
                alt_confidence,
                base_confidence,
                alt_sources,
                base_sources
            FROM remaining
            ORDER BY
                CASE conflict_type
                    WHEN 'normalized' THEN 1
                    WHEN 'subset'     THEN 2
                    WHEN 'different'  THEN 3
                END,
                id
        ) TO '{OUTPUT_REMAINING_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    con.close()

    print(f"\nWrote: {OUTPUT_REMAINING_PATH}")
    norm_count = (df['conflict_type'] == 'normalized').sum()
    print(f"\nSummary of {was_conflict.sum()} original primary-name conflicts:")
    print(f"  Resolved by normalization:  {norm_count}")
    print(f"  Subset (policy decision):   {subset_count}")
    print(f"  Genuinely different:        {different_count}")
    print(f"  Total:                      {norm_count + subset_count + different_count}")


if __name__ == "__main__":
    main()