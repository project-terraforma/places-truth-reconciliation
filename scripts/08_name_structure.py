"""
08_name_structure.py — Name attribute structural analysis (v2)

Purpose:
    Characterize name conflicts between alt and base candidates using a two-tier
    labeling system designed for reconciliation decision-making.

    Tier 1 (relationship type) — mutually exclusive, determines reconciliation action:
        casing_only              Identical after lowercasing.  → Auto-resolve.
        normalization_equivalent Same name after punctuation/spacing/diacritic/
                                 conjunction/spelling/script normalization.  → Auto-resolve.
        subset                   One name is meaningfully contained in the other
                                 (brand vs brand+branch, name vs name+gloss).
                                 → Policy decision.
        genuinely_different      Different names for the same place, or potential
                                 bad match.  → Requires human review / abstention.

    Tier 2 (transformation subtags) — multiple per row, diagnostic:
        For normalization_equivalent:
            punctuation    Dash/dot/apostrophe/quote/nakaguro/parenthesis differences
            spacing        Compound split/join (PhotoColorLab ↔ Photo Color Lab)
            diacritic      Accent differences (Bistrô ↔ Bistro)
            conjunction    &/and/et/und/y/e interchange
            spelling       British/American variants (centre ↔ center)
            word_reorder   Same tokens in different order
            script_form    Katakana ↔ hiragana, small kana normalization
            typo           Levenshtein distance ≤ 2

        For subset:
            branch_suffix      Brand + store/location (very common in JP/TH)
            parenthetical      Name + parenthetical reading/disambiguation
            biz_suffix         Legal suffix added/removed (LLC, GmbH, SRL, ...)
            seo_junk           SEO keywords in the longer name
            descriptor         Additional text describing the business (catch-all)

Critical fix (v2):
    v1 used [^a-zA-Z0-9\\s] in l2() which DESTROYED all non-Latin scripts.
    Every CJK, Thai, Korean, Cyrillic character was stripped, causing:
    - Thai/Japanese/Korean names to collapse to empty strings
    - Substring detection to fail across all non-Latin scripts
    - False "diacritic_variant" labels when "" == ""
    v2 uses Unicode-aware [^\\w\\s] (Python 3 re.UNICODE default) so that
    ALL scripts survive normalization.

Architecture:
    DuckDB:  Parquet extraction, SQL-side feature columns, aggregation, CSV output.
    Python:  Unicode normalization, katakana/hiragana conversion, conjunction/spelling
             normalization, Levenshtein, two-tier classification.  Enriched DataFrame
             is loaded into DuckDB as a table for downstream aggregation.

Outputs:
    name_agreement_breakdown.csv         2000-row funnel: 3 examples per agreement bucket
    name_all_agreements_labeled.csv      All non-conflict rows with agreement type + full JSON
    name_structure_summary.csv           Per-side structure metrics
    name_length_distribution.csv         Character length buckets
    name_wordcount_distribution.csv      Word count distribution
    name_casing_summary.csv              Casing pattern breakdown (conflict rows)
    name_tier1_summary.csv               Tier 1 label counts
    name_subtag_summary.csv              Tier 2 subtag frequency
    name_all_conflicts_labeled.csv       All conflict rows with tier1 + tier2 labels
    name_genuinely_different_inspect.csv Golden dataset population for manual review
"""

import re
import unicodedata
import duckdb
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────

PARQUET_PATH = "../data/raw/project_a_samples.parquet"

OUTPUT_METRICS_PATH                = "../analysis/names/name_structure_summary.csv"
OUTPUT_LENGTH_DISTRIBUTION_PATH    = "../analysis/names/name_length_distribution.csv"
OUTPUT_WORDCOUNT_DISTRIBUTION_PATH = "../analysis/names/name_wordcount_distribution.csv"
OUTPUT_CASING_PATH                 = "../analysis/names/name_casing_summary.csv"
OUTPUT_TIER1_SUMMARY_PATH          = "../analysis/names/name_tier1_summary.csv"
OUTPUT_SUBTAG_SUMMARY_PATH         = "../analysis/names/name_subtag_summary.csv"
OUTPUT_ALL_CONFLICTS_PATH          = "../analysis/names/name_all_conflicts_labeled.csv"
OUTPUT_GENUINELY_DIFFERENT_PATH    = "../analysis/names/name_genuinely_different_inspect.csv"
OUTPUT_AGREEMENT_BREAKDOWN_PATH    = "../analysis/names/name_agreement_breakdown.csv"
OUTPUT_ALL_AGREEMENTS_PATH         = "../analysis/names/name_all_agreements_labeled.csv"


# ══════════════════════════════════════════════════════════════════════════════
#  UNICODE-AWARE NORMALIZERS
# ══════════════════════════════════════════════════════════════════════════════
#
# Key principle: every normalizer must preserve characters from ALL scripts.
# CJK ideographs, Thai, Korean Hangul, Cyrillic, Arabic, Devanagari, etc.
# must survive every transformation that does not specifically target them.


def strip_fullwidth(s: str) -> str:
    """NFKD→NFC: convert fullwidth Latin to halfwidth (ａ→a) while
    preserving accented characters and all non-Latin scripts."""
    if not isinstance(s, str):
        return s
    return unicodedata.normalize("NFC", unicodedata.normalize("NFKD", s))


def strip_accents_py(s: str) -> str:
    """Strip LATIN combining diacritical marks only (é→e, ü→u).

    CRITICAL: The old implementation stripped ALL combining marks, which
    destroyed Japanese dakuten (バ→ハ, ガ→カ) and Thai tone marks (ห้→ห).
    These are linguistically meaningful — not cosmetic accents.

    Fix: only strip marks in U+0300..U+036F (Combining Diacritical Marks)
    and U+1DC0..U+1DFF (supplement).  Japanese U+3099/U+309A, Thai U+0E48+,
    Korean jamo, Arabic diacritics, etc. are all preserved.

    After filtering, NFC recomposition restores surviving combining sequences
    (e.g. NFD ハ+゙ → NFC バ stays intact)."""
    if not isinstance(s, str):
        return s
    filtered = []
    for c in unicodedata.normalize("NFD", s):
        if unicodedata.combining(c):
            cp = ord(c)
            # Only strip Latin/European combining diacritical marks
            if 0x0300 <= cp <= 0x036F or 0x1DC0 <= cp <= 0x1DFF:
                continue
        filtered.append(c)
    # NFC recomposition restores Japanese dakuten etc. that survived
    return unicodedata.normalize("NFC", "".join(filtered))


def l2(s: str) -> str:
    """Lowercase → strip punctuation/symbols → collapse whitespace.

    UNICODE-AWARE (v2 fix): preserves characters from ALL scripts by keeping
    Unicode categories L (Letter), N (Number), M (Mark), and whitespace.
    Strips categories P (Punctuation) and S (Symbol).

    v1 used [^a-zA-Z0-9\\s] which destroyed everything outside ASCII.
    An intermediate fix using [^\\w\\s] still stripped combining marks
    (category M) — losing Thai tone marks (ห้→ห) and Japanese dakuten
    when they appeared as combining characters."""
    if not isinstance(s, str):
        return s
    s = s.lower()
    # Keep: Letters (L*), Numbers (N*), Marks (M* — combining/enclosing),
    #        whitespace.
    # Strip: Punctuation (P*), Symbols (S*), everything else.
    result = []
    for c in s:
        cat = unicodedata.category(c)
        if cat[0] in ('L', 'N', 'M') or c in (' ', '\t', '\n'):
            result.append(c)
    s = ''.join(result)
    return re.sub(r'\s+', ' ', s).strip()


def norm_compare(s: str) -> str:
    """Standard comparison form for name matching.

    Applies three transformations in order:
    1. strip_fullwidth: NFKD→NFC, converts fullwidth chars to ASCII (ａ→a, U+3000→U+0020)
    2. strip_accents_py: removes Latin diacritics (é→e, ü→u), preserves JP/TH/KR marks
    3. l2: lowercases, strips punctuation/symbols, collapses whitespace

    Example: norm_compare("Origen's Bistrô") → "origens bistro"
    Example: norm_compare("ローソン いわき下好間店") → "ローソン いわき下好間店"

    Preserves all scripts; strips only Latin accents and punctuation."""
    return l2(strip_accents_py(strip_fullwidth(s)))


# ── Katakana ↔ Hiragana ───────────────────────────────────────────────────────

def kata_to_hira(s: str) -> str:
    """Convert katakana to hiragana for script-form comparison.
    ァ (U+30A1) .. ヶ (U+30F6) → ぁ (U+3041) .. ゖ (U+3096).
    Leaves everything else untouched (Latin, Thai, CJK ideographs, ...)."""
    if not isinstance(s, str):
        return s
    return ''.join(
        chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c
        for c in s
    )


def norm_compare_hira(s: str) -> str:
    """Katakana→hiragana then norm_compare.  For detecting Japanese script-form
    variants where the same word is written in different kana sets.
    Example: norm_compare_hira("ハナコ") → "はなこ" ← norm_compare_hira("はなこ")"""
    if not isinstance(s, str):
        return s
    return norm_compare(kata_to_hira(s))


# ── Conjunction normalization ──────────────────────────────────────────────────

def _strip_punct_symbols(s: str) -> str:
    """Strip punctuation (P*) and symbol (S*) categories, preserving
    letters, numbers, marks, and whitespace.  Used by norm_conj and l2."""
    return ''.join(c for c in s
                   if unicodedata.category(c)[0] in ('L', 'N', 'M')
                   or c in (' ', '\t', '\n'))


def norm_conj(s: str) -> str:
    """Normalize conjunction variants: & and et und y e → canonical 'and'.

    Order of operations (critical):
    1. Fullwidth + accent normalization FIRST.
    2. & → 'and' BEFORE stripping punctuation (if & is stripped first,
       'Acqua & Sapone' → 'acqua sapone' and the substitution never fires).
    3. Strip remaining punctuation.
    4. Normalize conjunction words.

    'y' and 'e' use strict word-boundary matching to avoid false positives
    inside words (Yelp, every, they, Etcetera, ...)."""
    if not isinstance(s, str):
        return s
    s = strip_accents_py(strip_fullwidth(s)).lower()
    s = re.sub(r'&', ' and ', s)
    s = _strip_punct_symbols(s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\b(and|et|und)\b', 'and', s)
    s = re.sub(r'(?<= )y(?= )', 'and', s)
    s = re.sub(r'(?<= )e(?= )', 'and', s)
    return re.sub(r'\s+', ' ', s).strip()


# ── British → American spelling ────────────────────────────────────────────────

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


def norm_spelling(s: str) -> str:
    """British→American after norm_compare.  Word-boundary matched."""
    if not isinstance(s, str):
        return s
    s = norm_compare(s)
    for british, american in BRITISH_AMERICAN.items():
        s = re.sub(r'\b' + british + r'\b', american, s)
    return s


# ── Levenshtein ────────────────────────────────────────────────────────────────

def levenshtein(a: str, b: str) -> int:
    """Standard DP Levenshtein.  O(len(a)*len(b)) time, O(len(b)) space."""
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


def _differs_only_in_digits(a: str, b: str) -> bool:
    """True if the only character differences between a and b are digit substitutions.
    'Fire Station 5' vs 'Fire Station 1' → True (different numbers, not a typo).
    'Agriturismo' vs 'Agritursmo' → False (letter difference, plausible typo)."""
    if len(a) != len(b):
        # Length differs — check if the inserted/deleted chars are digits
        short, long = (a, b) if len(a) < len(b) else (b, a)
        # Simple heuristic: if removing digits from the longer makes them equal, it's a number difference
        long_no_trailing_digits = long.rstrip('0123456789')
        if long_no_trailing_digits == short or long_no_trailing_digits.rstrip() == short.rstrip():
            return True
        return False
    # Same length: check if every differing position is a digit on at least one side
    has_diff = False
    for ca, cb in zip(a, b):
        if ca != cb:
            has_diff = True
            if not (ca.isdigit() or cb.isdigit()):
                return False  # Non-digit difference → plausible typo
    return has_diff


def is_typo(a: str, b: str) -> bool:
    """True if a and b are typo variants: both ≥ 5 chars, Levenshtein ≤ 2,
    similarity ≥ 0.85. Rejects digit-only differences (different branch numbers
    like 'Fire Station 5' vs 'Fire Station 1' are not typos)."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    if len(a) < 5 or len(b) < 5:
        return False
    dist = levenshtein(a, b)
    if dist > 2:
        return False
    if (1 - dist / max(len(a), len(b))) < 0.85:
        return False
    # Reject if the only differences are digit substitutions/insertions
    if _differs_only_in_digits(a, b):
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 2 SUBTAG DETECTORS
# ══════════════════════════════════════════════════════════════════════════════

# Compiled patterns used by subtag detectors.

_PUNCT_CHARS = re.compile(r'[^\w\s]', re.UNICODE)

_BIZ_SUFFIX_RE = re.compile(
    r',?\s*\b(llc|l\.l\.c\.|inc|inc\.|corp|corp\.|ltd|ltd\.|co\.'
    r'|company|incorporated|gmbh|g\.m\.b\.h\.|ag|sa|sarl|s\.a\.r\.l\.'
    r'|srl|s\.r\.l\.|snc|s\.n\.c\.|sas|s\.a\.s\.|kg|ohg|ug'
    r'|pty|plc|lp|llp|pllc|pa|pc|dba|cpa|dmd|dds|md|do'
    r'|pvt|oy|ab|as|aps|hf|ehf|kft|zrt|sp\.?\s*z\.?\s*o\.?\s*o\.?'
    r'|e\.v\.|mbh)\b\.?\s*$',
    re.IGNORECASE
)

_SEO_RE = re.compile(
    r'(hours|address|near me|official site|official|directions'
    r'|reviews|location|best |menu)',
    re.IGNORECASE
)

# Japanese branch patterns: 店 (store), 支店 (branch), 出張所 (sub-office),
# mall names (イオン, モール), directional suffixes (南店, 北店, 東店, 西店)
_JP_BRANCH_RE = re.compile(r'(店|支店|出張所|営業所|イオン|モール|マルイ)')

# Thai location / descriptor suffixes that indicate a branch listing
_TH_BRANCH_RE = re.compile(r'(สาขา|ถนน|ซอย|ต\.|อ\.|จ\.)')

# Generic English branch/location words
_EN_BRANCH_RE = re.compile(
    r'\b(branch|store|outlet|location|mall|plaza|center|centre)\b',
    re.IGNORECASE
)

# Bus stop / ATM / station suffixes
_FACILITY_SUFFIX_RE = re.compile(
    r'(バス停|bus\s*stop|atm|cash\s*machine|substation)',
    re.IGNORECASE
)


def _get_norm_subtags(row) -> str:
    """Compute Tier 2 subtags for normalization_equivalent rows.
    Each subtag is independently tested; multiple can be true.
    Typo only fires when it is the sole/primary explanation."""
    tags = []
    a_raw, b_raw = row['alt_name'], row['base_name']
    a_l2d, b_l2d = row['alt_l2d'], row['base_l2d']

    # ── Punctuation ────────────────────────────────────────────
    # Difference involves punctuation marks (dashes, dots, nakaguro, etc.)
    a_lower, b_lower = a_raw.lower(), b_raw.lower()
    a_depunct = _PUNCT_CHARS.sub('', a_lower)
    b_depunct = _PUNCT_CHARS.sub('', b_lower)
    if (a_lower != b_lower
            and (a_depunct != a_lower or b_depunct != b_lower)
            and (a_depunct == b_depunct
                 or a_depunct.replace(' ', '') == b_depunct.replace(' ', ''))):
        tags.append('punctuation')

    # ── Diacritic ──────────────────────────────────────────────
    # Accent stripping changes one or both names to make them match.
    a_no_accent = l2(strip_fullwidth(a_raw))   # l2 without accent strip
    b_no_accent = l2(strip_fullwidth(b_raw))
    if a_no_accent != b_no_accent and a_l2d == b_l2d:
        tags.append('diacritic')

    # ── Spacing ────────────────────────────────────────────────
    # Two layers:
    # (a) Whitespace-type variants — fullwidth space (U+3000) vs ASCII space,
    #     tab vs space, double-space vs single-space, etc.  These are erased
    #     by norm_compare (via NFKD + collapse), so a_l2d == b_l2d and the
    #     downstream check (which requires a_l2d != b_l2d) would miss them.
    #     Detected on raw lowered forms before any normalization.
    # (b) Compound split/join — PhotoColorLab ↔ Photo Color Lab.
    #     Detected on norm_compare forms where space-stripped versions match.
    a_ws_norm = re.sub(r'\s+', ' ', a_lower.strip())
    b_ws_norm = re.sub(r'\s+', ' ', b_lower.strip())
    if a_lower != b_lower and a_ws_norm == b_ws_norm:
        tags.append('spacing')
    elif a_l2d != b_l2d and row['alt_nospace'] == row['base_nospace']:
        tags.append('spacing')

    # ── Conjunction ────────────────────────────────────────────
    if a_l2d != b_l2d and row['alt_conj'] == row['base_conj']:
        tags.append('conjunction')

    # ── Spelling ───────────────────────────────────────────────
    if a_l2d != b_l2d and row['alt_spelling'] == row['base_spelling']:
        tags.append('spelling')

    # ── Word reorder ───────────────────────────────────────────
    if a_l2d != b_l2d and row['alt_sorted'] == row['base_sorted']:
        tags.append('word_reorder')

    # ── Script form (katakana ↔ hiragana) ──────────────────────
    if a_l2d != b_l2d and row['alt_hira'] == row['base_hira']:
        tags.append('script_form')

    # ── Typo ───────────────────────────────────────────────────
    # Only tag as typo when no other normalization path already explains
    # the match.  Avoids noise where spacing/punctuation differences also
    # happen to be within Levenshtein threshold.
    if row['is_typo'] and not tags:
        tags.append('typo')

    return ';'.join(tags) if tags else 'minor_variant'


def _get_subset_subtags(row) -> str:
    """Compute Tier 2 subtags for subset rows.
    Identifies what KIND of additional content the longer name carries."""
    tags = []
    a_raw, b_raw = row['alt_name'], row['base_name']
    a_l2d, b_l2d = row['alt_l2d'], row['base_l2d']

    # Identify which side is longer (the one with extra content)
    if len(a_l2d) >= len(b_l2d):
        longer_raw, shorter_raw = a_raw, b_raw
        longer_l2d, shorter_l2d = a_l2d, b_l2d
    else:
        longer_raw, shorter_raw = b_raw, a_raw
        longer_l2d, shorter_l2d = b_l2d, a_l2d

    # The "excess" is the part of the longer name beyond the shorter
    excess = longer_l2d.replace(shorter_l2d, '', 1).strip()

    # ── Parenthetical ──────────────────────────────────────────
    # Longer raw name has parentheses that shorter doesn't.
    has_paren_long = bool(re.search(r'[()（）【】\[\]]', longer_raw))
    has_paren_short = bool(re.search(r'[()（）【】\[\]]', shorter_raw))
    if has_paren_long and not has_paren_short:
        tags.append('parenthetical')

    # ── Business suffix ────────────────────────────────────────
    if _BIZ_SUFFIX_RE.search(longer_raw) and not _BIZ_SUFFIX_RE.search(shorter_raw):
        tags.append('biz_suffix')

    # ── SEO junk ───────────────────────────────────────────────
    if _SEO_RE.search(longer_raw) and not _SEO_RE.search(shorter_raw):
        tags.append('seo_junk')

    # ── Branch / location suffix ───────────────────────────────
    if (_JP_BRANCH_RE.search(excess) or _TH_BRANCH_RE.search(excess) or
            _EN_BRANCH_RE.search(excess)):
        tags.append('branch_suffix')

    # ── Facility suffix (bus stop, ATM, substation) ────────────
    if _FACILITY_SUFFIX_RE.search(excess):
        tags.append('facility_suffix')

    # ── Fallback: generic descriptor ───────────────────────────
    if not tags:
        tags.append('descriptor')

    return ';'.join(tags)


# ══════════════════════════════════════════════════════════════════════════════
#  TWO-TIER CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def _check_subset(a: str, b: str) -> bool:
    """True if one normalized string is contained in the other (and they differ
    in length).  Works across all scripts."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    if len(a) == 0 or len(b) == 0:
        return False
    if a == b:
        return False
    if len(a) == len(b):
        return False
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return short in long


def classify_row(row) -> tuple:
    """Return (tier1_label, tier2_subtags) for a single conflict row.

    Tier 1 priority:
        1. casing_only              lower(a) == lower(b)
        2. normalization_equivalent any normalization path makes them identical
        3. subset                   one normalized form contained in the other
        4. genuinely_different      everything else
    """
    a_raw, b_raw = row['alt_name'], row['base_name']
    if not isinstance(a_raw, str) or not isinstance(b_raw, str):
        return ('genuinely_different', '')

    # ── 1. Casing only ────────────────────────────────────────
    if a_raw.lower() == b_raw.lower():
        return ('casing_only', '')

    # Grab precomputed normalized forms
    a_l2d  = row['alt_l2d']
    b_l2d  = row['base_l2d']
    a_ns   = row['alt_nospace']
    b_ns   = row['base_nospace']

    # ── 2. Normalization equivalent ───────────────────────────
    # Check progressively stronger normalization paths.
    norm_eq = False

    # 2a. norm_compare match (case + fullwidth + accents + punctuation)
    if a_l2d == b_l2d and len(a_l2d) > 0:
        norm_eq = True
    # 2b. Space-stripped match (above + spacing/compound differences)
    elif a_ns == b_ns and len(a_ns) > 0:
        norm_eq = True
    # 2c. Conjunction normalized
    elif row['alt_conj'] == row['base_conj'] and len(row['alt_conj']) > 0:
        norm_eq = True
    # 2d. Conjunction normalized + space-stripped
    elif (row['alt_conj'].replace(' ', '') == row['base_conj'].replace(' ', '')
          and len(row['alt_conj']) > 0):
        norm_eq = True
    # 2e. Spelling normalized
    elif row['alt_spelling'] == row['base_spelling'] and len(row['alt_spelling']) > 0:
        norm_eq = True
    # 2f. Word reorder (sorted tokens)
    elif row['alt_sorted'] == row['base_sorted'] and len(row['alt_sorted']) > 0:
        norm_eq = True
    # 2g. Katakana ↔ hiragana
    elif row['alt_hira'] == row['base_hira'] and len(row['alt_hira']) > 0:
        norm_eq = True
    # 2h. Katakana ↔ hiragana + space-stripped
    elif (row['alt_hira'].replace(' ', '') == row['base_hira'].replace(' ', '')
          and len(row['alt_hira']) > 0):
        norm_eq = True
    # 2i. Typo (Levenshtein on norm_compare forms) — most expensive, last
    elif row['is_typo']:
        norm_eq = True

    if norm_eq:
        return ('normalization_equivalent', _get_norm_subtags(row))

    # ── 3. Subset ─────────────────────────────────────────────
    # Check containment on multiple normalized forms.
    is_sub = False

    # 3a. norm_compare containment (handles most Latin + CJK + Thai subsets)
    if _check_subset(a_l2d, b_l2d):
        is_sub = True
    # 3b. Space-stripped containment (handles Japanese compound boundaries:
    #     ローソン vs ローソンいわき下好間店)
    elif _check_subset(a_ns, b_ns):
        is_sub = True
    # 3c. Hiragana-normalized containment (handles katakana/hiragana mixed subsets)
    elif _check_subset(
        row['alt_hira'].replace(' ', '') if isinstance(row['alt_hira'], str) else '',
        row['base_hira'].replace(' ', '') if isinstance(row['base_hira'], str) else ''
    ):
        is_sub = True

    if is_sub:
        return ('subset', _get_subset_subtags(row))

    # ── 4. Genuinely different ────────────────────────────────
    return ('genuinely_different', '')


# ══════════════════════════════════════════════════════════════════════════════
#  DATAFRAME ENRICHMENT
# ══════════════════════════════════════════════════════════════════════════════

def precompute_forms(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all normalized forms needed for classification."""
    df = df.copy()

    # ── Core normalized forms ──────────────────────────────────
    df['alt_l2d']  = df['alt_name'].apply(norm_compare)
    df['base_l2d'] = df['base_name'].apply(norm_compare)

    df['alt_nospace']  = df['alt_l2d'].str.replace(r'\s', '', regex=True)
    df['base_nospace'] = df['base_l2d'].str.replace(r'\s', '', regex=True)

    df['alt_sorted']  = df['alt_l2d'].apply(
        lambda s: ' '.join(sorted(s.split())) if isinstance(s, str) else s)
    df['base_sorted'] = df['base_l2d'].apply(
        lambda s: ' '.join(sorted(s.split())) if isinstance(s, str) else s)

    df['alt_conj']  = df['alt_name'].apply(norm_conj)
    df['base_conj'] = df['base_name'].apply(norm_conj)

    df['alt_spelling']  = df['alt_name'].apply(norm_spelling)
    df['base_spelling'] = df['base_name'].apply(norm_spelling)

    # ── Script-form normalized (katakana → hiragana) ───────────
    df['alt_hira']  = df['alt_name'].apply(norm_compare_hira)
    df['base_hira'] = df['base_name'].apply(norm_compare_hira)

    # ── Typo flag (Levenshtein on norm_compare forms) ───────────────
    df['is_typo'] = df.apply(
        lambda r: is_typo(r['alt_l2d'], r['base_l2d']), axis=1)

    # ── Conflict flag ──────────────────────────────────────────
    df['is_conflict'] = df['alt_name'] != df['base_name']

    return df


def classify_conflicts(df: pd.DataFrame) -> pd.DataFrame:
    """Apply two-tier classification to all conflict rows.
    Non-conflict rows get tier1='agreement', tier2=''."""
    df = df.copy()
    df['tier1'] = 'agreement'
    df['tier2_subtags'] = ''

    mask = df['is_conflict']
    results = df.loc[mask].apply(classify_row, axis=1, result_type='expand')
    results.columns = ['tier1', 'tier2_subtags']
    df.loc[mask, 'tier1'] = results['tier1']
    df.loc[mask, 'tier2_subtags'] = results['tier2_subtags']

    return df


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    con = duckdb.connect(database=":memory:")

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 0: Agreement breakdown — where do the 2000 rows land?
    # ══════════════════════════════════════════════════════════════
    #
    # The dataset has 2000 rows.  Script 02 found 1375 name conflicts by
    # comparing raw JSON strings.  This script extracts only $.primary and
    # finds 1083 primary-name conflicts.  The difference (292 rows) have
    # matching primary names but differ in alternate/common name fields.
    #
    # This output makes the three buckets explicit with examples.

    con.execute(f"""
        COPY (
            WITH classified AS (
                SELECT
                    id,
                    CASE
                        WHEN names = base_names
                            THEN 'full_agreement'
                        WHEN json_extract_string(names, '$.primary')
                           = json_extract_string(base_names, '$.primary')
                            THEN 'primary_agrees_json_differs'
                        ELSE 'primary_conflict'
                    END AS agreement_type,
                    json_extract_string(names, '$.primary')      AS alt_primary,
                    json_extract_string(base_names, '$.primary') AS base_primary,
                    names                                         AS alt_names_json,
                    base_names                                    AS base_names_json
                FROM '{PARQUET_PATH}'
                WHERE names IS NOT NULL AND base_names IS NOT NULL
            ),
            counts AS (
                SELECT agreement_type, COUNT(*) AS row_count
                FROM classified GROUP BY agreement_type
            ),
            ranked AS (
                SELECT c.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.agreement_type ORDER BY c.id
                    ) AS rn
                FROM classified c
            )
            SELECT
                r.agreement_type,
                ct.row_count,
                ROUND(ct.row_count::DOUBLE / 2000 * 100, 1) AS pct_of_total,
                r.alt_primary,
                r.base_primary,
                r.alt_names_json,
                r.base_names_json
            FROM ranked r
            JOIN counts ct ON r.agreement_type = ct.agreement_type
            WHERE r.rn <= 3
            ORDER BY ct.row_count DESC, r.agreement_type, r.rn
        ) TO '{OUTPUT_AGREEMENT_BREAKDOWN_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 0b: All agreements labeled — every non-conflict row
    # ══════════════════════════════════════════════════════════════
    #
    # Every row where primary names match, labeled as full_agreement
    # or primary_agrees_json_differs, with full JSON for inspection.

    con.execute(f"""
        COPY (
            SELECT
                CASE
                    WHEN names = base_names
                        THEN 'full_agreement'
                    ELSE 'primary_agrees_json_differs'
                END AS agreement_type,
                id,
                json_extract_string(names, '$.primary')      AS alt_primary,
                json_extract_string(base_names, '$.primary') AS base_primary,
                names                                         AS alt_names_json,
                base_names                                    AS base_names_json,
                CASE WHEN json_valid(addresses)
                     THEN json_extract_string(addresses, '$[0].freeform')
                     ELSE NULL END                            AS alt_address,
                CASE WHEN json_valid(base_addresses)
                     THEN json_extract_string(base_addresses, '$[0].freeform')
                     ELSE NULL END                            AS base_address,
                CASE WHEN json_valid(addresses)
                     THEN json_extract_string(addresses, '$[0].locality')
                     ELSE NULL END                            AS city,
                CASE WHEN json_valid(addresses)
                     THEN json_extract_string(addresses, '$[0].region')
                     ELSE NULL END                            AS state,
                confidence                                    AS alt_confidence,
                base_confidence                               AS base_confidence
            FROM '{PARQUET_PATH}'
            WHERE names IS NOT NULL
              AND base_names IS NOT NULL
              AND json_extract_string(names, '$.primary')
                = json_extract_string(base_names, '$.primary')
            ORDER BY agreement_type, id
        ) TO '{OUTPUT_ALL_AGREEMENTS_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ── Extract primary names + context columns from parquet ───
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

    # ── Python-side enrichment ─────────────────────────────────
    df = precompute_forms(raw)
    df = classify_conflicts(df)

    # Coerce object columns to StringDtype for DuckDB compatibility
    for col in df.select_dtypes(include=['object', 'str']).columns:
        df[col] = df[col].astype(pd.StringDtype())

    con.execute("CREATE TABLE name_enriched AS SELECT * FROM df")

    # ── DuckDB feature view (structural metrics + diagnostic flags) ────
    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW name_features AS
        SELECT
            *,

            -- Length / word count
            length(alt_name)  AS alt_len,
            length(base_name) AS base_len,
            array_length(string_split(trim(alt_name),  ' ')) AS alt_word_count,
            array_length(string_split(trim(base_name), ' ')) AS base_word_count,

            -- Casing flags
            (alt_name  = upper(alt_name)  AND alt_name  != lower(alt_name))  AS alt_all_caps,
            (base_name = upper(base_name) AND base_name != lower(base_name)) AS base_all_caps,
            (alt_name  = lower(alt_name)  AND alt_name  != upper(alt_name))  AS alt_all_lower,
            (base_name = lower(base_name) AND base_name != upper(base_name)) AS base_all_lower,

            -- Diagnostic noise flags (informational, do NOT influence tier1)
            regexp_matches(alt_name,  '[\s#\-]+\d{3,}\s*$') AS alt_has_trailing_number,
            regexp_matches(base_name, '[\s#\-]+\d{3,}\s*$') AS base_has_trailing_number,
            regexp_matches(lower(alt_name),
                ',?\s+(llc|l\.l\.c\.|inc|inc\.|corp|corp\.|ltd|ltd\.|co\.|company|incorporated|gmbh|srl|s\.r\.l\.)\.?\s*$'
            ) AS alt_has_biz_suffix,
            regexp_matches(lower(base_name),
                ',?\s+(llc|l\.l\.c\.|inc|inc\.|corp|corp\.|ltd|ltd\.|co\.|company|incorporated|gmbh|srl|s\.r\.l\.)\.?\s*$'
            ) AS base_has_biz_suffix,
            regexp_matches(lower(alt_name),
                '(hours|address|near me|official site|official|directions|reviews|location|best |menu)'
            ) AS alt_has_seo,
            regexp_matches(lower(base_name),
                '(hours|address|near me|official site|official|directions|reviews|location|best |menu)'
            ) AS base_has_seo,
            (array_length(string_split(trim(alt_name),  ' ')) > 8) AS alt_excessive_length,
            (array_length(string_split(trim(base_name), ' ')) > 8) AS base_excessive_length

        FROM name_enriched
        WHERE alt_name IS NOT NULL AND base_name IS NOT NULL;
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 1: Structure summary (per-side metrics)
    # ══════════════════════════════════════════════════════════════
    con.execute(f"""
        COPY (
            SELECT side, COUNT(*) AS total_rows,
                ROUND(AVG(name_len), 1) AS avg_length,
                ROUND(MEDIAN(name_len), 1) AS median_length,
                MIN(name_len) AS min_length, MAX(name_len) AS max_length,
                ROUND(AVG(word_count), 2)    AS avg_word_count,
                ROUND(MEDIAN(word_count), 2) AS median_word_count,
                MIN(word_count) AS min_word_count,
                MAX(word_count) AS max_word_count,
                SUM(CASE WHEN is_all_caps  THEN 1 ELSE 0 END) AS all_caps_count,
                ROUND(AVG(CASE WHEN is_all_caps  THEN 1.0 ELSE 0 END)*100, 2) AS all_caps_pct,
                SUM(CASE WHEN is_all_lower THEN 1 ELSE 0 END) AS all_lower_count,
                ROUND(AVG(CASE WHEN is_all_lower THEN 1.0 ELSE 0 END)*100, 2) AS all_lower_pct,
                SUM(CASE WHEN has_trailing_number THEN 1 ELSE 0 END) AS trailing_number_count,
                ROUND(AVG(CASE WHEN has_trailing_number THEN 1.0 ELSE 0 END)*100, 2) AS trailing_number_pct,
                SUM(CASE WHEN has_biz_suffix THEN 1 ELSE 0 END) AS biz_suffix_count,
                ROUND(AVG(CASE WHEN has_biz_suffix THEN 1.0 ELSE 0 END)*100, 2) AS biz_suffix_pct,
                SUM(CASE WHEN has_seo THEN 1 ELSE 0 END) AS seo_count,
                ROUND(AVG(CASE WHEN has_seo THEN 1.0 ELSE 0 END)*100, 2) AS seo_pct,
                SUM(CASE WHEN excessive_length THEN 1 ELSE 0 END) AS excessive_length_count,
                ROUND(AVG(CASE WHEN excessive_length THEN 1.0 ELSE 0 END)*100, 2) AS excessive_length_pct
            FROM (
                SELECT 'alt' AS side, alt_len AS name_len, alt_word_count AS word_count,
                    alt_all_caps AS is_all_caps, alt_all_lower AS is_all_lower,
                    alt_has_trailing_number AS has_trailing_number,
                    alt_has_biz_suffix AS has_biz_suffix, alt_has_seo AS has_seo,
                    alt_excessive_length AS excessive_length FROM name_features
                UNION ALL
                SELECT 'base', base_len, base_word_count,
                    base_all_caps, base_all_lower,
                    base_has_trailing_number,
                    base_has_biz_suffix, base_has_seo,
                    base_excessive_length FROM name_features
            ) GROUP BY side ORDER BY side
        ) TO '{OUTPUT_METRICS_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 2: Length distribution
    # ══════════════════════════════════════════════════════════════
    con.execute(f"""
        COPY (
            SELECT side,
                CASE WHEN name_len<=5  THEN '1-5'   WHEN name_len<=10 THEN '6-10'
                     WHEN name_len<=20 THEN '11-20' WHEN name_len<=35 THEN '21-35'
                     WHEN name_len<=50 THEN '36-50' WHEN name_len<=75 THEN '51-75'
                     ELSE '>75' END AS length_bucket,
                CASE WHEN name_len<=5  THEN 1 WHEN name_len<=10 THEN 2
                     WHEN name_len<=20 THEN 3 WHEN name_len<=35 THEN 4
                     WHEN name_len<=50 THEN 5 WHEN name_len<=75 THEN 6
                     ELSE 7 END AS bucket_order,
                COUNT(*) AS count,
                ROUND(COUNT(*)::DOUBLE / SUM(COUNT(*)) OVER (PARTITION BY side) * 100, 2) AS pct
            FROM (
                SELECT 'alt'  AS side, alt_len  AS name_len FROM name_features UNION ALL
                SELECT 'base' AS side, base_len AS name_len FROM name_features
            )
            GROUP BY side, length_bucket, bucket_order
            ORDER BY side, bucket_order
        ) TO '{OUTPUT_LENGTH_DISTRIBUTION_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 3: Word count distribution
    # ══════════════════════════════════════════════════════════════
    con.execute(f"""
        COPY (
            SELECT side, word_count, COUNT(*) AS count,
                ROUND(COUNT(*)::DOUBLE / SUM(COUNT(*)) OVER (PARTITION BY side) * 100, 2) AS pct
            FROM (
                SELECT 'alt'  AS side, alt_word_count  AS word_count FROM name_features UNION ALL
                SELECT 'base' AS side, base_word_count AS word_count FROM name_features
            )
            GROUP BY side, word_count ORDER BY side, word_count
        ) TO '{OUTPUT_WORDCOUNT_DISTRIBUTION_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 4: Casing patterns (conflict rows only)
    # ══════════════════════════════════════════════════════════════
    con.execute(f"""
        COPY (
            SELECT casing_pattern, COUNT(*) AS count,
                ROUND(COUNT(*)::DOUBLE / SUM(COUNT(*)) OVER () * 100, 2) AS pct_of_conflicts
            FROM (
                SELECT CASE
                    WHEN tier1 = 'casing_only'                    THEN 'casing_only'
                    WHEN alt_all_caps  AND NOT base_all_caps       THEN 'alt_all_caps_base_not'
                    WHEN base_all_caps AND NOT alt_all_caps        THEN 'base_all_caps_alt_not'
                    WHEN alt_all_lower AND NOT base_all_lower      THEN 'alt_all_lower_base_not'
                    WHEN base_all_lower AND NOT alt_all_lower      THEN 'base_all_lower_alt_not'
                    ELSE 'both_mixed_or_title'
                END AS casing_pattern
                FROM name_features WHERE is_conflict
            )
            GROUP BY casing_pattern ORDER BY count DESC
        ) TO '{OUTPUT_CASING_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 5: Tier 1 summary
    # ══════════════════════════════════════════════════════════════
    con.execute(f"""
        COPY (
            WITH totals AS (
                SELECT COUNT(*) AS total_conflicts
                FROM name_features WHERE is_conflict
            )
            SELECT tier1, COUNT(*) AS count,
                ROUND(COUNT(*)::DOUBLE / t.total_conflicts * 100, 2) AS pct_of_conflicts
            FROM name_features, totals t
            WHERE is_conflict
            GROUP BY tier1, t.total_conflicts
            ORDER BY count DESC
        ) TO '{OUTPUT_TIER1_SUMMARY_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 6: Tier 2 subtag frequency
    # ══════════════════════════════════════════════════════════════
    #
    # Subtags are semicolon-delimited in tier2_subtags.
    # Unnest them to count each subtag independently.
    con.execute(f"""
        COPY (
            WITH exploded AS (
                SELECT
                    tier1,
                    unnest(string_split(tier2_subtags, ';')) AS subtag
                FROM name_features
                WHERE is_conflict AND tier2_subtags IS NOT NULL AND tier2_subtags != ''
            )
            SELECT tier1, subtag, COUNT(*) AS count
            FROM exploded
            WHERE subtag != ''
            GROUP BY tier1, subtag
            ORDER BY tier1, count DESC
        ) TO '{OUTPUT_SUBTAG_SUMMARY_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 7: All conflicts labeled (full detail for inspection)
    # ══════════════════════════════════════════════════════════════
    con.execute(f"""
        COPY (
            SELECT
                tier1,
                tier2_subtags,
                id,
                alt_name,
                base_name,
                alt_len,
                base_len,
                (base_len - alt_len)               AS len_diff_base_minus_alt,
                alt_word_count,
                base_word_count,
                (base_word_count - alt_word_count)  AS word_diff_base_minus_alt,
                alt_address,
                base_address,
                city,
                state,
                alt_category,
                base_category,
                alt_confidence,
                base_confidence,
                alt_sources,
                base_sources,
                -- Diagnostic flags (informational)
                alt_has_trailing_number,
                base_has_trailing_number,
                alt_has_biz_suffix,
                base_has_biz_suffix,
                alt_has_seo,
                base_has_seo,
                alt_excessive_length,
                base_excessive_length
            FROM name_features
            WHERE is_conflict
            ORDER BY
                CASE tier1
                    WHEN 'casing_only'              THEN 1
                    WHEN 'normalization_equivalent'  THEN 2
                    WHEN 'subset'                    THEN 3
                    WHEN 'genuinely_different'       THEN 4
                END,
                tier2_subtags,
                ABS(base_len - alt_len) DESC,
                id
        ) TO '{OUTPUT_ALL_CONFLICTS_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ══════════════════════════════════════════════════════════════
    #  OUTPUT 8: Genuinely different — golden dataset population
    # ══════════════════════════════════════════════════════════════
    con.execute(f"""
        COPY (
            SELECT
                tier2_subtags,
                id,
                alt_name,
                base_name,
                alt_len,
                base_len,
                (base_len - alt_len)               AS len_diff_base_minus_alt,
                alt_word_count,
                base_word_count,
                (base_word_count - alt_word_count)  AS word_diff_base_minus_alt,
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
            FROM name_features
            WHERE is_conflict AND tier1 = 'genuinely_different'
            ORDER BY ABS(base_len - alt_len) DESC, id
        ) TO '{OUTPUT_GENUINELY_DIFFERENT_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    con.close()

    # ── Summary to stdout ──────────────────────────────────────
    print(f"Wrote: {OUTPUT_AGREEMENT_BREAKDOWN_PATH}")
    print(f"  -> 2000 rows split into: full_agreement / primary_agrees_json_differs / primary_conflict")
    print(f"  -> 3 examples per bucket with full JSON for inspection.")
    print(f"Wrote: {OUTPUT_ALL_AGREEMENTS_PATH}")
    print(f"  -> All rows where primary names agree, labeled full_agreement or primary_agrees_json_differs.")
    print(f"Wrote: {OUTPUT_METRICS_PATH}")
    print(f"Wrote: {OUTPUT_LENGTH_DISTRIBUTION_PATH}")
    print(f"Wrote: {OUTPUT_WORDCOUNT_DISTRIBUTION_PATH}")
    print(f"Wrote: {OUTPUT_CASING_PATH}")
    print(f"Wrote: {OUTPUT_TIER1_SUMMARY_PATH}")
    print(f"  -> Tier 1 breakdown: casing_only | normalization_equivalent | subset | genuinely_different")
    print(f"Wrote: {OUTPUT_SUBTAG_SUMMARY_PATH}")
    print(f"  -> Tier 2 subtag frequency per tier1 label")
    print(f"Wrote: {OUTPUT_ALL_CONFLICTS_PATH}")
    print(f"  -> All {df['is_conflict'].sum()} conflict rows with tier1 + tier2 labels.")
    print(f"  -> Filter by tier1 to inspect any bucket.")
    print(f"Wrote: {OUTPUT_GENUINELY_DIFFERENT_PATH}")
    genuinely_different_count = (df['tier1'] == 'genuinely_different').sum()
    print(f"  -> {genuinely_different_count} genuinely different rows = golden dataset population.")


if __name__ == "__main__":
    main()