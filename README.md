# places-truth-reconciliation

> Building a reliable "golden record" for real-world places by selecting the best attribute values from two competing
> candidate records per place.

---

## Understanding the Dataset

The source file is `data/raw/project_a_samples.parquet`, described in `data/raw/readme_project_a_samples.txt`.

Each row represents a single real-world place with two candidate representations of its attributes. One candidate uses
the prefix `base_`; the other has no prefix (referred to here as `alt`). For each reconcilable attribute — phone,
website, address, category, name, social links, brand, email — the dataset provides a `base_*` value and an `alt` value
that may agree or disagree. The goal is to select the better value for each attribute, or abstain when neither can be
trusted.

Not all columns are reconciliation targets. `confidence` and `sources` are metadata fields: inputs to decision-making
rather than attributes to be selected. `confidence` is defined by the Overture schema as certainty that the place exists
— not that any given attribute is correct. `sources` identifies which upstream provider contributed each record, and is
a candidate feature for scoring but not a target. Both sides always have these fields.

### Column Coverage

Script: `scripts/01_dataset_overview.py`  
Output: `analysis/general/dataset_overview.csv`

| Column     | Alt Coverage | Base Coverage | Notes                                           |
|------------|--------------|---------------|-------------------------------------------------|
| id         | 100%         | 100%          | Row identifiers                                 |
| confidence | 100%         | 100%          | Metadata — place existence certainty            |
| sources    | 100%         | 100%          | Metadata — upstream provider identity           |
| names      | 100%         | 100%          |                                                 |
| addresses  | 100%         | 100%          |                                                 |
| categories | 99.2%        | 99.4%         |                                                 |
| phones     | 94.1%        | 85.0%         | Base missingness is partly string-encoded nulls |
| websites   | 83.3%        | 74.6%         |                                                 |
| socials    | 69.6%        | 50.9%         |                                                 |
| brand      | 35.2%        | 97.7%         | Coverage nearly inverted between sides          |
| emails     | 0.0%         | 10.95%        | Alt has no email data                           |

Two structural asymmetries stand out. Brand coverage is inverted: base has it for 98% of rows while alt has it for only
35%. This reflects a difference in what each provider tracks, not missingness in the usual sense. Emails go the
other direction entirely: alt has no email data while base supplies it for 11% of rows. Both are genuine data
characteristics that affect how reconciliation can work for those attributes.

---

## Exploratory Analysis

### Conflict Rates Across All Attributes

Script: `scripts/02_attribute_coverage_and_conflicts.py`  
Outputs: `analysis/general/attribute_conflict_summary.csv`, `analysis/general/attribute_conflict_breakdown.csv`

The table below shows conflict rates for every attribute in the dataset. A conflict is any row where both sides have a
value and those values disagree.

| Attribute  | Alt Coverage | Base Coverage | Conflict Count | Conflict Rate |
|------------|--------------|---------------|----------------|---------------|
| sources    | 100%         | 100%          | 2000           | 100%          |
| addresses  | 100%         | 100%          | 1722           | 86%           |
| categories | 99%          | 99%           | 1608           | 80%           |
| confidence | 100%         | 100%          | 1558           | 78%           |
| phones     | 95%          | 100%          | 1536           | 77%           |
| names      | 100%         | 100%          | 1375           | 69%           |
| websites   | 86%          | 100%          | 1292           | 65%           |
| socials    | 70%          | 51%           | 858            | 43%           |
| brand      | 35%          | 98%           | 389            | 19%           |
| emails     | 0%           | 50%           | 0              | 0%            |

`sources` conflicts at 100% by construction — the two sides always cite different providers. This is expected and not
meaningful as a conflict. `confidence` conflicting at 78% reflects the same: the two aggregation pipelines produce
different existence scores. Neither is a reconciliation target.

Among the reconcilable attributes, disagreement is high across the board. Addresses lead at 86%, but even brand — the
attribute with the most skewed coverage — still conflicts in 19% of rows. This is a dataset where the two sides
routinely
disagree, not one where one side is a reliable fallback.

**Disagreement is primarily semantic, not a coverage problem.** For addresses and categories, both sides have a value
in virtually every conflict row — they simply disagree on what that value is.

### Source Providers

Script: `scripts/03_source_providers.py`  
Outputs: `analysis/general/source_provider.csv`, `analysis/general/source_provider_pairings.csv`,
`analysis/general/source_property_values.csv`, `analysis/general/source_attr_contributors_per_row.csv`

The `sources` and `base_sources` fields identify which upstream provider contributed each record. Provider identity is a
candidate feature for reconciliation scoring: if certain providers systematically produce more reliable values for
specific attributes, that becomes a useful signal. Validating that hypothesis requires ground-truth labels and is
deferred to the feature engineering phase.

`source_provider.csv` shows which provider contributed attribute data per side:

| Side | Dataset    | Row Count | Row % |
|------|------------|-----------|-------|
| alt  | meta       | 1392      | 69.6% |
| alt  | Microsoft  | 466       | 23.3% |
| alt  | msft       | 142       | 7.1%  |
| base | FourSquare | 1000      | 50.0% |
| base | Microsoft  | 950       | 47.5% |
| base | msft       | 33        | 1.65% |
| base | meta       | 17        | 0.85% |

Alt attribute data comes almost entirely from meta. Base is split evenly between FourSquare and Microsoft.
`source_provider_pairings.csv` shows the combinations:

| Base Provider | Alt Provider | Row Count | Row % |
|---------------|--------------|-----------|-------|
| FourSquare    | meta         | 843       | 42.2% |
| Microsoft     | meta         | 525       | 26.3% |
| Microsoft     | Microsoft    | 309       | 15.5% |
| FourSquare    | Microsoft    | 157       | 7.9%  |
| Microsoft     | msft         | 116       | 5.8%  |

---

## Phone Attribute Analysis

Before designing reconciliation logic for phones, we separate four concerns and analyze each independently to avoid
conflating formatting noise with semantic disagreement.

### 1. Missingness

Script: `scripts/phones/04_phone_missingness.py`  
Output: `analysis/phones/phone_missingness_summary.csv`

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

**Interpretation**: Missingness is not limited to SQL NULL. The base side uses bracket-wrapped null markers heavily
(289 rows); the alt side uses SQL NULL (109 rows). Any comparison that treats these as real values will overcount
conflict. All null variants are unified to true NULL before any further analysis. These variants must be explicitly
handled or they will be misclassified as disagreement.

### 2. Structure and Formatting

Script: `scripts/phones/05_phone_structure.py`  
Outputs: `analysis/phones/phone_structure_summary.csv`, `analysis/phones/phone_digit_length_distribution.csv`

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

The two sides use systematically different formatting conventions. Alt uses E.164 format (`+` prefix) in 68% of rows.
Base uses local formatting (parentheses, hyphens, spaces) and almost never uses a `+` prefix. This means raw string
comparison will treat identical numbers as conflicts whenever they differ only in format.

**Interpretation**: Structural validity is generally high, but the two sides use systematically different formatting
conventions. Pure string comparison overestimates disagreement due to this variation.

This table buckets usable phone numbers by digit length.

| Bucket  | Meaning                 | Base Count | Alt Count |
|---------|-------------------------|------------|-----------|
| `<7`    | Likely malformed        | 0          | 0         |
| `7-9`   | Possibly local formats  | 90         | 28        |
| `10`    | Standard US format      | 1297       | 528       |
| `11`    | Country code + US       | 215        | 936       |
| `12-15` | International formats   | 97         | 389       |
| `>15`   | Implausible / malformed | 0          | 0         |

Digit length distribution shows that the vast majority of usable numbers fall in the 10–12 digit range with no evidence
of systemic corruption (no values below 7 or above 15 digits).

**Interpretation**: The majority of usable numbers fall within plausible bounds. No evidence of systemic
extreme-length corruption. Digit normalization is required before reconciliation.

#### 3. Normalization Impact

Script: `scripts/phones/06_phone_normalization.py`  
Outputs: `analysis/phones/phone_normalization_impact_staged.csv`, `analysis/phones/phone_remaining_conflicts.csv`

This is the core phone analysis. We apply progressively stronger normalization rules and measure how apparent conflict
drops at each stage.
Each stage is monotonic.

| Stage | Rule                              | Conflict Count | Conflict Rate | Improvement vs Prior |
|-------|-----------------------------------|----------------|---------------|----------------------|
| S0    | Null normalization (preamble)     | —              | —             | —                    |
| S1    | Raw string compare                | 1330           | 79.17%        | —                    |
| S2    | Strip non-digits; exact match     | 1261           | 75.06%        | 5.19%                |
| S3    | US: +1 leading digit vs 10-digit  | 819            | 48.75%        | 35.05%               |
| S4    | Generic 1-digit CC drop           | 765            | 45.54%        | 6.59%                |
| S5    | Trunk 0 vs 2-digit CC             | 554            | 32.98%        | 27.58%               |
| S6    | Trunk 0 vs 3-digit CC             | 478            | 28.45%        | 13.72%               |
| S7    | 2-digit CC vs national (no trunk) | 425            | 25.30%        | 11.09%               |
| S8    | 3-digit CC vs national (no trunk) | 417            | 24.82%        | 1.88%                |
| S9    | CC2+0+national vs CC2+national    | 402            | 23.93%        | 3.60%                |

Percentages are based on 1,680 usable rows (both sides have at least one digit). Of the remaining 320 rows: 100 have
no phone on either side, and 220 have a phone on only one side (201 alt-only, 19 base-only).

Remaining conflicts after all stages are exported for manual review in
`analysis/phones/phone_remaining_conflicts.csv` with a `conflict_type` column: `both_present` (402 rows), `alt_only` (
201 rows), and `base_only` (19 rows).

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

#### 4. Confidence Analysis

Script: `scripts/phones/07_phone_confidence.py`  
Outputs: `analysis/phones/phone_true_conflict_confidence_summary.csv`,
`analysis/phones/phone_true_conflict_confidence_detail.csv`, `analysis/phones/phone_confidence_distribution.csv`,
`analysis/phones/phone_confidence_distribution_bucketed.csv`

Per the [Overture schema](https://docs.overturemaps.org/schema/reference/places/place/),
`confidence` is defined as "the confidence of the existence of the place" - a score between
0 and 1 reflecting how sure the system is that the place itself is real and currently
operating. It is not a measure of individual attribute quality, completeness, or
correctness. This distinction is critical: a place can have high existence confidence and
still have a missing or incorrect phone number.

After normalization, we test whether confidence scores can resolve the remaining 622 phone conflicts (402 true
conflicts + 220 one-sided). They cannot.

**Base confidence is effectively binary.** Within the 402 true conflicts, `phone_confidence_distribution.csv` shows:

| Side | Confidence Value | Row Count | % of Class |
|------|------------------|-----------|------------|
| base | 1.0              | 234       | 58.2%      |
| base | 0.77             | 159       | 39.6%      |
| base | (all others)     | 9         | 2.2%       |

98% of base confidence scores in true conflicts are either exactly 1.0 or exactly 0.77. This is not a granular quality
measure — it is a two-state flag that cannot meaningfully rank one record against another.

Alt confidence has more spread (24 distinct values) but still clusters heavily at 0.77. `phone_confidence_distribution_bucketed.csv` shows:

|  Confidence Bucket | Row Count | % of Class |
|--------------------|-----------|------------|
| **1.00**           | **56**    | **13.9%**  |
| 0.99 – 0.98        | 66        | 16.4%      |
| 0.97 – 0.95        | 52        | 12.9%      |
| 0.94 – 0.92        | 10        | 2.5%       |
| 0.91 – 0.89        | 8         | 2.0%       |
| 0.88 – 0.86        | 4         | 1.0%       |
| 0.85 – 0.78        | 20        | 5.0%       |
| **0.77**           | **133**   | **33.1%**  |
| 0.76 – 0.60        | 11        | 2.7%       |
| 0.59 – 0.00        | 42        | 10.4%      |

**Base confidence is higher most of the time, regardless of correctness.** `phone_true_conflict_confidence_summary.csv` shows that in the 402 true conflicts:

| Side Higher | Count | % of Rows |
|-------------|-------|-----------|
| base        | 241   | 60.0%     |
| tied        | 89    | 22.1%     |
| alt         | 72    | 17.9%     |

Base scores higher in 60% of rows — but since base clusters at 1.0 by construction, this tells us nothing about which phone number is correct.

**Confidence gaps are too small to be useful.** The median confidence gap in true conflicts is 0.055. Most pairs have
nearly identical scores, making confidence useless as a tiebreaker.

**Higher confidence does not mean more data.** In the 201 alt-only rows where alt provides a phone and base has nothing,
`phone_true_conflict_confidence_summary.csv` shows:

| Conflict Class | Avg Alt Confidence | Avg Base Confidence | Base Higher |
|----------------|--------------------|---------------------|-------------|
| alt_only       | 0.753              | 0.995               | 97.5%       |

The side with no phone number is rated more confident in 97.5% of cases. This is consistent with the schema definition:
confidence measures place existence, not attribute completeness.

**Conclusion for phones**: confidence is not a viable reconciliation signal. Using it as a tiebreaker would
systematically favor the base side due to its clustering at 1.0, with no relationship to phone quality. True conflicts (
402 rows) should default to abstention — phone digits have no evaluable internal structure beyond format validity, so
neither a rule-based nor ML approach can determine correctness without external verification.

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
