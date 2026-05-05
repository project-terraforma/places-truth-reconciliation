# Entity Matching using Large Language Models

**Authors:** Ralph Peeters, Aaron Steiner, Christian Bizer
**Venue:** arXiv preprint arXiv:2310.11244 (submitted October 2023; updated to v4 October 2024)
**Year:** 2023
**Bib key:** `peeters2023entity`
**arXiv:** 2310.11244

---

## What the paper does

A systematic comparison of large language models for entity matching, covering both commercial (GPT-3.5, GPT-4) and open-source models that can run locally. The authors evaluate a range of prompt design choices:

- **Serialization**: how records are formatted as text (JSON, attribute-value pairs, natural language descriptions)
- **Demonstration selection**: how few-shot examples are chosen (random, stratified, similarity-based)
- **Zero-shot vs. few-shot**: effect of including examples in the prompt
- **Model size and type**: GPT-4 vs. GPT-3.5 vs. open-source alternatives

They evaluate on standard EM benchmarks (Structured: Amazon-Google, WDC; Textual; Dirty).

---

## Key findings

- Prompting large commercial LLMs with serialized records achieves **competitive or SOTA performance** on entity matching benchmarks relative to fine-tuned smaller models
- Serialization method matters: JSON-style attribute-value format generally outperforms natural language prose
- Few-shot demonstrations improve results, but demonstration selection strategy has limited impact
- GPT-4 outperforms GPT-3.5 substantially on harder matching tasks
- Open-source models lag commercial ones, especially on complex or multilingual records

---

## Limitations

- English-dominated benchmarks
- Matching step only — no canonicalization
- API costs at scale (motivates approaches like BoostER's budget-constrained selection)
- Evaluation on existing benchmarks, which may not reflect real-world data quality issues

---

## Note on authorship

The original bib entry in this project listed only two authors (Peeters and Bizer). The paper has three authors: Ralph Peeters, Aaron Steiner, Christian Bizer. The bib entry has been corrected.

---

## Relevance to this paper

The second of the two zero-shot/few-shot LLM ER papers cited alongside Narayan et al. (2022). Peeters et al. provide a more systematic evaluation of prompt strategies across multiple LLMs, while Narayan et al. established the zero-shot feasibility. Together they motivate the claim that LLM-based ER is now viable — setting up the paper's argument that the interesting question is not *whether* to use a model, but *on which rows* to use one.
