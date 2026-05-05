# Canonicalization of Database Records using Adaptive Similarity Measures

**Authors:** Aron Culotta, Michael Wick, Robert Hall, Matthew Marzilli, Andrew McCallum
**Venue:** Proceedings of the 13th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining
**Year:** 2007
**Bib key:** `culotta2007canonicalization`
**DOI:** 10.1145/1281192.1281217
**PDF:** https://people.cs.umass.edu/~mccallum/papers/canonical-kdd07.pdf

---

## What the paper does

One of the few papers that directly addresses the **canonicalization** (merging) step of entity resolution. Given a cluster of records identified as referring to the same entity, what should the canonical representation look like?

The paper frames canonicalization as finding a string that is "central" — most similar to all the records in the cluster under a given edit distance measure. Rather than using a fixed edit distance, they **learn** the edit costs from labeled examples.

Two approaches:
1. **Distance-based canonicalization**: find the string that minimizes total edit distance to all cluster members. Different edit cost matrices produce different canonical forms (e.g., lowering deletion costs favors abbreviated forms; lowering insertion costs favors expanded forms).
2. **Ranking-based canonicalization**: learn a preference ranking over candidate canonical strings using feature-based methods (linear classifier over string features).

Both are trained from a small amount of manually annotated data.

---

## Key contributions

- First learned approach to canonicalization (prior work was all rule-based or naive heuristics)
- Shows that the choice of edit costs significantly affects canonical form quality — abbreviations vs. expansions, etc.
- Feature-based ranking outperforms distance-based canonicalization on the evaluation dataset
- Demonstrates that even small amounts of labeled data improve canonicalization quality substantially

---

## Evaluation

Applied to a real-world publications database (author name canonicalization — "A. McCallum" vs. "Andrew McCallum" vs. "A. K. McCallum"). Evaluated by comparing generated canonical forms to gold-standard human annotations.

---

## Limitations

- Requires a fixed vocabulary of candidate canonical strings from within the cluster (can't generate new strings)
- Only addresses within-cluster canonicalization (which record to pick), not the harder case where the canonical value might not appear in any record
- Evaluated only on English author names — limited generalization to multilingual or place-name data
- From 2007 — predates neural representations; all features are hand-engineered character-level statistics

---

## Relevance to this paper

This is an optional citation for the "Canonicalization as the understudied step" paragraph — it's one of the earliest papers to treat canonicalization as a first-class learning problem rather than a post-processing heuristic.

It supports the claim that the canonicalization problem has received little attention: this 2007 KDD paper is one of only a handful that address it directly, and even it requires a small labeled dataset, which this paper avoids.

**Whether to add this citation**: the current paper already cites Binette & Steorts for the "understudied step" claim. Culotta et al. would be a supporting citation but may add length without being essential. Discuss with your advisor — it strengthens the historical argument but isn't required.
