# Can Foundation Models Wrangle Your Data?

**Authors:** Avanika Narayan, Ines Chami, Laurel Orr, Christopher Ré
**Venue:** Proceedings of the VLDB Endowment, Vol. 16, No. 4, pp. 738–746
**Year:** 2022 (published December 2022; arXiv May 2022)
**Bib key:** `narayan2022can`
**DOI:** 10.14778/3574245.3574258
**arXiv:** 2205.09911
**Code:** https://github.com/HazyResearch/fm_data_tasks

---

## What the paper does

This paper from the Hazy Research lab (Stanford) evaluates whether large foundation models (GPT-3, BERT variants) can perform classical data cleaning and integration tasks **zero-shot** — without any task-specific training data or fine-tuning.

They cast five data tasks as prompting problems:
1. **Entity matching** (are these records the same entity?)
2. **Data imputation** (fill in missing values)
3. **Error detection** (identify incorrect values)
4. **Data transformation** (normalize values to a canonical form)
5. **Schema matching** (map attribute names across schemas)

The key finding for entity matching: GPT-3 prompted with a description of the task and a few in-context examples achieves **state-of-the-art or near-SOTA accuracy** on several EM benchmarks, without any labeled training pairs.

---

## Key findings

- Foundation models achieve competitive performance on entity matching tasks even with **zero labeled pairs** (pure zero-shot) and further improve with few-shot in-context examples
- GPT-3 outperforms many fine-tuned models on textual EM
- On structured EM, the gap vs. fine-tuned approaches is larger — fine-tuning on labeled data still helps when data is available
- Data transformation (a form of canonicalization) is also addressed, though only at the schema/format level, not the semantic selection level

---

## Limitations

- Only English-language benchmarks
- Evaluates entity matching only — not which value to canonicalize after matching
- Foundation models are black boxes; cost and latency limit production use at scale
- GPT-3 at the time was available only via API

---

## Relevance to this paper

This is one of the two zero-shot LLM-based ER papers cited in the "LLM-based entity resolution" paragraph. It establishes that LLMs can do ER without labeled pairs — which motivates the broader question this paper asks: *if LLMs can do matching zero-shot, which conflicts actually require a model at all?*

The paper notes that Narayan et al. apply the same model uniformly to all pairs, without stratifying by conflict type. Our work argues this is wasteful: characterizing the conflict distribution first reveals that 75% of apparent conflicts don't need a model at all.
