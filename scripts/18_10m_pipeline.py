"""
18_10m_pipeline.py — Run name normalization pipeline on 10M Overture dataset

Purpose:
    Stress-test the staged normalization pipeline at scale. Preprocesses the
    10M flat record file into base/alt pairs (grouped by shared id), extracts
    primary names, applies the same 9-stage normalization pipeline from script 09,
    and reports conflict distribution.

Input:
    data/raw/terraforma_samples_10M.parquet  (one row per source record)

Output:
    analysis/names/10m_normalization_staged.csv   Per-stage conflict counts
    analysis/names/10m_conflict_summary.csv       Conflict type breakdown
"""

import re
import unicodedata
import pandas as pd
from itertools import combinations

# ── Paths ──────────────────────────────────────────────────────────────────────
PARQUET_PATH  = "../data/raw/terraforma_samples_10M.parquet"
OUT_STAGED    = "../analysis/names/10m_normalization_staged.csv"
OUT_SUMMARY   = "../analysis/names/10m_conflict_summary.csv"

# ══════════════════════════════════════════════════════════════════════════════
#  NORMALIZERS (identical to script 09)
# ══════════════════════════════════════════════════════════════════════════════

def strip_fullwidth(s):
    if not isinstance(s, str): return s
    return unicodedata.normalize("NFC", unicodedata.normalize("NFKD", s))

def strip_accents_py(s):
    if not isinstance(s, str): return s
    filtered = []
    for c in unicodedata.normalize("NFD", s):
        if unicodedata.combining(c):
            cp = ord(c)
            if 0x0300 <= cp <= 0x036F or 0x1DC0 <= cp <= 0x1DFF:
                continue
        filtered.append(c)
    return unicodedata.normalize("NFC", "".join(filtered))

def _strip_punct_symbols(s):
    return ''.join(c for c in s
                   if unicodedata.category(c)[0] in ('L', 'N', 'M')
                   or c in (' ', '\t', '\n'))

def kata_to_hira(s):
    if not isinstance(s, str): return s
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

CONJUNCTIONS = {"&": "and", "et": "and", "und": "and", "y": "and", "e": "and"}

def levenshtein(a, b):
    if len(a) < len(b): return levenshtein(b, a)
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]

def _differs_only_in_digits(a, b):
    if len(a) != len(b):
        short, long = (a, b) if len(a) < len(b) else (b, a)
        long_no = long.rstrip('0123456789')
        return long_no == short or long_no.rstrip() == short.rstrip()
    for ca, cb in zip(a, b):
        if ca != cb and not (ca.isdigit() or cb.isdigit()):
            return False
    return any(ca != cb for ca, cb in zip(a, b))

def is_typo(a, b):
    if not isinstance(a, str) or not isinstance(b, str): return False
    if len(a) < 5 or len(b) < 5: return False
    dist = levenshtein(a, b)
    if dist > 2: return False
    if (1 - dist / max(len(a), len(b))) < 0.85: return False
    if _differs_only_in_digits(a, b): return False
    return True

def s0_raw(s): return s if isinstance(s, str) else ''
def s1_casing(s): return s0_raw(s).lower()
def s2_unicode(s): return strip_accents_py(strip_fullwidth(s1_casing(s)))
def s3_punctuation(s):
    s = s2_unicode(s)
    s = _strip_punct_symbols(s)
    return re.sub(r'\s+', ' ', s).strip()
def s4_spacing(s): return s3_punctuation(s).replace(' ', '')
def s5_conjunction(s):
    s = s3_punctuation(s)
    words = s.split()
    words = [CONJUNCTIONS.get(w, w) for w in words]
    return ''.join(words)
def s6_spelling(s):
    s = s5_conjunction(s)
    words = s.split() if ' ' in s else [s]
    return ' '.join(BRITISH_AMERICAN.get(w, w) for w in words).replace(' ', '')
def s7_script(s): return kata_to_hira(s6_spelling(s))
def s8_reorder(s): return ''.join(sorted(s7_script(s)))

# ══════════════════════════════════════════════════════════════════════════════
#  PREPROCESSING — flat records → base/alt pairs
# ══════════════════════════════════════════════════════════════════════════════

def extract_primary_name(names_val):
    if isinstance(names_val, dict):
        return names_val.get('primary') or ''
    return ''

def build_pairs(df):
    """Group by id, create all pairwise combinations per id."""
    print("Extracting primary names...")
    df['primary_name'] = df['names'].apply(extract_primary_name)
    df = df[df['primary_name'].str.strip() != '']

    print("Grouping by id...")
    groups = df.groupby('id')

    pairs = []
    for place_id, group in groups:
        if len(group) < 2:
            continue
        records = group[['primary_name', 'provider']].values.tolist()
        # All pairwise combinations — covers 3+ source places fully
        for (n1, p1), (n2, p2) in combinations(records, 2):
            pairs.append({
                'id': place_id,
                'base_name': n1,
                'alt_name': n2,
                'base_provider': p1,
                'alt_provider': p2,
            })

    unique_ids = df['id'].nunique()
    print(f"  Built {len(pairs):,} pairs from {unique_ids:,} unique IDs")
    return pd.DataFrame(pairs)

# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE — run staged normalization on pairs
# ══════════════════════════════════════════════════════════════════════════════

STAGES = [
    ('S0', s0_raw),
    ('S1', s1_casing),
    ('S2', s2_unicode),
    ('S3', s3_punctuation),
    ('S4', s4_spacing),
    ('S5', s5_conjunction),
    ('S6', s6_spelling),
    ('S7', s7_script),
    ('S8', s8_reorder),
]

def run_pipeline(pairs_df):
    total = len(pairs_df)
    print(f"\nRunning normalization pipeline on {total:,} pairs...")

    base = pairs_df['base_name'].tolist()
    alt  = pairs_df['alt_name'].tolist()

    remaining = list(range(total))  # indices still conflicting
    staged_results = []

    prev_conflict_count = total

    for stage_name, fn in STAGES:
        norm_base = [fn(base[i]) for i in remaining]
        norm_alt  = [fn(alt[i])  for i in remaining]

        resolved = [i for i, nb, na in zip(remaining, norm_base, norm_alt) if nb == na]
        still_conflicting = [i for i, nb, na in zip(remaining, norm_base, norm_alt) if nb != na]

        conflict_count = len(still_conflicting)
        resolved_at_stage = prev_conflict_count - conflict_count
        pct_of_total = conflict_count / total * 100
        pct_improvement = resolved_at_stage / prev_conflict_count * 100 if prev_conflict_count > 0 else 0

        staged_results.append({
            'stage': stage_name,
            'conflicts_remaining': conflict_count,
            'conflict_rate_pct': round(pct_of_total, 2),
            'resolved_at_stage': resolved_at_stage,
            'pct_improvement': round(pct_improvement, 2),
        })

        print(f"  {stage_name}: {conflict_count:,} remaining ({pct_of_total:.2f}%), "
              f"resolved {resolved_at_stage:,} ({pct_improvement:.2f}%)")

        remaining = still_conflicting
        prev_conflict_count = conflict_count

    # Subset detection on remaining — use s7 normalized form (not s8 char-sort)
    print("  Subset detection...")
    subset_idx = []
    different_idx = []
    for i in remaining:
        nb = s7_script(base[i])
        na = s7_script(alt[i])
        if nb in na or na in nb:
            subset_idx.append(i)
        elif is_typo(nb, na):
            subset_idx.append(i)  # typo variant — treated as normalization-equivalent
        else:
            different_idx.append(i)

    print(f"  Subset: {len(subset_idx):,}, Genuinely different: {len(different_idx):,}")

    # Summary
    agreement = total - prev_conflict_count  # resolved before any normalization...
    # Actually: agreement = pairs where S0 already equal
    s0_norm_base = [s0_raw(b) for b in base]
    s0_norm_alt  = [s0_raw(a) for a in alt]
    agreement_count = sum(1 for nb, na in zip(s0_norm_base, s0_norm_alt) if nb == na)
    conflict_count_raw = total - agreement_count

    summary = {
        'total_pairs': total,
        'agreement': agreement_count,
        'agreement_pct': round(agreement_count / total * 100, 2),
        'raw_conflicts': conflict_count_raw,
        'raw_conflict_rate_pct': round(conflict_count_raw / total * 100, 2),
        'normalization_resolved': conflict_count_raw - prev_conflict_count,
        'subset': len(subset_idx),
        'genuinely_different': len(different_idx),
        'inflation_factor': round(conflict_count_raw / max(len(different_idx), 1), 1),
    }

    return staged_results, summary

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("Loading 10M parquet...")
    df = pd.read_parquet(PARQUET_PATH)
    print(f"  Loaded {len(df):,} records, {df['id'].nunique():,} unique IDs")

    pairs_df = build_pairs(df)

    staged_results, summary = run_pipeline(pairs_df)

    # Save outputs
    staged_df = pd.DataFrame(staged_results)
    staged_df.to_csv(OUT_STAGED, index=False)
    print(f"\nSaved staged results → {OUT_STAGED}")

    summary_df = pd.DataFrame([summary])
    summary_df.to_csv(OUT_SUMMARY, index=False)
    print(f"Saved summary → {OUT_SUMMARY}")

    print("\n── SUMMARY ──────────────────────────────────────────────")
    for k, v in summary.items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
