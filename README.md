# places-truth-reconciliation

> Building a reliable “golden record” for real-world places by resolving conflicting attributes across multiple data sources.

## Overview

Real-world places often appear in multiple datasets with **inconsistent, outdated, or conflicting information**.  
This project tackles the problem of **attribute-level conflation**: given multiple representations of the *same place*, how do we decide which attributes (phone, website, email, etc.) are the most accurate?

Our goal is to produce a **high-quality golden dataset** and evaluate different strategies—**rule-based logic vs. machine learning**—for selecting the best attributes.

This project is developed as part of coursework at the University of California, Santa Cruz, in partnership with the Overture Maps Foundation, using data from the Overture Maps places theme. It explores attribute-level truth reconciliation in large-scale, multi-source places data and reflects real-world constraints present in Overture Places datasets.

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

---

## Project Goals

- Create a **manually labeled golden dataset** from pre-matched place pairs
- Design a **rule-based attribute selection algorithm**
- Train and evaluate an **ML-based alternative**
- Compare approaches using quantitative metrics
- Analyze tradeoffs, limitations, and real-world applicability

---

## Attributes Considered

This project focuses on attributes that are commonly incomplete, conflicting, or stale in real-world places data:

- Phone number
- Website
- Email
- Address (limited evaluation)
- Category (exploratory)

Each attribute is evaluated **independently at the attribute level**, rather than assuming a single source is globally correct for a place.

---

## Methodology

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
└── README.md
└── LICENSE
└── .gitignore
