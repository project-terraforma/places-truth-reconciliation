"""
08b_name_unicode_audit.py — Count rows with script-essential Unicode marks

Purpose:
    Quantify how many name rows contain Japanese dakuten/handakuten,
    Thai tone marks, small kana, and other non-Latin combining marks
    that naive accent stripping would destroy.

Outputs:
    name_unicode_mark_counts.csv    Counts per mark type, per side
"""

import unicodedata
import duckdb
import pandas as pd

PARQUET_PATH = "../data/raw/project_a_samples.parquet"
OUTPUT_PATH = "../analysis/names/name_unicode_mark_counts.csv"


def audit_marks(s: str) -> dict:
    """Check a string for script-essential marks that naive stripping destroys."""
    if not isinstance(s, str):
        return {k: False for k in [
            'has_dakuten', 'has_handakuten', 'has_thai_tone',
            'has_small_kana', 'has_korean_mark', 'has_any_vulnerable_mark'
        ]}

    has_dakuten = False      # ゙ U+3099 (バ, ガ, ダ, etc.)
    has_handakuten = False   # ゚ U+309A (パ, etc.)
    has_thai_tone = False    # ่ ้ ๊ ๋ (U+0E48-U+0E4B)
    has_small_kana = False   # ァィゥェォ etc.
    has_korean_mark = False  # Hangul jamo combining

    # Check via NFD decomposition — this is how strip_accents sees them
    decomposed = unicodedata.normalize("NFD", s)
    for c in decomposed:
        cp = ord(c)
        if cp == 0x3099:
            has_dakuten = True
        elif cp == 0x309A:
            has_handakuten = True
        elif 0x0E48 <= cp <= 0x0E4B:
            has_thai_tone = True
        elif 0x1100 <= cp <= 0x11FF or 0xA960 <= cp <= 0xA97F:
            has_korean_mark = True

    # Small kana: check original string (not decomposed)
    for c in s:
        cp = ord(c)
        # Katakana small: ァ-ォ (U+30A1,30A3,30A5,30A7,30A9), ッ(30C3), ャュョ(30E3,30E5,30E7)
        if cp in (0x30A1, 0x30A3, 0x30A5, 0x30A7, 0x30A9,
                  0x30C3, 0x30E3, 0x30E5, 0x30E7):
            has_small_kana = True
        # Hiragana small: ぁ-ぉ, っ, ゃゅょ
        if cp in (0x3041, 0x3043, 0x3045, 0x3047, 0x3049,
                  0x3063, 0x3083, 0x3085, 0x3087):
            has_small_kana = True

    has_any = has_dakuten or has_handakuten or has_thai_tone or has_small_kana or has_korean_mark

    return {
        'has_dakuten': has_dakuten,
        'has_handakuten': has_handakuten,
        'has_thai_tone': has_thai_tone,
        'has_small_kana': has_small_kana,
        'has_korean_mark': has_korean_mark,
        'has_any_vulnerable_mark': has_any,
    }


def main():
    con = duckdb.connect(database=":memory:")

    raw = con.execute(f"""
        SELECT
            CASE WHEN json_valid(names)
                 THEN json_extract_string(names, '$.primary')
                 ELSE names END AS alt_name,
            CASE WHEN json_valid(base_names)
                 THEN json_extract_string(base_names, '$.primary')
                 ELSE base_names END AS base_name
        FROM '{PARQUET_PATH}'
        WHERE names IS NOT NULL AND base_names IS NOT NULL
    """).df()

    # Audit both sides
    results = []
    for side, col in [('alt', 'alt_name'), ('base', 'base_name')]:
        marks = raw[col].apply(audit_marks).apply(pd.Series)
        row = {'side': side, 'total_rows': len(marks)}
        for mark_col in marks.columns:
            row[f'{mark_col}_count'] = marks[mark_col].sum()
            row[f'{mark_col}_pct'] = round(marks[mark_col].mean() * 100, 2)
        results.append(row)

    # Also count rows where EITHER side has vulnerable marks
    alt_marks = raw['alt_name'].apply(audit_marks).apply(pd.Series)
    base_marks = raw['base_name'].apply(audit_marks).apply(pd.Series)
    either = alt_marks | base_marks
    row = {'side': 'either', 'total_rows': len(either)}
    for mark_col in either.columns:
        row[f'{mark_col}_count'] = int(either[mark_col].sum())
        row[f'{mark_col}_pct'] = round(either[mark_col].mean() * 100, 2)
    results.append(row)

    out = pd.DataFrame(results)
    out.to_csv(OUTPUT_PATH, index=False)

    con.close()

    print(f"Wrote: {OUTPUT_PATH}")
    print()
    print("Rows with script-essential marks that naive accent stripping would destroy:")
    print()
    either_row = results[2]
    for mark in ['has_dakuten', 'has_handakuten', 'has_thai_tone', 'has_small_kana', 'has_korean_mark', 'has_any_vulnerable_mark']:
        count = either_row[f'{mark}_count']
        pct = either_row[f'{mark}_pct']
        label = mark.replace('has_', '').replace('_', ' ')
        print(f"  {label:30s} {count:>5d} rows  ({pct}%)")


if __name__ == "__main__":
    main()