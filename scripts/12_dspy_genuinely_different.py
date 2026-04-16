"""
12_dspy_genuinely_different.py — DSPy evaluation for Hypothesis 2: name-pair relationship
classification in genuinely_different conflicts.

Purpose:
    Evaluate whether a small language model can classify the semantic relationship between
    two conflicting place names that normalization cannot reconcile — the 189 rows labeled
    `genuinely_different` in the conflict taxonomy (see README § ML Extension Hypotheses,
    Hypothesis 2).

    This is a structurally different task from Hypothesis 1 (11_dspy_extra_content.py):
    - H1 classifies a *fragment* (extra content) using lexical/semantic features.
    - H2 classifies a *relationship* between two full names using world knowledge
      (brand hierarchies, subsidiary naming conventions, abbreviation conventions,
      geographic context).

    Both use DSPy but require separate signatures and separate evaluation sets.

Input:
    analysis/names/name_genuinely_different_inspect.csv  — 189 genuinely-different rows
    Columns used: alt_name, base_name, alt_category, base_category, city, state

    NOTE: This file does not yet have `correct_answer` labels. Before running this
    script for evaluation, you must manually label a representative subset of rows with
    the relationship_type and recommended_action fields defined below. The script can
    run zero-shot (no labels) to generate predictions for manual review; it can run
    with full optimization once labels exist.

Output:
    analysis/names/dspy_h2_predictions.csv    — per-row predictions for manual review
    analysis/names/dspy_h2_results.csv        — per-row predictions with correctness flag
                                                (requires labeled input)
    analysis/names/dspy_h2_summary.csv        — accuracy by class and overall

Relationship taxonomy:
    same_entity_diff_name   Same real-world place, different provider naming conventions.
                            Examples: Citibanamex vs Citibank, Mishicot Fire Dept vs
                            Mishicot Volunteer Fire Depart, Barclays ATM vs Barclays Bank
                            Cash Machine.
                            → Abstain, or prefer by quality signal (completeness, recency).

    location_mismatch       Different branches of the same chain in different cities.
                            Examples: Sport Clips Panama City vs Sport Clips Lynn Haven.
                            → Flag as probable upstream matching error; do not select either.

    abbreviation_variant    One name is a shortened form of the other not caught by the
                            normalization pipeline (Thai ม. = มหาวิทยาลัย, informal
                            abbreviations, partial brand names).
                            → Prefer the expanded/full form.

    test_data               Placeholder, synthetic, or obviously invalid names.
                            Examples: "PUBLIC location 324234 #%&*".
                            → Discard both records.

Usage:
    # Zero-shot prediction (no labels needed — output for manual review):
    python 12_dspy_genuinely_different.py --zero-shot

    # Evaluate against labeled subset (requires manually labeled CSV):
    python 12_dspy_genuinely_different.py --labeled-path analysis/names/gd_labeled.csv

    # With optimizer:
    python 12_dspy_genuinely_different.py --labeled-path ... --optimize

Dependencies:
    pip install dspy-ai anthropic pandas
"""

import argparse
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


# ── Paths ──────────────────────────────────────────────────────────────────────

GD_PATH          = "../analysis/names/name_genuinely_different_inspect.csv"
PREDICTIONS_PATH = "../analysis/names/dspy_h2_predictions.csv"
RESULTS_PATH     = "../analysis/names/dspy_h2_results.csv"
SUMMARY_PATH     = "../analysis/names/dspy_h2_summary.csv"

VALID_RELATIONSHIP_TYPES = {
    "same_entity_diff_name",
    "location_mismatch",
    "abbreviation_variant",
    "test_data",
}
VALID_ACTIONS = {"abstain", "prefer_alt", "prefer_base", "flag_for_review", "discard"}

TRAIN_FRAC  = 0.6
RANDOM_SEED = 42


# ══════════════════════════════════════════════════════════════════════════════
#  DSPy SIGNATURE — Hypothesis 2
# ══════════════════════════════════════════════════════════════════════════════

class NamePairRelationshipClassifier(dspy.Signature):
    """
    Classify the semantic relationship between two conflicting place names.

    Context: Both names refer to the same real-world place (the record pair has already
    been matched), but normalization cannot reconcile them — they are structurally different
    names. Your job is to classify WHY they differ and what action to take.

    Four relationship types:

    - same_entity_diff_name: The two names refer to the same real-world entity but use
      different naming conventions — different language, different level of formality,
      subsidiary vs. parent brand, or different provider-specific naming.
      Examples:
        "Citibanamex 30 Av. Playa Del Carmen" vs "Citibank" (Mexican subsidiary vs global brand)
        "Mishicot Fire Dept" vs "Mishicot Volunteer Fire Depart" (abbreviation + informal vs formal)
        "Barclays ATM" vs "Barclays Bank Cash Machine" (same object, different descriptions)
        "Robert Walters Group" vs "Robert Walters Recruitment Ireland" (parent vs regional office)
      Action: abstain (neither is definitively better without external quality signals) or
              prefer whichever name is more complete/formal.

    - location_mismatch: The two names are for different branches of the same chain in
      different geographic locations. This indicates a probable upstream matching error —
      the two records should not have been paired.
      Examples:
        "Sport Clips Haircuts of Panama City - Cahall's Deli Plaza" vs
        "Sport Clips Haircuts of Lynn Haven" (different cities)
        "Arnold Clark Glasgow Vauxhall" vs "Arnold Clark Glasgow Hamilton Road Vauxhall"
        (possibly same dealership, but the street location differs)
      Action: flag_for_review — do not select either; escalate to matching pipeline.

    - abbreviation_variant: One name is a shortened or abbreviated form of the other that
      the normalization pipeline failed to catch. This includes Thai/Japanese abbreviations,
      informal short forms, and partial brand names where substring containment fails.
      Examples:
        "สำนักงานอธิการบดี ม.รามคำแหง" vs "สำนักงานอธิการบดี มหาวิทยาลัยรามคำแหง"
        (ม. is the standard Thai abbreviation for มหาวิทยาลัย = university)
        "B&B Hôtels" vs "B&B Hôtel Lyon Ouest Tassin"
        (plural vs singular brand + branch — subset containment failed on the suffix difference)
      Action: prefer whichever name is the expanded/full form.

    - test_data: At least one name is clearly a placeholder, synthetic entry, or invalid
      string that should never appear in a production dataset.
      Examples: "PUBLIC location 324234 #%&*", "PUBLIC LOCATION NAME EXTERNALID NAME"
      Action: discard — flag both records for removal.

    When classifying, consider:
    - The category field (if both sides agree on category, that supports same_entity_diff_name)
    - The city/state field (if the city matches, location_mismatch is less likely)
    - Whether one name contains the other after some transformation
      (supports abbreviation_variant over same_entity_diff_name)
    """

    alt_name:      str = dspy.InputField(desc="First place name (alt/primary candidate)")
    base_name:     str = dspy.InputField(desc="Second place name (base candidate)")
    alt_category:  str = dspy.InputField(desc="Place category from the alt record (may be empty)")
    base_category: str = dspy.InputField(desc="Place category from the base record (may be empty)")
    city:          str = dspy.InputField(desc="City where the place is located (may be empty)")
    state:         str = dspy.InputField(desc="State/region where the place is located (may be empty)")

    relationship_type: str = dspy.OutputField(
        desc="One of exactly: same_entity_diff_name, location_mismatch, abbreviation_variant, test_data"
    )
    recommended_action: str = dspy.OutputField(
        desc="One of exactly: abstain, prefer_alt, prefer_base, flag_for_review, discard"
    )
    confidence: str = dspy.OutputField(
        desc="One of exactly: high, medium, low"
    )
    reasoning: str = dspy.OutputField(
        desc=(
            "One sentence explaining the relationship classification. "
            "Be specific about which features of the name pair drove the decision."
        )
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MODULE
# ══════════════════════════════════════════════════════════════════════════════

class NamePairRelationshipModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.classify = dspy.ChainOfThought(NamePairRelationshipClassifier)

    def forward(
        self,
        alt_name: str,
        base_name: str,
        alt_category: str,
        base_category: str,
        city: str,
        state: str,
    ):
        pred = self.classify(
            alt_name=alt_name,
            base_name=base_name,
            alt_category=alt_category,
            base_category=base_category,
            city=city,
            state=state,
        )
        rt = pred.relationship_type.strip().lower().replace(" ", "_").replace("-", "_")
        if rt not in VALID_RELATIONSHIP_TYPES:
            for v in VALID_RELATIONSHIP_TYPES:
                if v in rt:
                    rt = v
                    break
            else:
                rt = "same_entity_diff_name"
        pred.relationship_type = rt
        return pred


# ══════════════════════════════════════════════════════════════════════════════
#  METRIC (only meaningful when labeled data is available)
# ══════════════════════════════════════════════════════════════════════════════

def exact_match(example, pred, trace=None):
    return int(pred.relationship_type == example.correct_answer)


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_gd_rows(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ["alt_name", "base_name"]:
        if col not in df.columns:
            raise ValueError(f"Required column '{col}' not found in {path}")
    for col in ["alt_category", "base_category", "city", "state"]:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    return df


def df_to_examples(df: pd.DataFrame, has_labels: bool) -> list[dspy.Example]:
    examples = []
    for _, row in df.iterrows():
        kwargs = dict(
            alt_name=str(row["alt_name"]),
            base_name=str(row["base_name"]),
            alt_category=str(row.get("alt_category", "")),
            base_category=str(row.get("base_category", "")),
            city=str(row.get("city", "")),
            state=str(row.get("state", "")),
        )
        if has_labels and "correct_answer" in df.columns:
            kwargs["correct_answer"] = str(row["correct_answer"])
        ex = dspy.Example(**kwargs).with_inputs(
            "alt_name", "base_name", "alt_category", "base_category", "city", "state"
        )
        examples.append(ex)
    return examples


def train_test_split(examples, train_frac, seed):
    import random
    rng = random.Random(seed)
    shuffled = list(examples)
    rng.shuffle(shuffled)
    split = int(len(shuffled) * train_frac)
    return shuffled[:split], shuffled[split:]


# ══════════════════════════════════════════════════════════════════════════════
#  EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def run_zero_shot(module, df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        try:
            pred = module(
                alt_name=str(row["alt_name"]),
                base_name=str(row["base_name"]),
                alt_category=str(row.get("alt_category", "")),
                base_category=str(row.get("base_category", "")),
                city=str(row.get("city", "")),
                state=str(row.get("state", "")),
            )
            rows.append({
                "alt_name":          row["alt_name"],
                "base_name":         row["base_name"],
                "city":              row.get("city", ""),
                "predicted_type":    pred.relationship_type,
                "recommended_action": pred.recommended_action,
                "confidence":        getattr(pred, "confidence", ""),
                "reasoning":         getattr(pred, "reasoning", ""),
            })
        except Exception as e:
            rows.append({
                "alt_name":          row["alt_name"],
                "base_name":         row["base_name"],
                "city":              row.get("city", ""),
                "predicted_type":    "error",
                "recommended_action": "",
                "confidence":        "",
                "reasoning":         str(e),
            })
    return pd.DataFrame(rows)


def run_evaluation(module, examples: list[dspy.Example]) -> pd.DataFrame:
    rows = []
    for ex in examples:
        try:
            pred = module(
                alt_name=ex.alt_name,
                base_name=ex.base_name,
                alt_category=ex.alt_category,
                base_category=ex.base_category,
                city=ex.city,
                state=ex.state,
            )
            rows.append({
                "alt_name":          ex.alt_name,
                "base_name":         ex.base_name,
                "correct_answer":    ex.correct_answer,
                "predicted":         pred.relationship_type,
                "recommended_action": pred.recommended_action,
                "confidence":        getattr(pred, "confidence", ""),
                "reasoning":         getattr(pred, "reasoning", ""),
                "correct":           int(pred.relationship_type == ex.correct_answer),
            })
        except Exception as e:
            rows.append({
                "alt_name":          ex.alt_name,
                "base_name":         ex.base_name,
                "correct_answer":    ex.correct_answer,
                "predicted":         "error",
                "recommended_action": "",
                "confidence":        "",
                "reasoning":         str(e),
                "correct":           0,
            })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  LM SETUP
# ══════════════════════════════════════════════════════════════════════════════

def configure_lm(provider: str, model: str):
    if provider == "anthropic":
        lm = dspy.LM(f"anthropic/{model}")
    elif provider == "openai":
        lm = dspy.LM(f"openai/{model}")
    elif provider == "ollama":
        lm = dspy.LM(f"ollama_chat/{model}", api_base="http://localhost:11434")
    elif provider == "together":
        lm = dspy.LM(f"together_ai/{model}")
    elif provider == "groq":
        lm = dspy.LM(f"groq/{model}")
    else:
        lm = dspy.LM(model)
    dspy.configure(lm=lm)
    print(f"LM configured: {provider}/{model}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="DSPy Hypothesis 2 — name-pair relationship classification")
    parser.add_argument("--provider",      default="ollama",                  help="LM provider: ollama|anthropic|together|groq|openai")
    parser.add_argument("--model",         default="mistral",                 help="Model name (default: mistral via Ollama)")
    parser.add_argument("--zero-shot",     action="store_true",               help="Run zero-shot predictions (no labels needed)")
    parser.add_argument("--labeled-path",  default=None,                      help="Path to manually labeled CSV (required for eval/optimize)")
    parser.add_argument("--optimize",      action="store_true",               help="Run BootstrapFewShot optimizer")
    parser.add_argument("--save-path",     default=None,                      help="Save optimized program JSON")
    parser.add_argument("--load-path",     default=None,                      help="Load saved program JSON")
    parser.add_argument("--gd-path",       default=GD_PATH,                   help="Path to genuinely_different CSV")
    args = parser.parse_args()

    configure_lm(args.provider, args.model)
    module = NamePairRelationshipModule()

    if args.load_path:
        module.load(args.load_path)

    # ── Zero-shot mode: generate predictions for manual review ────────────────
    if args.zero_shot:
        print(f"Loading genuinely_different rows from: {args.gd_path}")
        df = load_gd_rows(args.gd_path)
        print(f"Running zero-shot predictions on {len(df)} rows...")
        results = run_zero_shot(module, df)
        results.to_csv(PREDICTIONS_PATH, index=False)
        print(f"Predictions saved to: {PREDICTIONS_PATH}")
        print("\nRelationship type distribution (zero-shot):")
        print(results["predicted_type"].value_counts())
        print("\nRecommended action distribution:")
        print(results["recommended_action"].value_counts())
        return

    # ── Evaluation mode: requires labeled CSV ────────────────────────────────
    if not args.labeled_path:
        print(
            "No labeled data provided. Use --zero-shot to generate predictions for manual "
            "review, then add 'correct_answer' labels to the output and re-run with "
            "--labeled-path for accuracy evaluation."
        )
        return

    print(f"Loading labeled examples from: {args.labeled_path}")
    df = load_gd_rows(args.labeled_path)
    examples = df_to_examples(df, has_labels=True)
    examples = [e for e in examples if hasattr(e, "correct_answer") and e.correct_answer in VALID_RELATIONSHIP_TYPES]
    print(f"Loaded {len(examples)} labeled examples")

    train_ex, eval_ex = train_test_split(examples, TRAIN_FRAC, RANDOM_SEED)
    print(f"Train: {len(train_ex)}  |  Eval: {len(eval_ex)}")

    if args.optimize:
        from dspy.teleprompt import BootstrapFewShot
        optimizer = BootstrapFewShot(metric=exact_match, max_bootstrapped_demos=4, max_labeled_demos=4)
        module = optimizer.compile(module, trainset=train_ex)
        if args.save_path:
            Path(args.save_path).parent.mkdir(parents=True, exist_ok=True)
            module.save(args.save_path)
            print(f"Saved to: {args.save_path}")

    results = run_evaluation(module, eval_ex)
    overall = results["correct"].mean()
    print(f"\nOverall accuracy: {overall:.1%}  ({results['correct'].sum()} / {len(results)})")
    for rt in sorted(VALID_RELATIONSHIP_TYPES):
        subset = results[results["correct_answer"] == rt]
        if len(subset) > 0:
            print(f"  {rt:<25}  n={len(subset):>3}  accuracy={subset['correct'].mean():.1%}")

    results.to_csv(RESULTS_PATH, index=False)
    print(f"\nResults saved to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
