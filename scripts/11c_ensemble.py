"""
11c_ensemble.py — Majority-vote ensemble over per-model best results

Takes the best-run CSV for each of N models, aligns rows by (short_name, long_name,
extra_content), and picks the majority-vote classification. Computes label accuracy
and selection accuracy for the ensemble vs. each individual model.

Usage:
    python 11c_ensemble.py
    python 11c_ensemble.py --threshold 0.67   # require 2/3 agreement (drop ties)

Output:
    ../analysis/names/dspy_ensemble_results.csv   — per-row ensemble predictions
    Prints per-model and ensemble accuracy to stdout
"""

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

# Best-run file for each model (file, label)
MODEL_FILES = {
    "Mistral-7B":     "../analysis/names/dspy_own_mistral.csv",           # own greedy 91.8% sel
    "Llama-3.1-8B":   "../analysis/names/dspy_h1_v3_llama3.1_8b.csv",     # haiku v3  90.1% sel (best for ensemble diversity)
    "Qwen-2.5-7B":    "../analysis/names/dspy_h1_v3_qwen2.5_7b.csv",      # haiku v3  92.6% sel
    "Qwen-2.5-14B":   "../analysis/names/dspy_own_qwen2.5_14b.csv",        # own greedy 93.4% sel
}

VALID_CLASSES = {"business_type", "location", "disambiguation", "noise"}


def selection_correct(predicted: str, actual: str) -> bool:
    """Selection is correct if both are business_type or both are not."""
    return (predicted == "business_type") == (actual == "business_type")


def load_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Normalise column name — older files use 'correct_answer', same as current
    if "correct_answer" not in df.columns and "actual" in df.columns:
        df = df.rename(columns={"actual": "correct_answer"})
    key_cols = ["short_name", "long_name", "extra_content", "correct_answer", "predicted"]
    df = df[key_cols].copy()
    # Drop duplicate keys (the ATM/Post Office row appears twice in eval — documented
    # in README §Evaluation Limitations). Dedup before merge so we don't get a
    # cross-product that inflates row count.
    df = df.drop_duplicates(subset=["short_name", "long_name", "extra_content"])
    return df


def majority_vote(votes: list[str], threshold: float = 0.0) -> str | None:
    """
    Return the plurality label. If threshold > 0, return None when the top vote
    share is below the threshold (caller treats this as abstain/skip).

    Tie-breaking: when multiple labels share the top count, prefer business_type
    if it is among the tied labels (selection errors from crossing the
    business_type boundary are the most impactful). Otherwise take the
    lexicographically first label for determinism.
    """
    counts = Counter(votes)
    top_count = counts.most_common(1)[0][1]
    if threshold > 0 and top_count / len(votes) < threshold:
        return None
    tied = sorted(label for label, c in counts.items() if c == top_count)
    return "business_type" if "business_type" in tied else tied[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Minimum vote share required to emit a prediction (0=always emit)")
    parser.add_argument("--output", default="../analysis/names/dspy_ensemble_results.csv")
    args = parser.parse_args()

    # Load all model CSVs
    dfs = {}
    for name, path in MODEL_FILES.items():
        p = Path(__file__).parent / path
        if not p.exists():
            print(f"  MISSING: {path} — skipping {name}")
            continue
        dfs[name] = load_df(str(p))
        print(f"  Loaded {name}: {len(dfs[name])} rows")

    if len(dfs) < 2:
        print("Need at least 2 model files to ensemble.")
        return

    # Align on (short_name, long_name, extra_content) — all models ran on the same eval set
    base = list(dfs.values())[0][["short_name", "long_name", "extra_content", "correct_answer"]].copy()
    for name, df in dfs.items():
        base = base.merge(
            df[["short_name", "long_name", "extra_content", "predicted"]].rename(
                columns={"predicted": f"pred_{name}"}
            ),
            on=["short_name", "long_name", "extra_content"],
            how="inner",
        )

    print(f"\nAligned rows: {len(base)}")

    pred_cols = [c for c in base.columns if c.startswith("pred_")]

    # Majority vote
    base["ensemble_vote"] = base[pred_cols].apply(
        lambda row: majority_vote(list(row), args.threshold), axis=1
    )
    abstained = base["ensemble_vote"].isna().sum()
    if abstained:
        print(f"  Abstained (below threshold): {abstained} rows")

    voted = base.dropna(subset=["ensemble_vote"])

    # ── Print per-model accuracy ───────────────────────────────────────────────
    print("\n── Per-model accuracy (on aligned rows) ──")
    print(f"{'Model':<18}  {'Label acc':>10}  {'Sel acc':>8}")
    print("-" * 42)
    for col in pred_cols:
        name = col.removeprefix("pred_")
        label_acc = (base[col] == base["correct_answer"]).mean()
        sel_acc   = base.apply(lambda r: selection_correct(r[col], r["correct_answer"]), axis=1).mean()
        print(f"  {name:<16}  {label_acc:>9.1%}  {sel_acc:>7.1%}")

    # ── Ensemble accuracy ─────────────────────────────────────────────────────
    print("\n── Ensemble (majority vote) ──")
    label_acc = (voted["ensemble_vote"] == voted["correct_answer"]).mean()
    sel_acc   = voted.apply(
        lambda r: selection_correct(r["ensemble_vote"], r["correct_answer"]), axis=1
    ).mean()
    coverage  = len(voted) / len(base)
    print(f"  Label accuracy:     {label_acc:.1%}  ({voted['ensemble_vote'].eq(voted['correct_answer']).sum()} / {len(voted)})")
    print(f"  Selection accuracy: {sel_acc:.1%}")
    print(f"  Coverage:           {coverage:.1%}  ({len(voted)} / {len(base)} rows)")

    # ── Per-class breakdown ───────────────────────────────────────────────────
    print("\n── Ensemble per-class accuracy ──")
    for cls in sorted(VALID_CLASSES):
        subset = voted[voted["correct_answer"] == cls]
        if len(subset) == 0:
            continue
        acc = (subset["ensemble_vote"] == subset["correct_answer"]).mean()
        print(f"  {cls:<18}  n={len(subset):>3}  accuracy={acc:.1%}")

    # ── Agreement stats ───────────────────────────────────────────────────────
    def agreement_count(row):
        votes = [row[c] for c in pred_cols]
        return Counter(votes).most_common(1)[0][1]

    base["max_agreement"] = base[pred_cols].apply(agreement_count, axis=1)
    print("\n── Vote agreement distribution ──")
    for k in range(1, len(pred_cols) + 1):
        n = (base["max_agreement"] == k).sum()
        if n:
            subset = base[base["max_agreement"] == k]
            s_acc = subset.apply(
                lambda r: selection_correct(r["ensemble_vote"] if pd.notna(r["ensemble_vote"]) else "disambiguation",
                                            r["correct_answer"]), axis=1
            ).mean()
            print(f"  {k}/{len(pred_cols)} agree: {n:>3} rows  sel_acc={s_acc:.1%}")

    # ── Save ──────────────────────────────────────────────────────────────────
    out_path = Path(__file__).parent / args.output
    base.to_csv(out_path, index=False)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
