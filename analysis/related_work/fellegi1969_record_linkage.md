# A Theory of Record Linkage

**Authors:** Ivan P. Fellegi, Alan B. Sunter
**Venue:** Journal of the American Statistical Association (JASA)
**Year:** 1969
**Bib key:** `fellegi1969theory`
**DOI:** not digitally archived (pre-DOI era)

---

## What the paper does

Fellegi and Sunter formalized the record linkage problem as a statistical decision framework. Given a pair of records, the question is: do they refer to the same real-world entity (a "match") or not (a "non-match")?

Their key insight was to frame this as a likelihood-ratio test. Each comparison field (name, address, date of birth, etc.) contributes a weight based on two conditional probabilities:

- **m-probability**: the probability that the field agrees given the pair *is* a match
- **u-probability**: the probability that the field agrees given the pair is *not* a match

The overall weight for a pair is the log-likelihood ratio across all compared fields. Pairs above a high threshold are classified as matches; pairs below a low threshold are non-matches; pairs in between go to clerical review.

The paper proves that this decision rule is optimal (minimizes false positives and false negatives simultaneously) under the assumption that comparison fields are conditionally independent given match/non-match status.

---

## Key contributions

1. **Probabilistic decision framework** replacing ad-hoc string matching rules
2. **M/U probability model** that separated match probability from field-level agreement rates
3. **Three-way decision**: match, non-match, or "possible match requiring human review" — the first principled treatment of uncertainty in record linkage
4. **Optimality proof**: the likelihood-ratio rule minimizes both error types simultaneously (a Neyman-Pearson result applied to database records)

---

## Limitations and critiques

- Assumes conditional independence of comparison fields — violated when name and address fields are correlated
- Does not address *how* to estimate m- and u-probabilities (EM algorithm for this came later, from Dempster et al. 1977 and Jaro 1989)
- Binary match/non-match: doesn't model the full entity cluster (see Binette & Steorts 2022)
- Canonicalization (which value to keep after matching) is entirely out of scope

---

## Relevance to this paper

This is the foundational citation for the entity resolution field. The paper cites it in the introduction and related work as the origin of probabilistic record linkage. It motivates why modern work (DeepMatcher, Ditto, LLM-based ER) is situated within a well-developed matching literature — and why the *canonicalization* step has been comparatively neglected: Fellegi-Sunter only asks "are these the same entity?", not "which value should we keep?"
