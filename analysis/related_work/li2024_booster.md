# BoostER: Leveraging Large Language Models for Enhancing Entity Resolution

**Authors:** Huahang Li, Shuangyin Li, Fei Hao, Chen Jason Zhang, Yuanfeng Song, Lei Chen
**Venue:** Companion Proceedings of the ACM Web Conference 2024 (WWW '24)
**Year:** 2024
**Bib key:** `li2024booster`
**DOI:** 10.1145/3589335.3651245
**arXiv:** 2403.06434

---

## What the paper does

BoostER is a demonstration system (4-page WWW companion paper) that addresses a practical constraint: LLM API calls have a per-token cost, so you can't afford to send all candidate pairs to an LLM. The paper proposes a **budget-constrained** approach to LLM-assisted entity resolution.

The core idea:

1. Run a traditional ER system first (blocking + classifier) to get an initial distribution of match/non-match predictions
2. Design a greedy algorithm that selects the *most informative* matching questions to ask the LLM within a given API budget
3. Use LLM responses to refine the initial distribution (Bayesian update)
4. The selection criterion balances: expected accuracy gain vs. token cost

---

## Key contributions

- First to explicitly model **budget constraints** for LLM-enhanced ER
- Greedy selection of questions to maximize expected accuracy improvement per API dollar
- Demonstrates that a small budget (e.g., 10% of pairs sent to LLM) recovers most of the accuracy gains from sending all pairs
- Works as a post-processing layer on top of any existing ER system

---

## Limitations

- 4-page system demonstration, not a full research paper — limited ablations and theoretical justification
- Evaluated on a small number of benchmark datasets
- Addresses only the **matching** step; no canonicalization
- Budget model assumes independent pair decisions (ignores global consistency across clusters)

---

## Note on the wrong placeholder

The original bib entry `zhang2023large` in this project cited a completely unrelated 2023 paper about node classification on graphs. This has been replaced with the correct BoostER citation as `li2024booster`. All `\cite{zhang2023large}` references in main.tex have been updated to `\cite{li2024booster}`.

---

## Relevance to this paper

BoostER is cited to illustrate that the LLM-based ER literature has begun to grapple with cost constraints. However, BoostER's approach to cost management (budget over *which pairs to send*) is different from this paper's approach (characterize the conflict distribution to identify *which pairs need a model at all*). BoostER reduces API calls within the matching step; this paper's pipeline eliminates the need for any model on 75% of pairs in the canonicalization step.
