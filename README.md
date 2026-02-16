# places-truth-reconciliation

> Building a reliable “golden record” for real-world places by resolving conflicting attribute candidates produced by
> multiple aggregation strategies over multi-source data.

## Overview

Real-world places often appear in multiple datasets with **inconsistent, outdated, or conflicting information**.  
This project tackles the problem of **attribute-level conflation**: given multiple representations of the *same place*,
how do we decide which attributes (phone, website, email, etc.) are the most accurate?

Our goal is to produce a **high-quality golden dataset** and evaluate different strategies—**rule-based logic vs.
machine learning**—for selecting the best attributes.

This project is developed as part of coursework at the University of California, Santa Cruz, in partnership with the
Overture Maps Foundation, and is motivated by the structure and constraints of the Overture Maps Places dataset.

---

## Understanding the Dataset

The input dataset consists of pre-matched place records, where each row represents a single real-world place with **two
competing aggregated representations** of its attributes.

For each reconcilable attribute (e.g., phone number, website, address), the dataset provides:

- a baseline candidate (`base_*`)
- an alternative candidate (`*`)

Each candidate value is the **result of upstream aggregation across multiple source datasets** (e.g., Meta, Microsoft),
rather than a single raw provider value.

This structure intentionally models **disagreement between aggregation strategies**, not disagreement between individual
sources. The project therefore focuses on *decision-making under uncertainty* rather than raw source ingestion or entity
resolution.

These competing candidates can be thought of as outputs from two different aggregation or selection pipelines applied
over the same underlying multi-source inputs.

---

## Key Observations from Data Exploration

Exploratory analysis over the aggregated place sample reveals several properties that directly shape reconciliation
strategy design:

- **High disagreement rates across user-facing attributes**
    - Addresses, categories, phones, and websites exhibit disagreement rates on the order of 60-85% between baseline and
      alternative aggregated candidates, making them the highest-leverage attributes for reconciliation.

- **Disagreement is primarily semantic, not due to missing data**
    - For these high-impact attributes, the majority of conflicts occur when *both* aggregation strategies provide
      values that differ, rather than cases where one side is missing data. This indicates that reconciliation is
      largely a semantic disagreement problem rather than a coverage problem.

- **Confidence scores are weakly aligned with agreement.**
    - In many cases, conflicting candidates have comparable or higher average confidence than matching candidates. This
      suggests that confidence reflects internal aggregation certainty rather than cross-strategy agreement, and cannot
      be safely used as a tie-breaker on its own.

- **Truly high-risk conflicts are rare and isolatable.**
    - Rows where aggregation strategies disagree *and* both report low confidence occur infrequently. These cases
      represent the most dangerous failure modes for automation and can be explicitly identifies and routed for
      abstention or human review.

- **Metadata fields are signals, not reconciliation targets.**
    - Fields such as `sources` and `confidence` differ by construction and are treated as inputs to decision-making
      rather than attributes to be reconciled.

Together, these observations motivate:

- treating abstention as a first-class outcome,
    - Abstention is treated as a correctness-preserving outcome rather than a failure mode, preventing silent corruption
      when no defensible automated decision exists.
- avoiding naive confidence-based arbitration
- and prioritizing interpretable, rule-based decision logic for high-impact attributes.

These observations are supported by reproducible analysis artifacts in `analysis/general/`, including:

- `attribute_conflict_summary.csv` - attribute-level coverage, conflict, and abstention pressure
- `attribute_conflict_breakdown.csv` - decomposition of conflicts into missing-data vs true disagreement
- `attribute_confidence_behavior.csv` - comparison of confidence scores in conflict vs agreement cases
- `high_risk_*_conflicts.csv` - row-level cases where automated resolution is unsafe.

Based on these findings, the project focuses on four high-leverage attributes: **addresses, categories, phones, and
websites**.

### Phone Attribute Audit

Before designing reconciliation logic for phone numbers, we separate three concerns:

1. Missingness behavior
2. Structural formatting signals
3. Digit-length validity
4. Normalization impact on apparent conflicts

These are analyzed independently to avoid conflating formatting noise with semantic disagreement.

#### Phone Missingness Summary

File: `analysis/phones/phone_missingness_summary.csv`

This table measures how often phone values are actually absent versus encoded as string-wrapped null markers.

| Column                 | Meaning                                             | Base Count | Alt Count |
|------------------------|-----------------------------------------------------|------------|-----------|
| `total_rows`           | Total candidate rows evaluated per source           | 2000       | 2000      | 
| `sql_null`             | True SQL NULL values                                | 4          | 109       |
| `bracket_null`         | Exact string `[null]`                               | 288        | 0         |
| `bracket_empty_string` | Exact string `[""]`                                 | 8          | 10        |
| `bracket_null_caps`    | Exact string `["NULL"]`                             | 1          | 0         |
| `bracket_null_lower`   | Exact string `["null"]`                             | 0          | 0         |
| `contains_null_text`   | Any non-null string containing the substring `null` | 289        | 0         |
 
**Interpretation**

- Missingness is not limited to SQL NULL.
- These must be explicitly handled, or they will be misclassified as disagreement.

#### Phone Structural Summary

File: `analysis/phones/phone_structure_summary.csv`

This table evaluates formatting behavior **only for usable values**  
(defined as non-null strings containing at least one digit).

| Column                  | Meaning                            | Base Count | Alt Count |
|-------------------------|------------------------------------|------------|-----------|
| `usable_rows`           | Rows containing at least one digit | 1699       | 1881      |
| `has_plus_count`        | Contains `+` country prefix        | 13         | 1283      |
| `has_parentheses_count` | Contains parentheses               | 267        | 0         |
| `has_hyphen_count`      | Contains hyphen separators         | 329        | 0         |
| `pure_numeric_count`    | String consists only of digits     | 978        | 598       |
| `too_short_count`       | Digit length < 7                   | 0          | 0         |
| `too_long_count`        | Digit length > 15                  | 0          | 0         |

**Interpretation**

- Structural validity is generally high.
- Formatting conventions differ between aggregation strategies.
- Pure string comparison overestimates disagreement due to formatting variation.
- Confidence scores do not guarantee structural correctness.

#### Digit Length Distribution (Usable Values Only)

File: `analysis/phones/phone_digit_length_distribution.csv`

This table buckets usable phone numbers by digit length.

| Bucket  | Meaning                 | Base Count | Alt Count |
|---------|-------------------------|------------|-----------|
| `<7`    | Likely malformed        | 0          | 0         |
| `7-9`   | Possibly local formats  | 90         | 28        |
| `10`    | Standard US format      | 1297       | 528       |
| `11`    | Country code + US       | 215        | 936       |
| `12-15` | International formats   | 97         | 389       |
| `>15`   | Implausible / malformed | 0          | 0         |

**Interpretation**

- The majority of usable numbers fall within plausible bounds.
- No evidence of systemic extreme-length corruption.
- Digit normalization is required before reconciliation.

#### Phone Normalization Impact

File: `analysis/phones/phone_normalization_impact_staged.csv`

This analysis measures how apparent phone conflict drops as progressively stronger normalization rules are applied. Each stage is monotonic.

| Stage | Rule                            | Conflict Count | Conflict Rate | Improvement vs Prior |
|-------|---------------------------------|----------------|---------------|----------------------|
| S0    | Null normalization (preamble)   | —              | —             | —                    |
| S1    | Raw string compare              | 1330           | 79.17%        | —                    |
| S2    | Strip non-digits; exact match   | 1261           | 75.06%        | 5.19%                |
| S3    | US: +1 leading digit vs 10-digit| 819            | 48.75%        | 35.05%               |
| S4    | Generic 1-digit CC drop         | 765            | 45.54%        | 6.59%                |
| S5    | Trunk 0 vs 2-digit CC           | 554            | 32.98%        | 27.58%               |
| S6    | Trunk 0 vs 3-digit CC           | 478            | 28.45%        | 13.72%               |
| S7    | 2-digit CC vs national (no trunk gating) | 425   | 25.30%        | 11.09%               |
| S8    | 3-digit CC vs national (no trunk gating) | 417   | 24.82%        | 1.88%                |
| S9    | CC2+0+national vs CC2+national  | 402            | 23.93%        | 3.60%                |

Percentages are based on 1,680 usable (normalizable) rows (rows where both sides simultaneously have at least one digit). Of the remaining 320 rows: 100 have no phone on either side, and 220 have a phone on only one side (201 alt-only, 19 base-only). The one-sided cases are not automatically resolvable — absence may reflect a genuine removal rather than a coverage gap — and are handled separately during reconciliation.

Remaining conflicts after all stages are exported for manual review in
`analysis/phones/phone_remaining_conflicts.csv` with a `conflict_type` column: `both_present` (402 rows - genuinely different numbers after all normalization), `alt_only` (201 rows - alt has data, base missing), and `base_only` (19 rows - base has data, alt missing). 

**Interpretation**

- **Raw string comparison overstates phone conflict by approximately 3x.** After applying
  region-agnostic normalization rules, apparent conflict drops from 79% to 24%.
- **The largest single improvement (S3, ~35%) comes from US +1 prefix normalization**, reflecting
  the dataset's heavy US representation and a systematic formatting difference between the two
  aggregation strategies (E.164 vs bare national number).
- **International trunk-prefix normalization (S5–S6) accounts for ~37% combined reduction**,
  addressing the common pattern where one source stores a country code prefix while the other
  stores a local trunk-dialed number.
- **The remaining ~24% (402 pairs) represent genuinely different phone numbers.** These are true
  semantic conflicts that require reconciliation logic—either rule-based scoring, confidence
  arbitration, or abstention.
- **Normalization is a prerequisite to reconciliation, not a substitute.** Without this step,
  reconciliation logic would waste capacity on formatting artifacts and produce misleading
  accuracy metrics.

This staged approach serves as a template for normalization analysis on other attributes (websites, addresses)
where similar encoding differences between aggregation strategies may inflate apparent conflict.

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
This project explicitly handles ambiguity by prioritizing correctness, auditability, and the ability to abstain when
confidence is low.
In production systems, incorrect or unstable decisions can introduce churn across releases, making conservative
decision-making and abstention first-class requirements.

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

Other attributes (e.g., names, social links) are explored opportunistically but are not part of the core evaluation due
to subjectivity or lower impact.

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

Each attribute candidate is represented as a feature vector and used to train a classifier or ranking model that
predicts attribute correctness.

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

Evaluation includes cases where the system **intentionally abstains** from selecting an attribute due to insufficient
confidence.

---

## Production Considerations

In real-world systems, truth reconciliation must balance correctness, latency, explainability, and the ability to
incorporate human review.

This project prioritizes **interpretable decision logic and measurable confidence** over raw accuracy.  
Where possible, decisions are designed to remain stable across successive data releases, changing only when there is
strong evidence of a real-world update rather than transient upstream noise.
