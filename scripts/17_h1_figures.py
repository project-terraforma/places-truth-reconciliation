"""
17_h1_figures.py — Generate figures for H1 extra-content classification results.

Figures:
    analysis/names/figures/h1_model_comparison.png   — selection accuracy, all models × approaches
    analysis/names/figures/h1_per_class.png           — per-class label accuracy by model
    analysis/names/figures/h1_ensemble.png            — ensemble progression chart

Usage:
    python 17_h1_figures.py
"""

from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "analysis/names/figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Palette ────────────────────────────────────────────────────────────────────
C = {
    "haiku_v1":  "#3498db",   # blue
    "haiku_v3":  "#2980b9",   # dark blue
    "own_greedy":"#2ecc71",   # green
    "own_random":"#27ae60",   # dark green
    "mipro":     "#9b59b6",   # purple
    "zeroshot":  "#95a5a6",   # grey
    "ensemble":  "#e74c3c",   # red
    "rule":      "#f39c12",   # amber
    "bg":        "#f8f9fa",
}

# ─────────────────────────────────────────────────────────────────────────────
# Figure 1 — Model × approach selection accuracy grid
# ─────────────────────────────────────────────────────────────────────────────

# Verified against backing CSVs (binary selection metric, all 122 rows)
#   "—" → None  |  ‡ = clean re-run
data = {
    #  model           zeroshot  haiku_v1  haiku_v3  own_greedy  own_random  mipro
    "Phi-3 Mini\n3.8B":  [None,    86.9,     83.6,     79.5,       None,       None],
    "Mistral-7B":         [None,    87.7,     86.1,     91.8,       89.3,       88.5],
    "Llama-3.1-8B":       [None,    None,     86.1,     86.1,       None,       None],
    "Qwen-2.5-7B":        [None,    86.9,     90.2,     87.7,       86.1,       89.3],
    "Qwen-2.5-14B":       [93.4,    93.4,     None,     93.4,       None,       None],
    "Haiku\n(API)":       [95.9,    95.1,     96.7,     None,       94.3,       None],
}
approaches  = ["Zero-shot", "Haiku v1\n(greedy)", "Haiku v3\n(random‡)", "Own greedy", "Own random", "MIPROv2"]
colors_app  = [C["zeroshot"], C["haiku_v1"], C["haiku_v3"], C["own_greedy"], C["own_random"], C["mipro"]]
models      = list(data.keys())
n_models    = len(models)
n_app       = len(approaches)

fig, ax = plt.subplots(figsize=(12, 4.5))
bar_w   = 0.13
offsets = np.linspace(-(n_app - 1) / 2 * bar_w, (n_app - 1) / 2 * bar_w, n_app)
x       = np.arange(n_models)

for j, (approach, color, offset) in enumerate(zip(approaches, colors_app, offsets)):
    vals = [data[m][j] for m in models]
    for i, v in enumerate(vals):
        if v is None:
            continue
        bar = ax.bar(x[i] + offset, v - 75, bar_w, bottom=75, color=color,
                     zorder=3, alpha=0.9, edgecolor="white", linewidth=0.4)
        if v >= 90:
            ax.text(x[i] + offset, v + 0.4, f"{v:.0f}", ha="center", va="bottom",
                    fontsize=6.5, color="#2c3e50", fontweight="bold")

ax.set_xticks(x)
ax.set_xticklabels(models, fontsize=10)
ax.set_ylim(75, 101)
ax.set_ylabel("Selection accuracy (%)", fontsize=10)
ax.set_title("H1 Selection Accuracy — All Models × Prompt Strategies\n"
             "(binary metric: correct recommendation to keep longer or shorter name)",
             fontsize=11, pad=10)
ax.axhline(79.5,  color=C["rule"],     linewidth=1.2, linestyle="--", alpha=0.7, label="Rule baseline (79.5%)", zorder=2)
ax.axhline(95.0,  color=C["ensemble"], linewidth=1.2, linestyle="--", alpha=0.7, label="Ensemble majority (95.0%)", zorder=2)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_facecolor(C["bg"])
fig.patch.set_facecolor("white")

# Legend: approaches
patches = [mpatches.Patch(color=c, label=a.replace("\n", " "))
           for a, c in zip(approaches, colors_app)]
patches += [plt.Line2D([0], [0], color=C["rule"],     linestyle="--", linewidth=1.5, label="Rule baseline (79.5%)"),
            plt.Line2D([0], [0], color=C["ensemble"], linestyle="--", linewidth=1.5, label="4-model ensemble (95.0%)")]
ax.legend(handles=patches, fontsize=7.5, ncol=4, loc="lower right",
          framealpha=0.9, edgecolor="#ddd")

plt.tight_layout()
out = OUT_DIR / "h1_model_comparison.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 2 — Per-class label accuracy by model (best prompt per model)
# ─────────────────────────────────────────────────────────────────────────────

# From backing CSVs, best prompt per model
per_class = {
    # model           biz_type  location  disambig  noise   overall
    "Phi-3 Mini":     [72.1,    70.5,     67.9,     42.9,   68.9],
    "Mistral-7B":     [79.1,    90.9,     71.4,     71.4,   81.1],
    "Llama-3.1-8B":   [83.7,    90.9,     39.3,     57.1,   74.6],
    "Qwen-2.5-7B":    [93.0,    93.2,     53.6,     42.9,   81.1],
    "Qwen-2.5-14B":   [90.7,    95.5,     57.1,     85.7,   84.4],
    "Haiku\n(zero-shot)": [95.3, 97.7,   46.4,     85.7,   84.4],
    "Haiku\n(v3 clean)":  [95.3, 100.0,  46.4,     85.7,   85.2],
}
classes     = ["business_type", "location", "disambiguation", "noise", "overall"]
class_colors= ["#3498db", "#2ecc71", "#e74c3c", "#f39c12", "#2c3e50"]
class_labels= ["Business type", "Location", "Disambiguation", "Noise", "Overall"]

models_pc   = list(per_class.keys())
n_m         = len(models_pc)
n_c         = len(classes)
bar_w2      = 0.13
x2          = np.arange(n_m)
offsets2    = np.linspace(-(n_c - 1) / 2 * bar_w2, (n_c - 1) / 2 * bar_w2, n_c)

fig, ax = plt.subplots(figsize=(13, 4.5))
for j, (cls, color, label) in enumerate(zip(classes, class_colors, class_labels)):
    vals = [per_class[m][j] for m in models_pc]
    ax.bar(x2 + offsets2[j], vals, bar_w2, label=label, color=color,
           zorder=3, alpha=0.88, edgecolor="white", linewidth=0.4)

ax.set_xticks(x2)
ax.set_xticklabels(models_pc, fontsize=9.5)
ax.set_ylim(30, 107)
ax.set_ylabel("Label accuracy (%)", fontsize=10)
ax.set_title("H1 Per-Class Label Accuracy — Best Prompt per Model\n"
             "(disambiguation is the bottleneck class across all models)",
             fontsize=11, pad=10)
ax.axhline(100, color="#bdc3c7", linewidth=0.6, linestyle=":", zorder=1)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_facecolor(C["bg"])
fig.patch.set_facecolor("white")
ax.legend(fontsize=8.5, ncol=5, loc="upper left", framealpha=0.9, edgecolor="#ddd")

plt.tight_layout()
out = OUT_DIR / "h1_per_class.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 3 — Ensemble progression
# ─────────────────────────────────────────────────────────────────────────────

ensemble_steps = [
    ("Best individual\n(Qwen-2.5-14B)", 93.4,  122, "#3498db"),
    ("4-model\nmajority vote",          95.0,  122, "#2ecc71"),
    ("≥3/4 agreement\n(82% coverage)",  98.0,   99, "#e74c3c"),
]

fig, ax = plt.subplots(figsize=(6.5, 3.8))
for i, (label, acc, coverage, color) in enumerate(ensemble_steps):
    ax.bar(i, acc, color=color, zorder=3, width=0.5, alpha=0.9, edgecolor="white")
    ax.text(i, acc + 0.3, f"{acc:.1f}%", ha="center", va="bottom",
            fontsize=13, fontweight="bold", color="#2c3e50")
    coverage_pct = coverage / 122 * 100
    ax.text(i, 76, f"{coverage}/122 rows\n({coverage_pct:.0f}% coverage)",
            ha="center", va="bottom", fontsize=8.5, color="#555")

ax.set_xticks(range(len(ensemble_steps)))
ax.set_xticklabels([s[0] for s in ensemble_steps], fontsize=10)
ax.set_ylim(74, 102)
ax.set_ylabel("Selection accuracy (%)", fontsize=10)
ax.set_title("H1 Ensemble Progression\n"
             "Disagreement as an uncertainty signal for routing",
             fontsize=11, pad=10)
ax.axhline(79.5, color=C["rule"], linewidth=1.2, linestyle="--",
           alpha=0.7, label="Rule baseline (79.5%)")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_facecolor(C["bg"])
fig.patch.set_facecolor("white")
ax.legend(fontsize=9, loc="upper left")

# Annotation: routing implication
ax.annotate("18% abstained;\nroute to stronger model",
            xy=(2, 98.0), xytext=(2.35, 94),
            fontsize=8, color="#555",
            arrowprops=dict(arrowstyle="->", color="#999", lw=1.0))

plt.tight_layout()
out = OUT_DIR / "h1_ensemble.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")

print("\nAll H1 figures saved.")
