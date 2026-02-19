# places-truth-reconciliation

> Building a reliable “golden record” for real-world places by resolving conflicting attribute candidates produced by
> multiple aggregation strategies over multi-source data.

---

## Understanding the Dataset

The Overture Maps Places dataset consists of pre-matched place records, where each row represents a single real-world place with two
candidate representations of its attributes.

For each reconcilable attribute (e.g., phone number, website, address), the dataset provides:

- a baseline candidate (`base_*`)
- an alternative candidate (`*`)

---

## Key Observations from Data Exploration

Exploratory analysis over the 2,000-row place sample reveals several properties that directly shape reconciliation
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
      suggests confidence reflects a candidate's internal quality signal rather than its likelihood of being correct
      relative to the other side, and cannot be safely used as a tie-breaker on its own.

- **Truly high-risk conflicts are rare and isolatable.**
    - Rows where aggregation strategies disagree *and* both report low confidence occur infrequently. These cases
      represent the most dangerous failure modes for automation and can be explicitly identifies and routed for
      abstention or human review.

- **Metadata fields are signals, not reconciliation targets.**
    - Fields such as `sources` and `confidence` differ by construction and are treated as inputs to decision-making
      rather than attributes to be reconciled.

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
 
**Interpretation**: Missingness is not limited to SQL NULL. These variants must be explicitly handled or they will be
misclassified as disagreement.

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

**Interpretation**: Structural validity is generally high, but the two sides use systematically different formatting
conventions. Pure string comparison overestimates disagreement due to this variation.

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

**Interpretation**: The majority of usable numbers fall within plausible bounds. No evidence of systemic
extreme-length corruption. Digit normalization is required before reconciliation.

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
| S7    | 2-digit CC vs national (no trunk) | 425          | 25.30%        | 11.09%               |
| S8    | 3-digit CC vs national (no trunk) | 417          | 24.82%        | 1.88%                |
| S9    | CC2+0+national vs CC2+national  | 402            | 23.93%        | 3.60%                |

Percentages are based on 1,680 usable rows (both sides have at least one digit). Of the remaining 320 rows: 100 have
no phone on either side, and 220 have a phone on only one side (201 alt-only, 19 base-only). 

Remaining conflicts after all stages are exported for manual review in
`analysis/phones/phone_remaining_conflicts.csv` with a `conflict_type` column: `both_present` (402 rows), `alt_only` (201 rows), and `base_only` (19 rows). 

**Interpretation**

- **Raw string comparison overstates phone conflict by approximately 3x.** After applying
  region-agnostic normalization rules, apparent conflict drops from 79% to 24%.
- **The largest single improvement (S3, ~35%) comes from US +1 prefix normalization**, reflecting
  the dataset's heavy US representation and a systematic formatting difference between the two
  sides (E.164 vs bare national number).
- **International trunk-prefix normalization (S5–S6) accounts for ~37% combined reduction**,
  addressing the common pattern where one source stores a country code prefix while the other
  stores a local trunk-dialed number.
- **The remaining ~24% (402 pairs) represent genuinely different phone numbers.** These are true
  semantic conflicts requiring reconciliation logic

This staged approach serves as a template for normalization analysis on other attributes (websites, addresses)
where similar encoding differences between aggregation strategies may inflate apparent conflict.

---

## Project Goals

- Create a **manually labeled golden dataset** from pre-matched place pairs
- Design a **rule-based attribute selection algorithm**
- Train and evaluate an **ML-based alternative**
- Compare approaches using quantitative metrics
- Analyze tradeoffs, limitations, and real-world applicability

---

## Approach

### 1. Golden Dataset Creation

A subset of pre-matched place records is manually reviewed to determine the most reliable attribute values.  
These labels form a **ground-truth dataset** used for evaluation and supervised learning. Ambiguous cases
are explicitly marked rather than forced into a binary decision.

### 2. Rule-Based Baseline

A deterministic scoring system evaluates candidate attributes using signals such as format validity, source
reliability, recency, consensus across sources, and domain consistency (e.g., email domain matches website). The
highest-scoring attribute is selected, with support for abstention when confidence is low.

One candidate signal is **provider identity** — the `sources` field on each side identifies which upstream dataset
(e.g., Microsoft, FourSquare, Meta) contributed the record. If certain providers systematically produce more reliable
values for specific attributes, provider identity becomes a meaningful feature for the scorer. This hypothesis is not
assumed upfront; it is tested during feature engineering by checking whether provider identity correlates with
ground-truth labels in the golden dataset. Attribute CSVs pulled for analysis and labeling should include the
`sources` and `base_sources` fields so this signal is available when needed.

### 3. Machine Learning Approach

Each attribute candidate is represented as a feature vector and used to train a classifier or ranking model that
predicts attribute correctness. The ML approach is evaluated against the rule-based baseline to determine where ML
adds value, where it overfits or degrades interpretability, and whether hybrid approaches are justified.

### 4. Evaluation

Evaluation is performed at the attribute level, not just the place level, using attribute accuracy, precision/recall,
and coverage (the system's ability to make a confident selection). Evaluation explicitly includes cases where the
system intentionally abstains due to insufficient confidence.

---
