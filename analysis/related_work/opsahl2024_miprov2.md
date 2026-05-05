# Optimizing Instructions and Demonstrations for Multi-Stage Language Model Programs (MIPROv2)

**Authors:** Krista Opsahl-Ong, Michael J. Ryan, Josh Purtell, David Broman, Christopher Potts, Matei Zaharia, Omar Khattab
**Venue:** arXiv preprint arXiv:2406.11695
**Year:** 2024
**Bib key:** `opsahl2024miprov2`
**arXiv:** 2406.11695

---

## What the paper does

MIPRO (Multiprompt Instruction PRoposal Optimizer) extends DSPy's optimization to jointly optimize both the **instruction text** and the **few-shot demonstrations** for every module in a multi-stage LM program.

Prior DSPy optimizers (BootstrapFewShot) only select demonstrations — they don't modify the instruction text. MIPRO adds instruction generation and uses **Bayesian optimization** to search over the combined space.

The algorithm:
1. **Bootstrap**: run the program on training inputs to collect high-scoring traces (as demo candidates)
2. **Propose instructions**: use an LM to generate multiple candidate instruction texts, grounded in program code + data + traces
3. **Bayesian search**: use a surrogate model (TPE-style) to efficiently search over combinations of (instruction, demos) for each module
4. **MIPROv2** is the production version with improved initialization and a corrected validation evaluation

---

## Key results

- Outperforms BootstrapFewShot on 5 of 7 diverse multi-stage programs using Llama-3-8B, by up to **13% accuracy**
- Joint instruction + demo optimization beats either alone on most tasks
- Requires a larger training set to benefit: with small training sets, the surrogate model has too little signal and the search becomes noisy

---

## Relevance to this paper

MIPROv2 is one of the five prompt strategies evaluated in the H1 classification experiments. The paper finds that **MIPROv2 selected zero demonstrations for all four local models** — the Bayesian optimizer converged to zero-shot, finding no demo set that improved on the hand-written instruction on the validation split.

This is consistent with the MIPRO paper's own caveat that larger training sets are needed. With only 182 training rows and a 25% validation split (46 rows), the surrogate model has insufficient data to find a better configuration than the baseline. The MIPROv2 results in this paper are therefore effectively zero-shot measurements, which the text makes explicit.
