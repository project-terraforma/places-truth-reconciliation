# GER-LLM: Efficient and Effective Geospatial Entity Resolution with Large Language Model

**Authors:** Haojia Zhu, Zhicheng Li, Jiahui Jin
**Venue:** Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing (EMNLP 2025)
**Year:** 2025
**Bib key:** `zhu2025gerllm`
**ACL Anthology:** https://aclanthology.org/2025.emnlp-main.1186/

---

## What the paper does

GER-LLM addresses geospatial entity resolution (GER) — identifying which records across different datasets refer to the same physical place. Standard LLM-based ER approaches fail on geospatial data because:

1. **Spatial reasoning**: LLMs lack geographic understanding (they don't know that two records 50 meters apart are more likely to match than two records 5 km apart)
2. **Inference cost**: geospatial datasets contain millions of candidate pairs; sending all of them to an LLM is prohibitive

GER-LLM addresses both problems:

- **Spatially-informed blocking**: adaptive quadtree partitioning divides the geographic space into cells, with finer granularity in dense areas (cities) and coarser granularity in sparse areas (rural). Area of Interest (AOI) detection preserves records near cell boundaries.
- **Group prompting with graph-based conflict resolution**: instead of asking the LLM about one pair at a time, it sends a group of candidate pairs together and enforces global consistency (if A matches B and B matches C, then A matches C).

---

## Key contributions

1. **Quadtree-based blocking** that adapts to geographic density — reduces candidate pairs while preserving high recall
2. **Group prompting** for batch LLM evaluation — reduces API calls per candidate pair
3. **Graph-based conflict resolution** to enforce transitivity in match decisions
4. State-of-the-art results on real-world geospatial datasets

---

## Limitations

- Addresses only the **matching** step — which records are the same place
- Does not address canonicalization (which attribute values to retain)
- Evaluated on standard geospatial ER benchmarks, not specifically on multi-source place databases like Overture Maps
- Published at EMNLP 2025 — full details may differ from the ACL Anthology preprint

---

## Relevance to this paper

GER-LLM is the most directly related prior work in terms of domain (geospatial place data + LLMs). It is added to the new "Geospatial entity resolution" paragraph in the related work section.

The comparison is instructive:
- GER-LLM solves the **matching** step (are these the same place?) using LLMs with spatial awareness
- This paper solves the **canonicalization** step (which name should we keep?) using small local models after matching is already complete

Both papers make the same high-level observation — that applying LLMs uniformly to all pairs is wasteful — and address it via selective application. GER-LLM achieves this through spatial blocking; this paper achieves it through conflict-type characterization.
