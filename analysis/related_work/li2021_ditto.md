# Deep Entity Matching with Pre-Trained Language Models (Ditto)

**Authors:** Yuliang Li, Jinfeng Li, Yoshihiko Suhara, AnHai Doan, Wang-Chiew Tan
**Venue:** Proceedings of the VLDB Endowment, Vol. 14, No. 1, pp. 50–60
**Year:** 2021
**Bib key:** `li2021ditto`
**DOI:** 10.14778/3421424.3421431
**Code:** https://github.com/megagonlabs/ditto

---

## What the paper does

Ditto applies pre-trained transformer language models (BERT, DistilBERT, RoBERTa) to entity matching. It frames EM as a **sequence-pair classification** problem: serialize the two records as text, concatenate them with a separator token, and fine-tune a transformer to predict match/non-match.

Three key optimizations beyond naive fine-tuning:

1. **Domain knowledge injection**: span tagging to highlight important attribute values (type tags, summarized attribute values)
2. **Data augmentation**: generates synthetic training examples by swapping attribute values between matched pairs
3. **Summarization**: TF-IDF-based truncation of long records to fit within transformer context windows

---

## Key results

- Up to **29% F1 improvement** over DeepMatcher (Mudgal 2018) on benchmark datasets
- Matches previous SOTA using at most **half the labeled data**
- Effective across structured, textual, and dirty EM settings
- RoBERTa generally outperforms BERT and DistilBERT

---

## Limitations

- Still requires labeled training pairs, just fewer of them
- Fine-tuning cost grows with model size (RoBERTa-large is substantially slower)
- Only addresses the **matching** step — canonicalization is out of scope
- Benchmark datasets (WDC, Magellan) are limited in language diversity and place-data coverage

---

## Relevance to this paper

Ditto is the second of the two "modern deep learning approaches" cited alongside DeepMatcher. It represents the then-state-of-the-art (pre-LLM) in fine-tuned transformer EM. Citing both Mudgal and Li together establishes the trajectory: DL → pre-trained transformers → zero-shot LLMs. In both cases the focus is matching, not canonicalization.

Note: the paper is published as a VLDB journal article (PVLDB) but formatted like a conference paper. The bib entry correctly uses `journal={Proceedings of the VLDB Endowment}` rather than `booktitle`.
