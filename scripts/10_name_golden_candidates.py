"""
10_name_golden_candidates.py — Golden dataset candidate selection for names

Purpose:
    Apply concrete selection rules to every row in the dataset and produce a
    recommended "golden name" for each place. This is the capstone of the name
    analysis pipeline — everything from 08 (classification) and 09 (normalization)
    feeds into it.

    For each row, the output contains:
        - Both raw names (alt_name, base_name)
        - The selected golden name (selected_name)
        - Which side it came from (selected_source: alt / base / abstain)
        - Why it was selected (selection_reason)

Selection logic by conflict type:

    agreement (917 rows):
        Both sides have the same primary name. Pick either (identical).

    normalized (315 rows):
        Same name, different formatting. Pick the better-formatted version:
        - Prefer title case over ALL CAPS or all-lowercase
        - Prefer the form with apostrophes (Aherne's > Ahernes)
        - Prefer the form with accents (Café > Cafe)
        - Prefer spaced forms (Photo Color Lab > PhotoColorLab)
        - Prefer forms with Japanese nakaguro (ビジネスホテル・キャッスル)
        - Detect branded casing (ecoATM, IndianOil) and preserve it

    subset (592 rows):
        One name is contained in the other. Prefer the shorter core name
        for portability. The longer form's extra content (branch, parenthetical,
        descriptor) is preserved as metadata in a separate column.

    different (176 rows):
        Genuinely different names. Abstain — flag for human review.

Outputs:
    name_golden_candidates.csv       Every row with selected name and reasoning
    name_golden_summary.csv          Counts by selection source
"""

import re
import unicodedata
import duckdb
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────

PARQUET_PATH = "../data/raw/project_a_samples.parquet"

OUTPUT_GOLDEN_PATH   = "../analysis/names/name_golden_candidates.csv"
OUTPUT_SUMMARY_PATH  = "../analysis/names/name_golden_summary.csv"


# ══════════════════════════════════════════════════════════════════════════════
#  NORMALIZERS (reused from 08/09)
# ══════════════════════════════════════════════════════════════════════════════

def strip_fullwidth(s: str) -> str:
    if not isinstance(s, str):
        return s
    return unicodedata.normalize("NFC", unicodedata.normalize("NFKD", s))


def strip_accents_py(s: str) -> str:
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
    return ''.join(c for c in s
                   if unicodedata.category(c)[0] in ('L', 'N', 'M')
                   or c in (' ', '\t', '\n'))


def norm_compare(s: str) -> str:
    if not isinstance(s, str):
        return ''
    s = strip_accents_py(strip_fullwidth(s)).lower()
    result = []
    for c in s:
        cat = unicodedata.category(c)
        if cat[0] in ('L', 'N', 'M') or c in (' ', '\t', '\n'):
            result.append(c)
    return re.sub(r'\s+', ' ', ''.join(result)).strip()


def kata_to_hira(s: str) -> str:
    if not isinstance(s, str):
        return s
    return ''.join(
        chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c
        for c in s
    )


def norm_compare_hira(s: str) -> str:
    if not isinstance(s, str):
        return ''
    return norm_compare(kata_to_hira(s))


def levenshtein(a: str, b: str) -> int:
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
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    if len(a) < 5 or len(b) < 5:
        return False
    dist = levenshtein(a, b)
    if dist > 2:
        return False
    return (1 - dist / max(len(a), len(b))) >= 0.85


# ══════════════════════════════════════════════════════════════════════════════
#  SCRIPT DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _has_cjk(s: str) -> bool:
    """True if string contains CJK ideographs or Japanese kana."""
    if not isinstance(s, str):
        return False
    for c in s:
        cp = ord(c)
        if (0x4E00 <= cp <= 0x9FFF      # CJK Unified Ideographs
            or 0x3040 <= cp <= 0x309F    # Hiragana
            or 0x30A0 <= cp <= 0x30FF    # Katakana
            or 0x3400 <= cp <= 0x4DBF    # CJK Extension A
            or 0xFF66 <= cp <= 0xFF9F):  # Halfwidth Katakana
            return True
    return False


def _has_thai(s: str) -> bool:
    """True if string contains Thai characters."""
    if not isinstance(s, str):
        return False
    return any(0x0E01 <= ord(c) <= 0x0E5B for c in s)


# ══════════════════════════════════════════════════════════════════════════════
#  CLASSIFICATION (reused from 08/09)
# ══════════════════════════════════════════════════════════════════════════════

def _check_subset(a: str, b: str) -> bool:
    if not a or not b or a == b or len(a) == len(b):
        return False
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return short in long


def classify_conflict(row) -> str:
    """Classify a conflict row into: casing | normalized | subset | different."""
    a_raw = row['alt_name']
    b_raw = row['base_name']

    if not isinstance(a_raw, str) or not isinstance(b_raw, str):
        return 'different'

    if a_raw == b_raw:
        return 'agreement'

    if a_raw.lower() == b_raw.lower():
        return 'casing'

    a_nc = row['alt_nc']
    b_nc = row['base_nc']
    a_ns = a_nc.replace(' ', '')
    b_ns = b_nc.replace(' ', '')
    a_hira = row['alt_hira']
    b_hira = row['base_hira']
    a_hira_ns = a_hira.replace(' ', '') if isinstance(a_hira, str) else ''
    b_hira_ns = b_hira.replace(' ', '') if isinstance(b_hira, str) else ''

    # Normalization equivalent checks
    if a_nc == b_nc and len(a_nc) > 0:
        return 'normalized'
    if a_ns == b_ns and len(a_ns) > 0:
        return 'normalized'
    # Conjunction normalized
    a_conj = row['alt_conj']
    b_conj = row['base_conj']
    if a_conj == b_conj and len(a_conj) > 0:
        return 'normalized'
    if a_conj.replace(' ', '') == b_conj.replace(' ', '') and len(a_conj) > 0:
        return 'normalized'
    # Spelling
    if row['alt_spell'] == row['base_spell'] and len(row['alt_spell']) > 0:
        return 'normalized'
    # Hiragana
    if a_hira == b_hira and len(a_hira) > 0:
        return 'normalized'
    if a_hira_ns == b_hira_ns and len(a_hira_ns) > 0:
        return 'normalized'
    # Sorted
    if ''.join(sorted(a_hira_ns)) == ''.join(sorted(b_hira_ns)) and len(a_hira_ns) > 0:
        return 'normalized'
    # Typo
    if is_typo(a_nc, b_nc):
        return 'normalized'

    # Subset checks
    if _check_subset(a_nc, b_nc):
        return 'subset'
    if _check_subset(a_ns, b_ns):
        return 'subset'
    if _check_subset(a_hira_ns, b_hira_ns):
        return 'subset'

    return 'different'


# ══════════════════════════════════════════════════════════════════════════════
#  SELECTION RULES
# ══════════════════════════════════════════════════════════════════════════════

# French/Italian/Spanish/Portuguese prepositions and articles that should
# be lowercase in names. Used to evaluate casing quality.
_LOWERCASE_PARTICLES = {
    'de', 'del', 'della', 'delle', 'dei', 'degli', 'dello',
    'di', 'da', 'du', 'des', 'la', 'le', 'les', 'l',
    'el', 'los', 'las', 'do', 'da', 'dos', 'das',
    'van', 'von', 'den', 'der', 'het',
    'of', 'the', 'and', 'in', 'at', 'by', 'for', 'to', 'on',
}


def _count_accented(s: str) -> int:
    """Count characters that have accent marks (Latin only)."""
    count = 0
    for c in s:
        decomposed = unicodedata.normalize("NFD", c)
        if len(decomposed) > 1:
            cp = ord(decomposed[1])
            if 0x0300 <= cp <= 0x036F:
                count += 1
    return count


def _count_good_apostrophes(s: str) -> int:
    """Count linguistically valid apostrophes. Rejects:
    - Ongkeco'S (capital letter after apostrophe mid-word → bad possessive)
    - La' Ziza (apostrophe before space with long prefix → misplaced)
    Valid patterns:
    - 's possessive (Aherne's)
    - Trailing contraction (Dunkin', Gettin')
    - l'/d' French elision (L'ynara, d'Alain)"""
    if not isinstance(s, str):
        return 0
    count = 0
    for i, c in enumerate(s):
        if c not in ("'", "\u2019"):
            continue

        # Check what follows the apostrophe
        after_is_end = (i + 1 >= len(s))
        after_is_space = (not after_is_end and s[i + 1] == ' ')

        # Trailing apostrophe (Dunkin', Gettin') — valid contraction
        if after_is_end or after_is_space:
            # But reject La' Ziza pattern: single short word + apostrophe + space
            # Valid trailing: the preceding "word" should be > 2 chars
            prefix_start = i
            while prefix_start > 0 and s[prefix_start - 1].isalpha():
                prefix_start -= 1
            prefix_len = i - prefix_start
            if prefix_len >= 3:  # Dunkin' (6 chars) OK, La' (2 chars) rejected
                count += 1
            continue

        # Apostrophe followed by uppercase mid-word (Ongkeco'S)
        if s[i + 1].isupper() and i > 0 and s[i - 1].isalpha():
            prefix_start = i
            while prefix_start > 0 and s[prefix_start - 1].isalpha():
                prefix_start -= 1
            prefix_len = i - prefix_start
            if prefix_len > 2:  # Long prefix → bad possessive (Ongkeco'S)
                continue
            # Short prefix (D', L') → French elision, valid
            count += 1
            continue

        # All other cases: apostrophe before lowercase letter → valid
        count += 1
    return count


def _has_nakaguro(s: str) -> bool:
    return '・' in s if isinstance(s, str) else False


def _casing_score(s: str) -> int:
    """Score the casing quality of a name. Higher = better.

    Rules:
    - Prefer title case with correct particle lowercasing (best)
    - Prefer mixed case over ALL CAPS or all lowercase
    - Penalize grammatical casing errors (Ongkeco'S, random ALL CAPS words)
    - For CJK/Thai-mixed names with Latin text, prefer uppercase Latin (Japanese convention)
    """
    if not isinstance(s, str) or len(s) == 0:
        return 0

    score = 0
    words = s.split()
    if not words:
        return 0

    has_cjk = _has_cjk(s)

    # French/Italian elision particles: d', l', n', s', c', qu'
    # These should be lowercase when not the first word.
    _ELISION_PREFIXES = {'d', 'l', 'n', 's', 'c', 'qu', 'j', 'm'}

    for i, word in enumerate(words):
        # Extract just Latin letters from this word
        latin = ''.join(c for c in word if c.isalpha() and ord(c) < 0x0250)
        if not latin:
            continue

        word_lower = word.lower().rstrip("'.,;:!?")

        # Check for French elision: D'Art → should be d'Art (when not first word)
        if "'" in word or "\u2019" in word:
            for apos in ("'", "\u2019"):
                idx = word.find(apos)
                if idx > 0 and i > 0:
                    prefix = word[:idx].lower()
                    if prefix in _ELISION_PREFIXES:
                        # Lowercase elision prefix is better
                        if word[:idx] == word[:idx].lower():
                            score += 2  # d'Art → good
                        else:
                            score -= 1  # D'Art → bad (should be lowercase)

        # Articles/prepositions should be lowercase (unless first word)
        if word_lower in _LOWERCASE_PARTICLES and i > 0:
            if latin == latin.lower():
                score += 2  # Correctly lowercase particle
            elif latin == latin.upper():
                score -= 1  # ALL CAPS particle (bad)
            else:
                score += 1  # Title case particle (acceptable)
        else:
            # Normal content words
            if latin == latin.upper() and len(latin) > 4:
                score -= 1  # ALL CAPS word longer than 4 chars (shouting: SHELL, RAQSA, CONAD)
            elif latin == latin.upper() and len(latin) <= 4:
                score += 3  # Short uppercase: abbreviation/brand (OXXO, HDFC, ATM, BP)
            elif latin[0].isupper() and latin[1:] == latin[1:].lower():
                score += 2  # Proper title case
            elif latin == latin.lower():
                score += 0  # all lowercase content word (neutral)

        # Check for bad apostrophe casing: Ongkeco'S
        if "'" in word or "\u2019" in word:
            for apos in ("'", "\u2019"):
                idx = word.find(apos)
                if idx > 0 and idx + 1 < len(word) and word[idx + 1].isupper():
                    # Check if this is a short elision prefix (D', L')
                    prefix = word[:idx]
                    if len(prefix) > 2:
                        score -= 3  # Bad: Ongkeco'S

    # Japanese convention: strongly prefer uppercase Latin in CJK-mixed names
    # (e.g. セルフ写真館BLANC, not セルフ写真館Blanc)
    if has_cjk:
        latin_chars = [c for c in s if c.isalpha() and ord(c) < 0x0250]
        if latin_chars and all(c.isupper() for c in latin_chars):
            score += 5  # Strong bonus — overrides "shouting" penalty for CJK context

    return score


def _has_branded_casing(s: str) -> bool:
    """Detect camelCase or internal capitalization patterns.
    Examples: ecoATM, IndianOil, PuroClean, iPhone, McDonald's.

    Works by detecting lowercase→uppercase transitions within a word.
    The transition must NOT be at position 0 (that's just capitalization)
    and the word must not be all-caps (that's just an abbreviation)."""
    if not isinstance(s, str):
        return False
    for word in s.split():
        # Skip all-caps words (abbreviations)
        latin = ''.join(c for c in word if c.isalpha() and ord(c) < 0x0250)
        if not latin or latin == latin.upper():
            continue
        # Look for lowercase→uppercase transition
        for i in range(1, len(word)):
            if word[i - 1].islower() and word[i].isupper():
                return True
    return False


def _count_spaces(s: str) -> int:
    return s.count(' ') if isinstance(s, str) else 0


def _has_internal_dash(s: str) -> bool:
    """Detect intentional compound dashes like Save-A-Lot, A-1."""
    if not isinstance(s, str):
        return False
    return bool(re.search(r'\w-\w', s))


def select_normalized(alt: str, base: str) -> tuple:
    """Select the better-formatted version of two normalization-equivalent names.
    Returns (selected_name, selected_source, reason).

    Priority order:
    1. Branded casing (ecoATM, IndianOil) — preserve it
    2. Apostrophe quality (valid apostrophes preferred)
    3. Accented form (Café > Cafe)
    4. Nakaguro for Japanese readability
    5. Internal dashes (Save-A-Lot preserved over Save A Lot)
    6. Casing quality score (title case, particle handling, etc.)
    7. Prefer compound form over split (PhotoColorLab > Photo Color Lab)
    8. Shorter, then alt as tiebreaker
    """

    # Rule 1: Branded casing — if one side has camelCase, prefer it
    alt_branded = _has_branded_casing(alt)
    base_branded = _has_branded_casing(base)
    if alt_branded and not base_branded:
        return (alt, 'alt', 'branded_casing')
    if base_branded and not alt_branded:
        return (base, 'base', 'branded_casing')

    # Rule 2: Prefer valid apostrophes (Aherne's > Ahernes, but not Ongkeco'S)
    alt_apos = _count_good_apostrophes(alt)
    base_apos = _count_good_apostrophes(base)
    if alt_apos > base_apos:
        return (alt, 'alt', 'has_apostrophe')
    if base_apos > alt_apos:
        return (base, 'base', 'has_apostrophe')

    # Rule 3: Prefer accented form (richer linguistic info)
    alt_acc = _count_accented(alt)
    base_acc = _count_accented(base)
    if alt_acc > base_acc:
        return (alt, 'alt', 'has_accents')
    if base_acc > alt_acc:
        return (base, 'base', 'has_accents')

    # Rule 4: Prefer nakaguro for Japanese katakana names
    if _has_nakaguro(alt) and not _has_nakaguro(base):
        return (alt, 'alt', 'has_nakaguro')
    if _has_nakaguro(base) and not _has_nakaguro(alt):
        return (base, 'base', 'has_nakaguro')

    # Rule 5: Prefer abbreviation periods (Mr. > Mr, A. > A, Mark A. > Mark A)
    alt_periods = alt.count('.')
    base_periods = base.count('.')
    if alt_periods > base_periods and base_periods == 0:
        return (alt, 'alt', 'has_periods')
    if base_periods > alt_periods and alt_periods == 0:
        return (base, 'base', 'has_periods')

    # Rule 6: Prefer internal dashes (Save-A-Lot > Save A Lot)
    alt_dash = _has_internal_dash(alt)
    base_dash = _has_internal_dash(base)
    if alt_dash and not base_dash:
        return (alt, 'alt', 'has_compound_dash')
    if base_dash and not alt_dash:
        return (base, 'base', 'has_compound_dash')

    # Rule 7: Casing quality score
    alt_casing = _casing_score(alt)
    base_casing = _casing_score(base)
    if alt_casing > base_casing:
        return (alt, 'alt', 'better_casing')
    if base_casing > alt_casing:
        return (base, 'base', 'better_casing')

    # Rule 8: Prefer COMPOUND form (fewer spaces) — if someone wrote it as
    # one word, it was probably intentional. EXCEPTION: if the space separates
    # a trailing number (pickleball 406 > pickleball406), prefer the spaced form.
    alt_spaces = _count_spaces(alt)
    base_spaces = _count_spaces(base)
    if alt_spaces != base_spaces:
        # Check if the difference is just a number being split off
        fewer = alt if alt_spaces < base_spaces else base
        more = base if alt_spaces < base_spaces else alt
        fewer_src = 'alt' if alt_spaces < base_spaces else 'base'
        more_src = 'base' if alt_spaces < base_spaces else 'alt'
        # If the extra space separates a trailing number, prefer spaced
        if re.search(r'\s\d+\s*$', more) and not re.search(r'\s\d+\s*$', fewer):
            return (more, more_src, 'prefer_spaced_number')
        # Otherwise prefer compound
        return (fewer, fewer_src, 'prefer_compound')

    # Rule 9: Prefer shorter (less noise), then alt by convention
    if len(alt) < len(base):
        return (alt, 'alt', 'shorter')
    if len(base) < len(alt):
        return (base, 'base', 'shorter')

    return ('', 'abstain', 'tiebreaker_undecidable')


def select_subset(alt: str, base: str, alt_nc: str, base_nc: str) -> tuple:
    """Select from a subset pair. Returns (selected_name, selected_source,
    reason, extra_content).

    Selection logic:
    1. CJK/Thai names: prefer the LONGER (more specific) form.
    2. Generic short names (≤6 chars or single word): prefer longer.
    3. Extra content contains business-type descriptor (Hotel, Bar, Café,
       Spa, Bistro, Supermarket...): prefer longer — these describe
       what the place IS, not just where it is.
    4. Latin names: prefer the SHORTER core name (default).

    Known limitation: cannot distinguish business-type descriptors from
    location qualifiers without an ML model. "Supermarket" (keep) and
    "Marseille" (drop) both appear as extra content after the core name.
    """

    # Business-type words that describe WHAT a place is (not WHERE).
    # If the extra content contains one, the longer name is more informative.
    _BUSINESS_TYPE_WORDS = {
        'hotel', 'motel', 'inn', 'hostel', 'resort', 'lodge',
        'bar', 'pub', 'cafe', 'café', 'bistro', 'restaurant', 'grill',
        'pizzeria', 'trattoria', 'brasserie', 'tavern', 'cantina',
        'spa', 'salon', 'studio', 'clinic', 'pharmacy', 'apotheke',
        'hospital', 'medical', 'dental',
        'supermarket', 'market', 'mart', 'grocery', 'store', 'shop',
        'boutique', 'gallery', 'museum', 'theater', 'theatre', 'cinema',
        'school', 'academy', 'university', 'college', 'institute',
        'church', 'mosque', 'temple', 'cathedral',
        'gym', 'fitness', 'arena', 'stadium',
        'bank', 'insurance', 'agency',
        'sportsbar', 'brewpub', 'coffeehouse',
    }

    # Determine which is shorter/longer on normalized forms
    alt_ns = alt_nc.replace(' ', '')
    base_ns = base_nc.replace(' ', '')

    if len(alt_ns) <= len(base_ns):
        short_raw, long_raw = alt, base
        short_source, long_source = 'alt', 'base'
    else:
        short_raw, long_raw = base, alt
        short_source, long_source = 'base', 'alt'

    # Extract extra content (what the longer name adds)
    short_nc = norm_compare(short_raw)
    long_nc = norm_compare(long_raw)
    extra = long_nc.replace(short_nc, '', 1).strip()
    if not extra:
        long_ns = norm_compare(long_raw).replace(' ', '')
        short_ns = norm_compare(short_raw).replace(' ', '')
        extra = long_ns.replace(short_ns, '', 1).strip()

    # ── Rule 1: CJK/Thai → prefer longer (more specific) ──────
    if _has_cjk(long_raw) or _has_thai(long_raw):
        return (long_raw, long_source, 'prefer_specific_cjk_thai', extra)

    # ── Rule 2: Generic short name → prefer longer ─────────────
    # Strip parenthetical and pipe content before checking length,
    # so "CIBC Branch (Cash at ATM only)" doesn't win over "CIBC"
    # just because the parenthetical makes it longer.
    short_clean = re.sub(r'\s*[\(（【\[].*?[\)）】\]]', '', short_raw).strip()
    short_clean = re.sub(r'\s*\|.*$', '', short_clean).strip()
    short_words = short_clean.split()
    if len(short_clean) <= 6 or len(short_words) <= 1:
        # But also check the long name isn't just short + location/noise
        # If the long name also cleans down to something short, prefer shorter
        long_clean = re.sub(r'\s*[\(（【\[].*?[\)）】\]]', '', long_raw).strip()
        long_clean = re.sub(r'\s*\|.*$', '', long_clean).strip()
        return (long_raw, long_source, 'short_name_too_generic', extra)

    # ── Rule 3: Extra content has business-type descriptor → prefer longer
    # Words that describe WHAT a place is (Hotel, Bar, Spa, Supermarket...)
    # are semantically important. Location qualifiers (city names, addresses)
    # are not — but we cannot reliably distinguish them without an ML model.
    extra_words = set(extra.lower().split())
    if extra_words & _BUSINESS_TYPE_WORDS:
        return (long_raw, long_source, 'has_business_type', extra)

    # ── Rule 4: Latin default → prefer shorter (core name) ────
    reason = 'prefer_core_name'
    return (short_raw, short_source, reason, extra)


# ══════════════════════════════════════════════════════════════════════════════
#  CONJUNCTION NORMALIZATION (for classification)
# ══════════════════════════════════════════════════════════════════════════════

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


def norm_conj(s: str) -> str:
    if not isinstance(s, str):
        return ''
    s = strip_accents_py(strip_fullwidth(s)).lower()
    s = re.sub(r'&', ' and ', s)
    s = _strip_punct_symbols(s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\b(and|et|und)\b', 'and', s)
    s = re.sub(r'(?<= )y(?= )', 'and', s)
    s = re.sub(r'(?<= )e(?= )', 'and', s)
    return re.sub(r'\s+', ' ', s).strip()


def norm_spelling(s: str) -> str:
    if not isinstance(s, str):
        return ''
    s = norm_compare(s)
    for british, american in BRITISH_AMERICAN.items():
        s = re.sub(r'\b' + british + r'\b', american, s)
    return s


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    con = duckdb.connect(database=":memory:")

    # ── Extract from parquet ───────────────────────────────────
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

    # ── Precompute normalized forms ────────────────────────────
    df = raw.copy()
    df['alt_nc'] = df['alt_name'].apply(norm_compare)
    df['base_nc'] = df['base_name'].apply(norm_compare)
    df['alt_hira'] = df['alt_name'].apply(norm_compare_hira)
    df['base_hira'] = df['base_name'].apply(norm_compare_hira)
    df['alt_conj'] = df['alt_name'].apply(norm_conj)
    df['base_conj'] = df['base_name'].apply(norm_conj)
    df['alt_spell'] = df['alt_name'].apply(norm_spelling)
    df['base_spell'] = df['base_name'].apply(norm_spelling)

    # ── Classify each row ──────────────────────────────────────
    df['conflict_type'] = df.apply(classify_conflict, axis=1)

    # ── Apply selection rules ──────────────────────────────────
    results = []
    for _, row in df.iterrows():
        alt = row['alt_name']
        base = row['base_name']
        ctype = row['conflict_type']

        if ctype == 'agreement':
            results.append({
                'selected_name': alt,
                'selected_source': 'agreement',
                'selection_reason': 'both_sides_identical',
                'extra_content': '',
            })

        elif ctype == 'casing':
            name, source, reason = select_normalized(alt, base)
            results.append({
                'selected_name': name,
                'selected_source': source,
                'selection_reason': f'casing:{reason}',
                'extra_content': '',
            })

        elif ctype == 'normalized':
            name, source, reason = select_normalized(alt, base)
            results.append({
                'selected_name': name,
                'selected_source': source,
                'selection_reason': f'normalized:{reason}',
                'extra_content': '',
            })

        elif ctype == 'subset':
            name, source, reason, extra = select_subset(
                alt, base, row['alt_nc'], row['base_nc'])
            results.append({
                'selected_name': name,
                'selected_source': source,
                'selection_reason': f'subset:{reason}',
                'extra_content': extra,
            })

        elif ctype == 'different':
            results.append({
                'selected_name': '',
                'selected_source': 'abstain',
                'selection_reason': 'genuinely_different:human_review_required',
                'extra_content': '',
            })

    results_df = pd.DataFrame(results)
    df = pd.concat([df, results_df], axis=1)

    # ── Output 1: Full golden candidates ───────────────────────
    for col in df.select_dtypes(include=['object', 'str']).columns:
        df[col] = df[col].astype(pd.StringDtype())

    con.execute("CREATE TABLE golden AS SELECT * FROM df")
    con.execute(f"""
        COPY (
            SELECT
                conflict_type,
                selected_source,
                selection_reason,
                selected_name,
                extra_content,
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
                alt_sources,
                base_sources
            FROM golden
            ORDER BY
                CASE conflict_type
                    WHEN 'agreement'  THEN 1
                    WHEN 'casing'     THEN 2
                    WHEN 'normalized' THEN 3
                    WHEN 'subset'     THEN 4
                    WHEN 'different'  THEN 5
                END,
                selection_reason,
                id
        ) TO '{OUTPUT_GOLDEN_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    # ── Output 2: Summary counts ───────────────────────────────
    con.execute(f"""
        COPY (
            SELECT
                conflict_type,
                selected_source,
                selection_reason,
                COUNT(*) AS count,
                ROUND(COUNT(*)::DOUBLE / 2000 * 100, 2) AS pct_of_total
            FROM golden
            GROUP BY conflict_type, selected_source, selection_reason
            ORDER BY count DESC
        ) TO '{OUTPUT_SUMMARY_PATH}' WITH (HEADER, DELIMITER ',')
    """)

    con.close()

    # ── Summary to stdout ──────────────────────────────────────
    print(f"Wrote: {OUTPUT_GOLDEN_PATH}")
    print(f"Wrote: {OUTPUT_SUMMARY_PATH}")
    print()

    # Conflict type summary
    type_counts = df['conflict_type'].value_counts()
    print("Conflict type distribution:")
    for ctype, count in type_counts.items():
        print(f"  {ctype:<15s} {count:>5d}  ({count/len(df)*100:.1f}%)")

    print()

    # Selection source summary
    source_counts = df['selected_source'].value_counts()
    print("Selection source distribution:")
    for source, count in source_counts.items():
        print(f"  {source:<15s} {count:>5d}  ({count/len(df)*100:.1f}%)")

    print()

    # Selection reason summary (top 15)
    reason_counts = df['selection_reason'].value_counts().head(15)
    print("Top selection reasons:")
    for reason, count in reason_counts.items():
        print(f"  {reason:<50s} {count:>5d}")

    print()

    # Show some examples per conflict type
    for ctype in ['casing', 'normalized', 'subset', 'different']:
        subset = df[df['conflict_type'] == ctype].head(3)
        print(f"\n{'='*80}")
        print(f"Examples: {ctype}")
        print(f"{'='*80}")
        for _, row in subset.iterrows():
            print(f"  alt:      {row['alt_name']}")
            print(f"  base:     {row['base_name']}")
            print(f"  selected: {row['selected_name']}")
            print(f"  source:   {row['selected_source']}  reason: {row['selection_reason']}")
            if row['extra_content']:
                print(f"  extra:    {row['extra_content']}")
            print()


if __name__ == "__main__":
    main()