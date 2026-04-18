"""
14_dspy_name_construction.py — Hypothesis 4: Name Construction from Compound Extra Content

Purpose:
    Identify and resolve a specific failure mode in the H1 pipeline: cases where the extra
    content in a subset conflict contains BOTH a business-type descriptor AND a location
    qualifier. In these cases, neither existing name is the correct canonical form:

        Short name:  Arthur Murray            (too generic — loses business type)
        Long name:   Arthur Murray Dance Studio - Beaverton  (has business type but also location noise)
        Ideal:       Arthur Murray Dance Studio              (generated — does not exist in data)

    This script:
      1. Loads the compound cases identified during manual analysis (all named in the script).
      2. Runs Stage 1: compound detection — asks the model to decompose the extra content
         into business-type tokens and location tokens separately.
      3. Runs Stage 2: name synthesis — generates the canonical name from short_name +
         business-type tokens, constrained to be faithful (all output tokens appear in long_name).
      4. Applies a faithfulness check to every constructed name.
      5. Saves predictions for human evaluation (ground truth cannot be machine-verified).

Cases identified in the 2,000-row dataset (all 5 are manually listed here because the
eval set is too small for automated accuracy measurement):

    Latin script:
    - Arthur Murray / Arthur Murray Dance Studio - Beaverton   → Arthur Murray Dance Studio
    - Dog's Shop / Dog's Shop Pampulha - Pet Shop              → Dog's Shop Pet Shop (or Dog's Shop)
    - Me n Moms / Me n Moms Baby Care & Kids Store in Barasar  → Me n Moms Baby Care & Kids Store

    Japanese (CJK) script:
    - カレット / カレット洋菓子店 矢田店   → カレット洋菓子店   (strip 矢田店 branch suffix)
    - ローソン / ローソン いわき下好間店   → ローソン          (pure branch, no type to keep)

Note on ローソン: the extra content (いわき下好間店) is a branch-location suffix with no
business-type component. The correct action here is keep_shorter (ローソン alone), not
construction. Stage 1 should detect this as non-compound. It is included to test that the
pipeline correctly abstains from construction when there is no business-type token.

Faithfulness constraint:
    For Latin script: every whitespace-separated token in constructed_name must appear as
    a substring of long_name (case-insensitive).
    For CJK script: every character in constructed_name must appear in long_name (since
    CJK has no whitespace word boundaries). This is weaker but sufficient to prevent
    hallucination of new characters.

Usage:
    python 14_dspy_name_construction.py
    python 14_dspy_name_construction.py --model claude-haiku-4-5-20251001
    python 14_dspy_name_construction.py --model ollama/qwen2.5:7b

Dependencies:
    pip install dspy-ai anthropic pandas
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import dspy
except ImportError:
    sys.exit("dspy-ai is required: pip install dspy-ai")


# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT              = Path(__file__).parent.parent
RESULTS_PATH      = ROOT / "analysis/names/dspy_h4_results.csv"
FULL_RESULTS_PATH = ROOT / "analysis/names/dspy_h4_full_results.csv"
CANDIDATES_PATH   = ROOT / "analysis/names/h4_construction_candidates.csv"


# ── Compound cases — manually identified in the 2,000-row dataset ─────────────
#
# These are the universe of name-construction candidates found during analysis.
# Each row: (short_name, long_name, script_type, note)
# The note describes what the ideal constructed name should look like — this is
# the human ground truth used for qualitative evaluation.

COMPOUND_CASES = [
    {
        "short_name":   "Arthur Murray",
        "long_name":    "Arthur Murray Dance Studio - Beaverton",
        "extra_content": "dance studio beaverton",
        "script_type":  "latin",
        "note":         "Beaverton is a city in Oregon; 'dance studio' is the business type. "
                        "Ideal: 'Arthur Murray Dance Studio'.",
    },
    {
        "short_name":   "Dog's Shop",
        "long_name":    "Dog's Shop Pampulha - Pet Shop",
        "extra_content": "pampulha pet shop",
        "script_type":  "latin",
        "note":         "Pampulha is a neighborhood in Belo Horizonte, Brazil; 'pet shop' is "
                        "the business type. Ideal: 'Dog's Shop Pet Shop' or just 'Dog's Shop'.",
    },
    {
        "short_name":   "Me n Moms",
        "long_name":    "Me n Moms Baby Care & Kids Store in Barasar",
        "extra_content": "baby care kids store in barasar",
        "script_type":  "latin",
        "note":         "Barasar is a locality in West Bengal; 'baby care & kids store' is the "
                        "business type. Ideal: 'Me n Moms Baby Care & Kids Store'.",
    },
    {
        "short_name":   "カレット",
        "long_name":    "カレット洋菓子店 矢田店",
        "extra_content": "洋菓子店 矢田店",
        "script_type":  "cjk",
        "note":         "洋菓子店 = Western confectionery store (business type). "
                        "矢田店 = Yata branch (location suffix — 矢田 is a district in Tokoname, "
                        "Aichi Prefecture). The character 店 (store/branch) appears in both: "
                        "洋菓子店 closes a compound noun; 矢田店 is a branch-naming particle. "
                        "Ideal: 'カレット洋菓子店' (keep business type, strip branch suffix).",
    },
    {
        "short_name":   "ローソン",
        "long_name":    "ローソン いわき下好間店",
        "extra_content": "いわき下好間店",
        "script_type":  "cjk",
        "note":         "いわき下好間店 = Lawson Iwaki-Shimokoshima branch. This is a pure branch "
                        "location with no business-type component (Lawson is already known as a "
                        "convenience store). Expected: Stage 1 detects as NON-compound; correct "
                        "action is keep_shorter (ローソン). Included as a negative test case.",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
#  STAGE 1: COMPOUND DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class CompoundDetector(dspy.Signature):
    """
    Determine whether extra content in a place name contains BOTH a business-type descriptor
    AND a location qualifier — a compound that makes the long name unsuitable as a canonical
    form without modification.

    A compound extra content fuses two semantically distinct components:
    1. Business-type: describes what KIND of place this is (e.g. "dance studio", "pet shop",
       "洋菓子店" = confectionery store, "baby care & kids store").
    2. Location: a proper noun identifying a geographic place (city, neighborhood, district,
       branch location) that was appended to disambiguate, not as part of the canonical name
       (e.g. "beaverton", "pampulha", "矢田店" = Yata branch, "in barasar").

    If BOTH components are present, the long name should not be selected as-is — neither
    the long name (has location noise) nor the short name (loses business type) is ideal.
    A new name must be constructed.

    If only ONE component is present (only business type, or only location), return
    is_compound = False. The existing H1 pipeline handles these cases correctly.

    For CJK script: pay careful attention to branch-naming suffixes. In Japanese, 店 (ten/mise)
    can close a compound noun (洋菓子店 = confectionery store) or serve as a branch suffix
    (矢田店 = Yata branch). The distinction depends on whether the preceding characters name
    a product category or a geographic place.
    """

    short_name:    str = dspy.InputField(desc="The shorter core place name")
    long_name:     str = dspy.InputField(desc="The longer name containing extra content")
    extra_content: str = dspy.InputField(desc="The extra content the long name adds beyond the short name")
    script_type:   str = dspy.InputField(desc="Script family: 'latin', 'cjk', or 'thai'")

    is_compound:       bool = dspy.OutputField(
        desc="True if extra_content contains BOTH a business-type component AND a location component"
    )
    biz_type_tokens:   str  = dspy.OutputField(
        desc="The portion of extra_content that describes the business type. Empty string if is_compound is False."
    )
    location_tokens:   str  = dspy.OutputField(
        desc="The portion of extra_content that is a location/branch qualifier. Empty string if is_compound is False."
    )
    reasoning:         str  = dspy.OutputField(
        desc="One or two sentences explaining the compound decomposition. For CJK, explain the morpheme boundary decision."
    )


# ══════════════════════════════════════════════════════════════════════════════
#  STAGE 2: NAME SYNTHESIS
# ══════════════════════════════════════════════════════════════════════════════

class NameConstructor(dspy.Signature):
    """
    Construct the canonical place name from a short name and a business-type descriptor,
    dropping the location qualifier.

    The long name has been identified as compound: it contains both a business-type
    descriptor (which should be kept) and a location qualifier (which should be dropped).
    Your task is to synthesize the canonical name by combining the short_name with the
    business-type portion only.

    Constraints — you MUST follow these:
    1. FAITHFULNESS: Every word in the constructed name must appear in the long_name.
       Do not invent words, correct spellings, or reorder beyond what is needed.
    2. MINIMALISM: Do not add any word that is not in biz_type_tokens or short_name.
    3. PUNCTUATION: Reproduce punctuation (hyphens, ampersands, apostrophes) exactly as
       they appear in the long_name. Do not add or remove punctuation.
    4. CJK: For Japanese/Chinese names with no word boundaries, concatenate without spaces
       unless the long_name uses spaces between components.
    5. ABSTAIN: If you cannot construct a faithful name (e.g. the biz_type_tokens are
       themselves ambiguous or empty), output constructed_name = short_name and set
       faithfulness_confident = False.

    Example:
        short_name = "Arthur Murray"
        long_name  = "Arthur Murray Dance Studio - Beaverton"
        biz_type_tokens = "dance studio"
        → constructed_name = "Arthur Murray Dance Studio"
        (drop "- Beaverton"; reproduce capitalization from long_name)

    Japanese example:
        short_name = "カレット"
        long_name  = "カレット洋菓子店 矢田店"
        biz_type_tokens = "洋菓子店"
        → constructed_name = "カレット洋菓子店"
        (concatenate without inserting space; 矢田店 is stripped)
    """

    short_name:      str = dspy.InputField(desc="The shorter core place name")
    long_name:       str = dspy.InputField(desc="The longer name (source of truth for tokens and casing)")
    biz_type_tokens: str = dspy.InputField(desc="The business-type portion to retain from the extra content")
    script_type:     str = dspy.InputField(desc="Script family: 'latin', 'cjk', or 'thai'")

    constructed_name:       str  = dspy.OutputField(
        desc="The canonical name: short_name combined with biz_type_tokens, with correct casing from long_name"
    )
    faithfulness_confident: bool = dspy.OutputField(
        desc="True if every token in constructed_name is present in long_name; False if uncertain"
    )
    construction_reasoning: str  = dspy.OutputField(
        desc="One sentence describing how the name was assembled and what was dropped."
    )


# ══════════════════════════════════════════════════════════════════════════════
#  FAITHFULNESS CHECK (deterministic post-processing)
# ══════════════════════════════════════════════════════════════════════════════

def check_faithfulness(constructed: str, long_name: str, script_type: str) -> bool:
    """
    Verify that the constructed name does not hallucinate tokens absent from long_name.

    Latin: every whitespace-separated token in constructed must appear as a case-insensitive
    substring of long_name.

    CJK: every character in constructed must appear in long_name. This is weaker (it allows
    character reordering) but sufficient to catch the most dangerous failure: inventing
    characters that appear in neither source name.
    """
    if script_type == "cjk":
        return all(ch in long_name for ch in constructed)
    else:
        tokens = constructed.lower().split()
        long_lower = long_name.lower()
        return all(tok in long_lower for tok in tokens)


# ══════════════════════════════════════════════════════════════════════════════
#  MODULES
# ══════════════════════════════════════════════════════════════════════════════

class CompoundDetectorModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.detect = dspy.ChainOfThought(CompoundDetector)

    def forward(self, short_name, long_name, extra_content, script_type):
        return self.detect(
            short_name=short_name,
            long_name=long_name,
            extra_content=extra_content,
            script_type=script_type,
        )


class NameConstructorModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.construct = dspy.ChainOfThought(NameConstructor)

    def forward(self, short_name, long_name, biz_type_tokens, script_type):
        return self.construct(
            short_name=short_name,
            long_name=long_name,
            biz_type_tokens=biz_type_tokens,
            script_type=script_type,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def configure_lm(model: str) -> None:
    """Configure DSPy LM from a model string (anthropic/*, ollama/*, openai/*)."""
    if model.startswith("ollama/"):
        lm = dspy.LM(model=model, api_base="http://localhost:11434", api_key="ollama")
    elif "/" not in model:
        # Bare model name — assume Anthropic
        lm = dspy.LM(model=f"anthropic/{model}", api_key=os.environ.get("ANTHROPIC_API_KEY"))
    else:
        lm = dspy.LM(model=model, api_key=os.environ.get("ANTHROPIC_API_KEY"))
    dspy.configure(lm=lm)
    print(f"LM configured: {model}")


def main():
    parser = argparse.ArgumentParser(description="H4: Name construction from compound extra content")
    parser.add_argument(
        "--model",
        default="anthropic/claude-haiku-4-5-20251001",
        help="LM to use (default: claude-haiku-4-5-20251001)",
    )
    parser.add_argument(
        "--input-csv",
        default=None,
        help="CSV of candidates to process (default: uses hardcoded 5 cases). "
             "Pass path to h4_construction_candidates.csv to run all identified candidates.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path (default: dspy_h4_results.csv for hardcoded cases, "
             "dspy_h4_full_results.csv for --input-csv)",
    )
    args = parser.parse_args()

    configure_lm(args.model)

    # Load cases — either from CSV or hardcoded list
    if args.input_csv:
        df_in = pd.read_csv(args.input_csv)
        cases = []
        for _, row in df_in.iterrows():
            cases.append({
                "short_name":    row["short_name"],
                "long_name":     row["long_name"],
                "extra_content": row["extra_content"],
                "script_type":   row["script_type"],
                "note":          f"Ideal: {row['ideal_constructed_name']}  ({row['construction_reason']})",
                "ideal":         row["ideal_constructed_name"],
            })
        out_path = Path(args.output) if args.output else FULL_RESULTS_PATH
    else:
        cases = COMPOUND_CASES
        for c in cases:
            c.setdefault("ideal", None)
        out_path = Path(args.output) if args.output else RESULTS_PATH

    detector    = CompoundDetectorModule()
    constructor = NameConstructorModule()

    results = []

    print(f"\nProcessing {len(cases)} cases...\n")
    print("─" * 72)

    for case in cases:
        short      = case["short_name"]
        long       = case["long_name"]
        extra      = case["extra_content"]
        script     = case["script_type"]
        note       = case["note"]
        ideal      = case.get("ideal")

        print(f"  Short: {short!r}")
        print(f"  Long:  {long!r}")
        print(f"  Extra: {extra!r}")

        # ── Stage 1: Compound detection ────────────────────────────────────────
        det = detector(
            short_name=short,
            long_name=long,
            extra_content=extra,
            script_type=script,
        )

        is_compound    = det.is_compound
        biz_tokens     = det.biz_type_tokens.strip()
        loc_tokens     = det.location_tokens.strip()
        det_reasoning  = det.reasoning

        print(f"  Stage 1 → is_compound={is_compound}")
        print(f"    biz_type: {biz_tokens!r}")
        print(f"    location: {loc_tokens!r}")
        print(f"    reason:   {det_reasoning}")

        row = {
            "short_name":        short,
            "long_name":         long,
            "extra_content":     extra,
            "script_type":       script,
            "note":              note,
            "ideal_constructed_name": ideal,
            "is_compound":       is_compound,
            "biz_type_tokens":   biz_tokens,
            "location_tokens":   loc_tokens,
            "detection_reasoning": det_reasoning,
            "constructed_name":  None,
            "faithfulness_model": None,
            "faithfulness_rule":  None,
            "construction_reasoning": None,
            "action":            None,
        }

        # ── Stage 2: Name synthesis (only if compound) ─────────────────────────
        if is_compound and biz_tokens:
            con = constructor(
                short_name=short,
                long_name=long,
                biz_type_tokens=biz_tokens,
                script_type=script,
            )

            constructed        = con.constructed_name.strip()
            faith_model        = con.faithfulness_confident
            con_reasoning      = con.construction_reasoning

            # Deterministic faithfulness check overrides model's self-assessment
            faith_rule = check_faithfulness(constructed, long, script)

            print(f"  Stage 2 → constructed: {constructed!r}")
            print(f"    faithfulness (model): {faith_model}  |  (rule): {faith_rule}")
            print(f"    reason: {con_reasoning}")

            action = "construct" if faith_rule else "abstain_unfaithful"

            row.update({
                "constructed_name":       constructed,
                "faithfulness_model":     faith_model,
                "faithfulness_rule":      faith_rule,
                "construction_reasoning": con_reasoning,
                "action":                 action,
            })
        else:
            action = "keep_shorter" if not is_compound else "abstain_no_biz_tokens"
            row["action"] = action
            print(f"  Stage 2 → skipped (not compound) → action: {action}")

        print()
        results.append(row)

    # ── Summary ────────────────────────────────────────────────────────────────
    print("─" * 72)
    print("\nSummary:")
    for r in results:
        action = r["action"]
        name   = r["constructed_name"] or r["short_name"]
        print(f"  {r['short_name']!r:30s} → {action:25s} → {name!r}")

    # ── Save ───────────────────────────────────────────────────────────────────
    df = pd.DataFrame(results)

    # When ideal_constructed_name is available, compute exact-match accuracy
    if "ideal_constructed_name" in df.columns and df["ideal_constructed_name"].notna().any():
        constructed_mask = df["action"] == "construct"
        if constructed_mask.sum() > 0:
            exact = (
                df.loc[constructed_mask, "constructed_name"].str.strip() ==
                df.loc[constructed_mask, "ideal_constructed_name"].str.strip()
            )
            print(f"\nExact-match vs ideal: {exact.sum()}/{constructed_mask.sum()} "
                  f"({exact.mean():.1%}) constructed names match ideal exactly")

    df.to_csv(out_path, index=False)
    print(f"\nSaved → {out_path}")

    # ── Faithfulness audit ────────────────────────────────────────────────────
    constructed_rows = df[df["action"] == "construct"]
    if len(constructed_rows) > 0:
        passed = constructed_rows["faithfulness_rule"].sum()
        print(f"\nFaithfulness check: {passed}/{len(constructed_rows)} constructed names "
              f"passed deterministic token-in-source test")

        failed = constructed_rows[constructed_rows["faithfulness_rule"].eq(False)]
        if len(failed) > 0:
            print("\nFaithfulness FAILURES (hallucinated tokens):")
            for _, r in failed.iterrows():
                print(f"  long:        {r['long_name']!r}")
                print(f"  constructed: {r['constructed_name']!r}")
                missing = [
                    tok for tok in r["constructed_name"].lower().split()
                    if tok not in r["long_name"].lower()
                ]
                print(f"  missing tokens: {missing}")


if __name__ == "__main__":
    main()
