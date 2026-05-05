# (Almost) All of Entity Resolution

**Authors:** Olivier Binette, Rebecca C. Steorts
**Venue:** Science Advances, Vol. 8, No. 12, Article eabi8021
**Year:** 2022 (published March 25, 2022)
**Bib key:** `binette2022almost`
**DOI:** 10.1126/sciadv.abi8021
**arXiv:** 2008.04443
**PMC:** PMC11636688

---

## What the paper does

A comprehensive methodological survey of entity resolution (record linkage, de-duplication) spanning foundational work from the 1940s–50s through modern Bayesian and deep learning approaches. Written for a broad audience; published in Science Advances (multidisciplinary).

The review organizes ER into a pipeline:
1. **Preprocessing** and blocking (candidate generation)
2. **Comparison** (feature extraction from record pairs)
3. **Classification** (match vs. non-match)
4. **Clustering** (grouping matched pairs into entities)
5. **Canonicalization** (merging a cluster into a single canonical record)

---

## Key contributions

- Consolidates ER literature across databases, statistics, and NLP communities, which use different terminology for the same problem
- Reviews blocking strategies, probabilistic (Fellegi-Sunter), Bayesian, and supervised/semi-supervised approaches
- **Explicitly identifies canonicalization as the least-studied stage**: most benchmarks evaluate only whether records are correctly linked, not which values should be retained
- Covers applications in human rights, census, medical records, and citation networks
- Discusses challenges of scalability, evaluation, and error propagation from linked data

---

## On canonicalization specifically

From the paper: canonicalization (also called "merging" or "data fusion") is the task of producing a single representative record from a cluster of matched records. The authors note:

> "Canonicalization, or data fusion, is arguably the least-studied stage of the entity resolution pipeline."

They describe naive approaches (majority vote, longest string, most recent value) and more principled methods (learned ranking, probabilistic consensus), but note the literature on this is sparse relative to the matching stage.

---

## Note on bib key

The original bib entry in this project used the key `steorts2022record` with an incorrect title ("Record linkage: A methodological review"). The actual paper is "(Almost) All of Entity Resolution" by **Binette and Steorts** (Binette is first author). The key has been corrected to `binette2022almost` and all `\cite` commands in main.tex updated accordingly.

---

## Relevance to this paper

This is the primary citation for the claim that canonicalization is the understudied step in the ER pipeline. The "Canonicalization as the understudied step" paragraph in related work directly builds on Binette & Steorts' observation. Our paper addresses this gap specifically for the name attribute in geospatial place data.
