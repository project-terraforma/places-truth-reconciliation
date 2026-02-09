# places-truth-reconciliation

> Building a reliable “golden record” for real-world places by resolving conflicting attribute candidates produced by multiple aggregation strategies over multi-source data.

## Overview

Real-world places often appear in multiple datasets with **inconsistent, outdated, or conflicting information**.  
This project tackles the problem of **attribute-level conflation**: given multiple representations of the *same place*, how do we decide which attributes (phone, website, email, etc.) are the most accurate?

Our goal is to produce a **high-quality golden dataset** and evaluate different strategies—**rule-based logic vs. machine learning**—for selecting the best attributes.

This project is developed as part of coursework at the University of California, Santa Cruz, in partnership with the Overture Maps Foundation, and is motivated by the structure and constraints of the Overture Maps Places dataset.

---

## Understanding the Dataset

The input dataset consists of pre-matched place records, where each row represents a single real-world place with **two competing aggregated representations** of its attributes.

For each reconcilable attribute (e.g., phone number, website, address), the dataset provides:
- a baseline candidate (`base_*`)
- an alternative candidate (`*`)

Each candidate value is the **result of upstream aggregation across multiple source datasets** (e.g., Meta, Microsoft), rather than a single raw provider value.

This structure intentionally models **disagreement between aggregation strategies**, not disagreement between individual sources. The project therefore focuses on *decision-making under uncertainty* rather than raw source ingestion or entity resolution.

These competing candidates can be thought of as outputs from two different aggregation or selection pipelines applied over the same underlying multi-source inputs.

---

## Key Observations from Data Exploration 

Exploratory analysis over the aggregated place sample reveals several properties that directly shape reconciliation strategy design:
- **High disagreement rates across user-facing attributes**
  Addresses, categories, phones, and websites exhibit disagreement rates on the order of 60-85% between baseline and alternative aggregated candidates, making them the highest-leverage attributes for reconciliation.

- **Disagreement is primarily semantic, not due to missing data.**
  For these high-impact attributes, the majority of conflicts occur when *both* aggregation strategies provide values that differ, rather than cases where one side is missing data. This indicates that reconciliation is largely a semantic disagreement problem rather than a coverage problem.

- **Confidence scores are weakly aligned with agreement.**
  In many cases, conflicting candidates have comparable or higher average confidence than matching candidates. This suggests that confidence reflects internal aggregation certainty rather than cross-strategy agreement, and cannot be safely used as a tie-breaker on its own.

- **Truly high-risk conflicts are rare and isolatable.**
  Rows where aggregation strategies disagree *and* both report low confidence occur infrequently. These cases represent the most dangerous failure modes for automation and can be explicitly identifies and routed for abstention or human review.

- **Metadata fields are signals, not reconciliation targets.**
  Fields such as `sources` and `confidence` differ by construction and are treated as inputs to decision-making rather than attributes to be reconciled.

Together, these observations motivate:
- treating abstention as a first-class outcome,
- avoiding naive confidence-based arbitration
- and prioritizing interpretable, rule-based decision logic for high-impact attributes.

Abstention is treated as a correctness-preserving outcome rather than a failure mode, preventing silent corruption when no defensible automated decision exists.

These observations are supported by reproducible analysis artifacts in `analysis/`, including:

- `attribute_conflict_summary.csv` - attribute-level coverage, conflict, and abstention pressure
- `attribute_conflict_breakdown.csv` - decomposition of conflicts into missing-data vs true disagreement
- `attribute_confidence_behavior.csv` - comparison of confidence scores in conflict vs agreement cases
- `high_risk_*_conflicts.csv` - row-level cases where automated resolution is unsafe.

Based on these findings, the project focuses on four high-leverage attributes: **addresses, categories, phones, and websites**.

---

## Problem Statement

When multiple data sources describe the same place, they frequently disagree:

- Different phone numbers
- Outdated or broken websites
- Inconsistent emails
- Partial or malformed data

Naive approaches like “most recent” or “most common” often fail.  
This project explores **how to programmatically determine the cleanest, most reliable data**.

---

## Why This Is Hard

Many attributes have no objectively correct answer.  
Sources may all be wrong, partially correct, or correct at different times.  
This project explicitly handles ambiguity by prioritizing correctness, auditability, and the ability to abstain when confidence is low.
In production systems, incorrect or unstable decisions can introduce churn across releases, making conservative decision-making and abstention first-class requirements.

---

## Project Goals

- Create a **manually labeled golden dataset** from pre-matched place pairs
- Design a **rule-based attribute selection algorithm**
- Train and evaluate an **ML-based alternative**
- Compare approaches using quantitative metrics
- Analyze tradeoffs, limitations, and real-world applicability

---

## Attributes Considered

This project focuses on attributes that are both highly prevalent and highly contested in the dataset:

- Address
- Category
- Phone number
- Website

Other attributes (e.g., names, social links) are explored opportunistically but are not part of the core evaluation due to subjectivity or lower impact.

---

## Approach

### 1. Golden Dataset Creation

A subset of pre-matched place records is manually reviewed to determine the most reliable attribute values.  
These labels form a **ground-truth dataset** used for evaluation and supervised learning.

Ambiguous cases are explicitly marked rather than forced into a binary decision.

### 2. Rule-Based Baseline

A deterministic scoring system evaluates candidate attributes using signals such as:

- Format validity (e.g., phone or email structure)
- Source reliability
- Recency
- Consensus across sources
- Domain consistency (e.g., email domain matches website)

The highest-scoring attribute is selected, with support for abstention when confidence is low.

### 3. Machine Learning Approach

Each attribute candidate is represented as a feature vector and used to train a classifier or ranking model that predicts attribute correctness.

The ML approach is evaluated against the rule-based baseline to determine:
- Where ML adds value
- Where it overfits or degrades interpretability
- Whether hybrid approaches are justified

### 4. Evaluation

Evaluation is performed at the **attribute level**, not just the place level, using:

- Attribute accuracy
- Precision / recall
- Coverage (ability to make a confident selection)
- Comparison between rule-based and ML approaches

Evaluation includes cases where the system **intentionally abstains** from selecting an attribute due to insufficient confidence.

---

## Production Considerations

In real-world systems, truth reconciliation must balance correctness, latency, explainability, and the ability to incorporate human review.

This project prioritizes **interpretable decision logic and measurable confidence** over raw accuracy.  
Where possible, decisions are designed to remain stable across successive data releases, changing only when there is strong evidence of a real-world update rather than transient upstream noise.

---

## (Proposed) Repository Structure
```text
places-attribute-conflation/
├── data/
│   ├── raw/                # Original matched datasets
│   ├── labeled_golden/     # Manually labeled ground truth
│   └── processed/          # Feature-engineered data
├── rules/
│   └── rule_engine.py      # Rule-based selection logic
├── models/
│   └── train.py            # ML training and inference
├── evaluation/
│   └── metrics.py          # Evaluation scripts
├── notebooks/
│   └── analysis.ipynb      # Exploratory analysis
└── .gitignore
└── LICENSE
└── README.md
