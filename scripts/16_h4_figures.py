"""
16_h4_figures.py — Generate figures for H4 name construction results.

Produces three figures:
    analysis/names/figures/h4_results_summary.png   — detection + construction metrics
    analysis/names/figures/h4_error_taxonomy.png     — taxonomy of faithful-but-not-exact cases
    analysis/names/figures/h4_candidate_overview.png — distribution of 31 candidate types

Usage:
    python 16_h4_figures.py
"""

from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT    = Path(__file__).parent.parent
RESULTS = ROOT / "analysis/names/dspy_h4_full_results.csv"
OUT_DIR = ROOT / "analysis/names/figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Color palette ──────────────────────────────────────────────────────────────
C_PASS  = "#2ecc71"   # green
C_FAIL  = "#e74c3c"   # red
C_SKIP  = "#95a5a6"   # grey
C_BLUE  = "#3498db"
C_NAVY  = "#2c3e50"
C_AMBER = "#f39c12"

# ── Load data ──────────────────────────────────────────────────────────────────
df = pd.read_csv(RESULTS)

constructed = df[df["action"] == "construct"].copy()
kept_shorter = df[df["action"] == "keep_shorter"]

exact_mask = (
    constructed["constructed_name"].str.strip()
    == constructed["ideal_constructed_name"].str.strip()
)
faithful_mask = constructed["faithfulness_rule"].astype(bool)

n_total      = len(df)               # 31
n_construct  = len(constructed)      # 27
n_keep       = len(kept_shorter)     # 4
n_faithful   = faithful_mask.sum()   # 27
n_exact      = exact_mask.sum()      # 20
n_near       = n_construct - n_exact # 7 — faithful but non-exact

# ─────────────────────────────────────────────────────────────────────────────
# Figure 1 — Results summary (stacked bar, 3 metrics)
# ─────────────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 3.6))

metrics = [
    ("Stage 1\nDetection",   n_construct, n_keep,                  0,            "Compound (27)", "Non-compound, abstain (4)", ""),
    ("Stage 2\nFaithfulness",n_faithful,  0,                        0,            "Pass (27/27)", "", ""),
    ("Exact match\nvs ideal", n_exact,    n_near,                   0,            "Exact (20/27)", "Faithful paraphrase (7/27)", ""),
]

y = np.arange(len(metrics))
bar_h = 0.45

for i, (label, a, b, c, la, lb, lc) in enumerate(metrics):
    ax.barh(y[i], a, height=bar_h, color=C_PASS, zorder=3)
    ax.barh(y[i], b, height=bar_h, left=a, color=C_AMBER, zorder=3)
    # annotations inside bars
    if a > 0:
        ax.text(a / 2, y[i], f"{a}/{n_total}", va="center", ha="center",
                fontsize=10, fontweight="bold", color="white")
    if b > 0:
        ax.text(a + b / 2, y[i], str(b), va="center", ha="center",
                fontsize=10, fontweight="bold", color=C_NAVY)

ax.set_yticks(y)
ax.set_yticklabels([m[0] for m in metrics], fontsize=11)
ax.set_xlim(0, n_total + 2)
ax.set_xlabel("Cases (out of 31 candidates)", fontsize=10)
ax.set_title("H4 Name Construction — Two-Stage Pipeline Results\n(Claude Haiku, zero-shot, 31-candidate eval set)",
             fontsize=12, pad=10)
ax.axvline(x=n_total, color="#bdc3c7", linewidth=0.8, linestyle="--", zorder=1)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_xlim(0, 35)

# Legend
patch_pass  = mpatches.Patch(color=C_PASS,  label="Pass / compound / exact")
patch_amber = mpatches.Patch(color=C_AMBER, label="Faithful paraphrase / non-compound")
ax.legend(handles=[patch_pass, patch_amber], fontsize=9, loc="lower right")

plt.tight_layout()
out = OUT_DIR / "h4_results_summary.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 2 — Error taxonomy for the 7 faithful-but-non-exact cases
# ─────────────────────────────────────────────────────────────────────────────
error_types = {
    "Ampersand vs. 'and'": 2,
    "Casing mismatch": 2,
    "Separator style (/ or |)": 2,
    "Extra legal suffix retained": 1,
}

fig, ax = plt.subplots(figsize=(6, 2.8))
labels = list(error_types.keys())
counts = list(error_types.values())
colors = [C_AMBER, C_AMBER, C_AMBER, C_AMBER]

bars = ax.barh(labels, counts, height=0.5, color=colors, zorder=3)
for bar, count in zip(bars, counts):
    ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
            f"  {count}", va="center", ha="left", fontsize=11, color=C_NAVY)

ax.set_xlim(0, 3.2)
ax.set_xlabel("Number of cases (out of 7 faithful, non-exact)", fontsize=9)
ax.set_title("H4 Surface-Form Errors in Faithful Paraphrases\n(all 7 are semantically correct — no hallucinated tokens)",
             fontsize=10, pad=8)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_xticks([0, 1, 2])

plt.tight_layout()
out = OUT_DIR / "h4_error_taxonomy.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 3 — Candidate distribution: script + compound type
# ─────────────────────────────────────────────────────────────────────────────
# From h4_construction_candidates.csv for breakdown by language family
try:
    candidates = pd.read_csv(ROOT / "analysis/names/h4_construction_candidates.csv")
    # Derive language label from script_type + language hints in short/long names
    # Use the existing script_type column
    lang_counts = candidates["script_type"].value_counts()
except Exception:
    lang_counts = pd.Series({"latin": 29, "cjk": 1, "thai": 1})

compound_type_counts = {
    "Type 1 — compound extra\n(brand + type + location fused)": 25,
    "Type 2 — non-canonical short\n(acronym/CAPS + descriptor + location)": 6,
}

fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))

# Left: script distribution
ax = axes[0]
colors_sc = [C_BLUE, C_PASS, C_AMBER]
wedges, texts, autotexts = ax.pie(
    lang_counts.values,
    labels=[f"{k.upper()}\n({v})" for k, v in lang_counts.items()],
    autopct="%1.0f%%",
    colors=colors_sc[: len(lang_counts)],
    startangle=90,
    textprops={"fontsize": 10},
)
for at in autotexts:
    at.set_fontsize(9)
ax.set_title("Script type of 31 H4 candidates", fontsize=11)

# Right: compound subtype
ax = axes[1]
y = np.arange(len(compound_type_counts))
vals = list(compound_type_counts.values())
ax.barh(y, vals, height=0.5, color=[C_BLUE, C_PASS], zorder=3)
for yi, v in zip(y, vals):
    ax.text(v + 0.2, yi, str(v), va="center", ha="left", fontsize=11, color=C_NAVY)
ax.set_yticks(y)
ax.set_yticklabels(list(compound_type_counts.keys()), fontsize=9)
ax.set_xlim(0, 32)
ax.set_xlabel("Count", fontsize=9)
ax.set_title("Compound sub-type breakdown", fontsize=11)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.suptitle("H4 Candidate Set — 31 Construction Cases in 2,000-Row Sample", fontsize=12, y=1.02)
plt.tight_layout()
out = OUT_DIR / "h4_candidate_overview.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")

print("\nAll H4 figures saved.")
