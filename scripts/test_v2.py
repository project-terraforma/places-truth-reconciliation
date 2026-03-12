"""
test_v2.py — Regression tests for 08_name_structure.py (v2)

Validates the two-tier classification logic against specific examples from manual
inspection. Covers all Tier 1 labels, CJK/Thai/Korean scripts, and the edge cases
that were misclassified in v1 due to Unicode bugs.

Run from the same directory as 08_name_structure.py:
    python test_v2.py

All tests with an expected_tier1 must pass (✓). Tests without an expected value
print their result for manual inspection.
"""

import sys
import os
import pandas as pd

# Import 08_name_structure from the same directory as this test file.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
script = importlib.import_module("08_name_structure")

l2 = script.l2
norm_compare = script.norm_compare
norm_compare_hira = script.norm_compare_hira
classify_row = script.classify_row
precompute_forms = script.precompute_forms

PASS = 0
FAIL = 0


def test_pair(alt, base, expected_tier1=None, expected_subtag=None, desc=""):
    """Classify a single pair and print results."""
    global PASS, FAIL
    df = pd.DataFrame([{
        'alt_name': alt, 'base_name': base,
        'alt_address': None, 'base_address': None,
        'city': None, 'state': None,
        'alt_category': None, 'base_category': None,
        'alt_confidence': None, 'base_confidence': None,
        'alt_sources': None, 'base_sources': None, 'id': 'test'
    }])
    df = precompute_forms(df)
    row = df.iloc[0]
    tier1, subtags = classify_row(row)

    status = ""
    ok = True
    if expected_tier1:
        if tier1 != expected_tier1:
            status = f"✗ (expected {expected_tier1})"
            ok = False
        else:
            status = "✓"
    if expected_subtag:
        if expected_subtag not in subtags:
            status = f"✗ (missing subtag {expected_subtag})"
            ok = False
        elif not status:
            status = "✓"

    if expected_tier1 or expected_subtag:
        if ok:
            PASS += 1
        else:
            FAIL += 1

    print(f"{status:20s} tier1={tier1:28s} subtags={subtags}")
    print(f"                     alt: {alt}")
    print(f"                     base: {base}")
    if desc:
        print(f"                     note: {desc}")
    print()


def section(title):
    print("=" * 100)
    print(title)
    print("=" * 100)
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  BUG 1: l2() ASCII-only regex destroyed non-Latin scripts
# ══════════════════════════════════════════════════════════════════════════════

section("BUG 1 FIX: Unicode-aware l2() preserves CJK/Thai/Korean")

test_pair(
    'วัดห้วยปราบ',
    'วัดห้วยปราบ ต. บ่อวิน อ.ศรีราชา ชลบุรี',
    'subset', desc='Thai temple + location. Was: diacritic_variant')

test_pair(
    'ローソン',
    'ローソン いわき下好間店',
    'subset', 'branch_suffix', 'Lawson + branch. Was: diacritic_variant')

test_pair(
    'JINS',
    'JINS イオンモール宮崎店',
    'subset', 'branch_suffix', 'Brand + mall location. Was: spacing_variant')

test_pair(
    'Agaligo clinic โบทอก ฟิลเลอร์ ร้อยไหม ปรับรูปหน้า เสริมจมูก',
    'Agaligo Clinic',
    'subset', desc='Name + Thai services list. Was: spacing_variant')

test_pair(
    'The North Face',
    'THE NORTH FACE (ザ・ノース・フェイス) 北千住マルイ',
    'subset', desc='Brand + kana + location. Was: spacing_variant')

test_pair(
    '百十',
    '百十 なんばこめじるし店',
    'subset', 'branch_suffix', 'Brand kanji + branch. Was: diacritic_variant')

test_pair(
    'すき家',
    'すき家 札幌北郷店',
    'subset', 'branch_suffix', 'Sukiya + branch. Was: diacritic_variant')

test_pair(
    'セブンイレブン',
    'セブンイレブン 波崎土合南店',
    'subset', 'branch_suffix', '7-Eleven + branch. Was: diacritic_variant')

test_pair(
    '西野山団地',
    '西野山団地 バス停',
    'subset', 'facility_suffix', 'Housing complex + bus stop. Was: diacritic_variant')


# ══════════════════════════════════════════════════════════════════════════════
#  BUG 2: strip_accents_py() destroyed Japanese dakuten and Thai tone marks
# ══════════════════════════════════════════════════════════════════════════════

section("BUG 2 FIX: strip_accents preserves dakuten and tone marks")

# Verify that l2 preserves Japanese voiced consonants and Thai tones
print("  l2 preservation checks:")
assert 'バ' in l2('バス停'), "Japanese dakuten (バ) destroyed by l2"
print("    ✓ l2('バス停') preserves バ (dakuten intact)")
assert 'ห้' in l2('ห้วย'), "Thai mai tho (ห้) destroyed by l2"
print("    ✓ l2('ห้วย') preserves ห้ (tone mark intact)")
PASS += 2
print()


# ══════════════════════════════════════════════════════════════════════════════
#  BUG 3: Fullwidth spaces (U+3000) invisible to subtag detection
# ══════════════════════════════════════════════════════════════════════════════

section("BUG 3 FIX: Fullwidth space (U+3000) detected as spacing subtag")

test_pair(
    '麺屋 克',           # ASCII space U+0020
    '麺屋\u3000克',      # Fullwidth space U+3000
    'normalization_equivalent', 'spacing', 'Fullwidth vs ASCII space. Was: minor_variant')

test_pair(
    'スナック ほしや',     # ASCII space
    'スナック\u3000ほしや', # Fullwidth space
    'normalization_equivalent', 'spacing', 'Katakana snack bar — fullwidth space variant')


# ══════════════════════════════════════════════════════════════════════════════
#  NORMALIZATION EQUIVALENTS
# ══════════════════════════════════════════════════════════════════════════════

section("NORMALIZATION EQUIVALENTS — spacing")

test_pair(
    'からみそラーメン ふくろう 刈谷店',
    'からみそラーメンふくろう刈谷店',
    'normalization_equivalent', 'spacing', 'Japanese spacing. Was: diacritic_variant')

test_pair(
    '船員保険北海道健康管理センター',
    '船員保険 北海道健康管理センター',
    'normalization_equivalent', 'spacing', 'Japanese spacing. Was: diacritic_variant')

test_pair(
    'PhotoColorLab',
    'Photo Color Lab',
    'normalization_equivalent', 'spacing', 'Compound split')

test_pair(
    'Dance4Life',
    'Dance 4 Life',
    'normalization_equivalent', 'spacing', 'Compound split')

section("NORMALIZATION EQUIVALENTS — punctuation")

test_pair(
    'ビジネスホテル・キャッスル',
    'ビジネスホテルキャッスル',
    'normalization_equivalent', 'punctuation', 'Nakaguro (・). Was: diacritic_variant')

test_pair(
    'Farmers Insurance David Hiney',
    'Farmers Insurance - David Hiney',
    'normalization_equivalent', 'punctuation', 'Dash as separator')

test_pair(
    'Dana Stampi s.r.l.',
    'Dana Stampi SRL',
    'normalization_equivalent', 'punctuation', 'Abbreviation dots')

test_pair(
    'Samantha Sachau D.P.T., P.T.',
    'Samantha Sachau, DPT,PT',
    'normalization_equivalent', 'punctuation', 'Abbreviation dots + commas')

test_pair(
    'Kosmetiketage Nofretete',
    'KOSMETIK-ETAGE-NOFRETETE',
    'normalization_equivalent', 'punctuation', 'Compound split + dashes')

section("NORMALIZATION EQUIVALENTS — conjunction")

test_pair(
    'Howarth Timber and Building Supplies',
    'Howarth Timber & Building Supplies',
    'normalization_equivalent', 'conjunction', 'and ↔ &')

test_pair(
    'Acqua e Sapone',
    'Acqua & Sapone',
    'normalization_equivalent', 'conjunction', 'Italian e ↔ &')

test_pair(
    'António Sousa Baltazar & Filhos',
    'Antonio Sousa Baltazar e Filhos',
    'normalization_equivalent', 'conjunction', 'Portuguese e ↔ & + diacritic')

section("NORMALIZATION EQUIVALENTS — mixed / other")

test_pair(
    'origensbistro',
    "Origen's Bistrô",
    'normalization_equivalent', 'spacing', 'Apostrophe + diacritic + spacing')

test_pair(
    'Crepes&Coffee',
    'Crepes & Coffee',
    'normalization_equivalent', 'punctuation', 'Punctuation + spacing + conjunction')

test_pair(
    'ホテル オホーツクイン',
    'ホテルオホーツク・イン',
    'normalization_equivalent', 'punctuation', 'Spacing + nakaguro')

section("NORMALIZATION EQUIVALENTS — script form (katakana ↔ hiragana)")

test_pair(
    'コインランドリーはなこ',
    'コインランドリーハナコ',
    'normalization_equivalent', 'script_form', 'Hiragana ↔ katakana for はなこ/ハナコ')


# ══════════════════════════════════════════════════════════════════════════════
#  SUBSETS
# ══════════════════════════════════════════════════════════════════════════════

section("SUBSETS — parenthetical")

test_pair(
    'วัดวาลุการาม',
    'วัดวาลุการาม (หนองผักบุ้ง)',
    'subset', 'parenthetical', 'Temple + village parenthetical')

test_pair(
    'Moana',
    'Moana (モアナ)',
    'subset', 'parenthetical', 'Name + kana reading parenthetical')

test_pair(
    'โรงเรียนวรสารพิทยา',
    'โรงเรียนวรสารพิทยา ( เซนต์โยเซฟยานนาวา )',
    'subset', 'parenthetical', 'School + parenthetical alt name')

section("SUBSETS — branch suffix")

test_pair(
    'ドミノ・ピザ',
    'ドミノ・ピザ大江店',
    'subset', 'branch_suffix', "Domino's Pizza + Oe branch (店)")


# ══════════════════════════════════════════════════════════════════════════════
#  GENUINELY DIFFERENT (must NOT be normalized)
# ══════════════════════════════════════════════════════════════════════════════

section("GENUINELY DIFFERENT — must not be normalized away")

test_pair(
    'เนื้อต้มแม่สมร สะพานขาว',
    'เนื้อต้มสะพานขาว',
    'genuinely_different', desc='Mae Samon vs plain — different owner/brand')

test_pair(
    'ก๋วยเตี๋ยวปลาในตำนาน นครนายก',
    'ก๋วยเตี๋ยวปลาสดนครนายก',
    'genuinely_different', desc='Legendary fish vs Fresh fish — different words')

test_pair(
    "Sport Clips Haircuts of Panama City - Cahall's Deli Plaza",
    'Sport Clips Haircuts of Lynn Haven',
    'genuinely_different', desc='Different locations entirely')


# ══════════════════════════════════════════════════════════════════════════════
#  EDGE CASES (documented limitations)
# ══════════════════════════════════════════════════════════════════════════════

section("EDGE CASES — documented limitations, inspect manually")

test_pair(
    'สำนักงานอธิการบดี ม.รามคำแหง',
    'สำนักงานอธิการบดี มหาวิทยาลัยรามคำแหง',
    desc='Thai abbreviation (ม. vs มหาวิทยาลัย) — needs lookup table')

test_pair(
    'คลีนิคบ้านหมอ',
    'คลีนิกบ้านหมอ',
    desc='Thai spelling variant (คลีนิค vs คลินิก)')

test_pair(
    'ミカモラィディングクラブ',
    'ミカモライディングクラブ',
    desc='Small kana ラィ vs ライ')

test_pair(
    'いきなり! ステーキ 出雲斐川町',
    'いきなりステーキ出雲斐川町店',
    desc='! punctuation + spacing + 店 suffix')

test_pair(
    '숙명여자대학교 박물관·미술관',
    '숙명여자대학교박물관',
    desc='Korean — longer name has additional department (미술관)')


# ══════════════════════════════════════════════════════════════════════════════
#  l2() UNICODE PRESERVATION VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════

section("l2() UNICODE PRESERVATION — all scripts must survive")

examples = [
    ('ローソン',              'Japanese katakana'),
    ('วัดห้วยปราบ',      'Thai'),
    ('숙명여자대학교',          'Korean'),
    ('Коллегия адвокатов', 'Russian'),
    ('Photo Color Lab',    'Latin'),
]
for text, script_name in examples:
    result = l2(text)
    assert len(result) > 0, f"l2() destroyed {script_name} text: '{text}' → ''"
    print(f"  ✓ l2({text:30s}) → '{result}'  ({script_name})")
    PASS += 1

print()
print("v1 would have produced '' for all non-Latin scripts above.")


# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

print()
print("=" * 100)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    print("SOME TESTS FAILED — see ✗ marks above")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
print("=" * 100)