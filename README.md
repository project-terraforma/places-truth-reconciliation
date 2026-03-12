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
| 0.99              | 29        | 7.2%       |
| 0.98              | 37        | 9.2%       |
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

**Confidence gaps are too small to be useful.** The median absolute confidence gap across the 402 true conflicts is 0.055, and 48% of rows have a gap of 0.05 or less:

| Confidence Gap | Row Count | % of True Conflicts |
|----------------|-----------|---------------------|
| ≤ 0.05         | 193       | 48.0%               |
| 0.06 – 0.10    | 23        | 5.7%                |
| 0.11 – 0.20    | 14        | 3.5%                |
| > 0.20         | 172       | 42.8%               |

Nearly half of all true conflicts have gaps so small they are effectively tied. The 42.8% with gaps above 0.20 might seem actionable, but since base clusters at 1.0 those large gaps mostly just reflect base's fixed anchor value, not a meaningful quality difference.

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

## Name Attribute Analysis

Before designing reconciliation logic for names, we separate three concerns and analyze each independently:
structural characteristics of raw name values, conflict classification using a two-tier labeling system, and
Unicode normalization correctness. Names have 100% coverage on both sides (no missingness analysis needed),
so the focus is entirely on characterizing disagreement.

### 1. Structure and Formatting

Script: `scripts/names/08_name_structure.py`  
Outputs: `analysis/names/name_structure_summary.csv`, `analysis/names/name_length_distribution.csv`,
`analysis/names/name_wordcount_distribution.csv`, `analysis/names/name_casing_summary.csv`

This table measures structural characteristics of name values per side, independent of whether they agree.

| Metric              | Alt    | Base   |
|---------------------|--------|--------|
| Total rows          | 2000   | 2000   |
| Avg length (chars)  | 20.4   | 21.0   |
| Median length       | 18.0   | 19.0   |
| Min / Max length    | 2 / 90 | 2 / 89 |
| Avg word count      | 3.01   | 3.09   |
| All-caps names      | 39 (1.95%) | 69 (3.45%) |
| All-lower names     | 18 (0.9%)  | 15 (0.75%) |
| Business suffix     | 68 (3.4%)  | 71 (3.55%) |
| SEO keywords        | 16 (0.8%)  | 15 (0.75%) |
| Excessive (>8 words)| 19 (0.95%) | 23 (1.15%) |

The two sides are structurally similar. Both cluster around 2–3 word names of 18–21 characters. Base has
slightly more all-caps names (3.5% vs 2.0%), which reflects formatting conventions in certain upstream
providers.

**Business suffixes** (3.4% alt, 3.6% base) detect legal entity markers appended to business names:
`LLC`, `Inc`, `Corp`, `GmbH`, `SRL`, `s.r.l.`, `Ltd`, etc. Examples: `Dana Stampi s.r.l.` vs
`Dana Stampi SRL`, `Aspen Grove - Kitchen & Bath Inc.` vs `Aspen Grove Kitchen & Bath Inc`. These
per-side counts measure how often each source includes legal suffixes, independent of whether the
other side agrees. When one side has a suffix and the other doesn't, it typically creates a subset
conflict (e.g. `Emerson Fence Inc` vs `Emerson Fence`).

**SEO keywords** (0.8% alt, 0.75% base) detect marketing/directory junk injected into name fields:
`hours`, `address`, `near me`, `official site`, `directions`, `reviews`, `menu`. Example:
`Harrah's Casino New Orleans: Hours, Address` vs `Harrah's`. These are rare but unambiguously noise —
the side with SEO keywords is never the preferred name.

**Excessive length** (>8 words; 0.95% alt, 1.15% base) flags names that may contain embedded
descriptions, addresses, or listing boilerplate. Examples include
`DANCENTER (39879) 6 Personen Ferienhaus in einem Ferienpark in Hanstholm` (vacation rental listing
template with unit ID) and `HWV Hanseatische Wirtschafts- und Vertriebsgesellschaft für Ärztebedarf
R. Blome GmbH` (full legal entity name). Excessive length is not inherently noise — long German company
names are legitimate — but it correlates with listing boilerplate that inflates apparent conflict.

Character length distribution (`name_length_distribution.csv`) confirms the bulk falls in the 11–35 character
range (71% alt, 69% base), with a thin tail beyond 50 characters:

| Bucket | Alt     | Base    |
|--------|---------|---------|
| 1–5    | 3.6%    | 3.75%   |
| 6–10   | 15.4%   | 15.95%  |
| 11–20  | 38.85%  | 36.0%   |
| 21–35  | 32.35%  | 32.9%   |
| 36–50  | 7.75%   | 8.85%   |
| 51–75  | 1.9%    | 2.25%   |
| >75    | 0.15%   | 0.3%    |

Word count distribution (`name_wordcount_distribution.csv`) shows that 1–3 word names dominate (69% alt,
68% base), with names beyond 5 words accounting for under 10%:

| Words | Alt     | Base    |
|-------|---------|---------|
| 1     | 19.15%  | 17.6%   |
| 2     | 25.05%  | 25.65%  |
| 3     | 25.2%   | 24.85%  |
| 4     | 13.55%  | 13.3%   |
| 5     | 8.1%    | 8.25%   |
| 6+    | 8.95%   | 10.35%  |

**Interpretation**: The two sides produce structurally similar name values. There is no systematic
length or complexity asymmetry that would favor one side over the other as a formatting signal.

### 2. Conflict Classification — Two-Tier Labeling

Script: `scripts/names/08_name_structure.py`  
Outputs: `analysis/names/name_agreement_breakdown.csv`, `analysis/names/name_all_agreements_labeled.csv`,
`analysis/names/name_tier1_summary.csv`, `analysis/names/name_subtag_summary.csv`,
`analysis/names/name_all_conflicts_labeled.csv`, `analysis/names/name_genuinely_different_inspect.csv`

The `names` and `base_names` fields are JSON objects containing a `primary` name and optionally
alternate or common names. This analysis focuses on the **primary name** only — the most important
field for reconciliation. The 2000 rows break down as follows
(`name_agreement_breakdown.csv` has 3 examples per bucket with full JSON):

| Bucket                          | Rows | % of Total | Meaning                                      |
|---------------------------------|------|------------|----------------------------------------------|
| `full_agreement`                | 625  | 31.3%      | Entire JSON matches — no conflict at all      |
| `primary_agrees_json_differs`   | 292  | 14.6%      | Primary names match; JSON envelope differs (empty fields) |
| `primary_conflict`              | 1083 | 54.2%      | Primary names disagree — this is what we classify below |

These buckets use **raw string comparison with no normalization**. A row lands in `primary_conflict`
if the extracted primary name strings differ at all — including pure casing differences like
`ROSSMANN` vs `Rossmann`. The Tier 1 classifier below determines which of the 1083 are real
semantic conflicts versus formatting noise.

The 292 `primary_agrees_json_differs` rows are entirely a JSON serialization difference — the base
side includes empty structural fields that the alt side omits. For example:

- alt: `{"primary":"Edward Jones"}`
- base: `{"primary":"Edward Jones","common":{},"rules":[]}`

All 292 rows follow this pattern. There is no actual name data difference in any of them.

`name_all_agreements_labeled.csv` contains every row from the first two buckets (917 rows) with
agreement type, both primary names, both full JSON objects, address, and confidence — the
counterpart to `name_all_conflicts_labeled.csv`. Together the two files account for all 2000 rows.

The 292 `primary_agrees_json_differs` rows require no reconciliation action — the name data is
identical, only the JSON envelope differs. The remaining 1083 primary-name conflicts are classified
using a two-tier system designed for reconciliation decision-making.

#### Tier 1: Relationship Type

Tier 1 labels are mutually exclusive and determine the reconciliation action.

| Tier 1 Label              | Meaning                                                         | Reconciliation Action          |
|---------------------------|-----------------------------------------------------------------|--------------------------------|
| `casing_only`             | Identical after lowercasing                                     | Auto-resolve; formatting pref  |
| `normalization_equivalent`| Same name after punctuation/spacing/diacritic/conjunction/spelling/script-form normalization | Auto-resolve; formatting pref  |
| `subset`                  | One name is meaningfully contained in the other (brand vs brand+branch, name vs name+gloss) | Policy decision: prefer core name vs full listing |
| `genuinely_different`     | Different names for the same place, or potential bad match       | Requires human review or abstention |

The distribution across 1083 conflict rows:

| Tier 1 Label              | Count | % of Conflicts |
|---------------------------|-------|----------------|
| `subset`                  | 600   | 55.4%          |
| `normalization_equivalent`| 238   | 22.0%          |
| `genuinely_different`     | 187   | 17.3%          |
| `casing_only`             | 58    | 5.4%           |

Over 82% of name conflicts (casing + normalization + subset) have a deterministic or policy-based
resolution path. Only 17.3% are genuinely different names requiring human review.

#### How Tier 1 Classification Works

Classification operates as a **decision tree**: each conflict row is checked against the Tier 1
labels in priority order, and the first label that matches is assigned. This is different from the
phone analysis, which applied a staged monotonic pipeline and measured conflict reduction at each
step. Here, each row gets exactly one label and stops. (The monotonic pipeline in Section 6
applies a similar staged approach to names and measures cumulative conflict reduction.)

The decision tree has four steps. Step 1 is a single check. Step 2 runs through 9 progressively
stronger normalizers — if *any* of them produce a match, the row is labeled and we stop. Steps 3
and 4 are single checks.

**Step 1 — Casing only.** If `lower(alt) == lower(base)`, the row is `casing_only` and we stop.
Example: `ROSSMANN` vs `Rossmann`.

**Step 2 — Normalization equivalent.** We apply progressively stronger normalizations to both names
and check whether any of them produce a match. Each normalizer builds on `norm_compare` (the
standard comparison form), which applies: fullwidth→ASCII conversion, Latin accent stripping,
lowercasing, punctuation/symbol removal, and whitespace collapsing. The normalizers are checked in
order from cheapest to most expensive — if any one matches, the row is `normalization_equivalent`
and we stop.

In the table below, the three-part arrow notation `A` → `normalized` ← `B` shows both inputs
normalizing to the same middle form. The two-part notation `A` ↔ `B` means the two match after
normalization without showing the intermediate form.

| # | Check                         | What it catches                                              | Example                                                        |
|---|-------------------------------|--------------------------------------------------------------|----------------------------------------------------------------|
| 1 | `norm_compare` match          | Case, accents, punctuation differences                       | `Origen's Bistrô` → `origens bistro` ← `origensbistro`        |
| 2 | Space-stripped match           | Compound split/join                                          | `Photo Color Lab` → `photocolorlab` ← `PhotoColorLab`         |
| 3 | Conjunction-normalized         | `&`/`and`/`et`/`und`/`y`/`e` unified                       | `Acqua e Sapone` → `acqua and sapone` ← `Acqua & Sapone`     |
| 4 | Conjunction + space-stripped   | Conjunction + compound boundary                              | `Crepes&Coffee` → `crepesandcoffee` ← `Crepes & Coffee`       |
| 5 | Spelling-normalized            | British/American variants                                    | `Defence Centre` → `defense center` ← `Defense Center`        |
| 6 | Word-reorder (sorted tokens)   | Same words in different order                                | `Colombo Cristoforo` → `colombo cristoforo` ← `Cristoforo Colombo` |
| 7 | Katakana→hiragana              | Japanese script-form variants (see note below)               | `コインランドリーハナコ` → `こいんらんどりーはなこ` ← `コインランドリーはなこ` |
| 8 | Katakana→hiragana + space-stripped | Script-form + Japanese compound boundary                 | Same as 7 but also collapses spacing differences               |
| 9 | Levenshtein typo (see note below) | 1–2 character substitutions/insertions                    | `คลีนิคบ้านหมอ` ↔ `คลีนิกบ้านหมอ` (Thai spelling variant)    |

**Stages 7–8: Katakana and hiragana.** Japanese has two phonetic scripts — katakana (カタカナ) and
hiragana (ひらがな) — that represent the same sounds with different characters. A business name
written in katakana and the same name written in hiragana are the same name, just in different
scripts. This is analogous to writing "HELLO" vs "hello" in English, except the character sets are
entirely different. `コインランドリーハナコ` (katakana) and `コインランドリーはなこ` (hiragana)
both read "Coin Laundry Hanako." The normalizer converts all katakana to hiragana before comparing.
Stage 8 additionally strips spaces to handle Japanese compound word boundaries (see Step 3 below).

**Stage 9: Levenshtein thresholds.** The typo detector uses edit distance ≤ 2 with a similarity
ratio ≥ 0.85 (computed as `1 − distance / max_length`), and only fires on strings of 5+ characters.
These thresholds are conservative: edit distance 2 catches single transpositions, a dropped letter,
or a substitution (like Thai `ค` vs `ก`), while the 0.85 similarity floor prevents short strings
from false-matching (a 1-character edit on a 5-character string is only 0.80 similarity and would be
rejected). The 5-character minimum avoids trivially matching short words. Typo detection is the last
check because it is the most expensive (quadratic in string length) and the least precise.

**Step 3 — Subset.** If one name is meaningfully contained inside the other, the row is `subset`.
This check runs on multiple normalized forms because word boundaries differ between sources and
scripts.

**Why multiple containment checks are needed — Japanese compound boundaries:** Japanese text is
typically written without spaces between words. Whether spaces appear depends on the source's
formatting conventions, not linguistic rules. So `ローソン` (Lawson, 3 characters) needs to be
found inside `ローソンいわき下好間店` (Lawson Iwaki-Shimokoma branch, 11 characters) — a pure
character-level substring check with no spaces. But another source might write the same branch as
`ローソン いわき下好間店` (with a space after the brand name). To handle both, subset detection
runs three containment checks:

1. Standard normalized forms — handles most Latin, Thai, and CJK subsets where spaces are consistent
2. Space-stripped forms — handles Japanese compound boundaries where one source uses spaces and the other does not
3. Hiragana-normalized + space-stripped forms — handles cases where one source writes in katakana and the other in hiragana, with different spacing

Example: `すき家` (Sukiya) vs `すき家 札幌北郷店` (Sukiya Sapporo Kitago branch) — the
shorter name is the brand, the longer name is the branch listing. This is the most common
pattern in Japanese and Thai data.

**Step 4 — Genuinely different.** If none of the above matched, the row is `genuinely_different`.
Example: `ก๋วยเตี๋ยวปลาในตำนาน` (Legendary fish noodles) vs `ก๋วยเตี๋ยวปลาสด` (Fresh fish
noodles) — different words, different businesses.

#### Why Two Tiers?

Tier 1 answers **"what do we do with this conflict?"** — it maps directly to a reconciliation
action. `casing_only` and `normalization_equivalent` are auto-resolvable. `subset` is a policy
decision. `genuinely_different` requires human review.

Tier 2 answers **"what kind of difference is it?"** — it is diagnostic. When presenting to
stakeholders, Tier 2 explains *why* conflicts exist in the data (punctuation conventions differ
between providers, Japanese listings include branch suffixes, etc.). Tier 2 subtags are also
candidates for feature engineering if an ML approach is pursued later.

#### Tier 2: Transformation Subtags

Tier 2 subtags are diagnostic — multiple can apply per row. They describe *what kind* of
transformation explains the difference, not the reconciliation action.

**For `normalization_equivalent` rows:**

| Subtag        | Meaning                                                          |
|---------------|------------------------------------------------------------------|
| `punctuation` | Dash/dot/apostrophe/quote/nakaguro (・) differences              |
| `spacing`     | Compound split/join (PhotoColorLab ↔ Photo Color Lab)            |
| `diacritic`   | Accent differences (Bistrô ↔ Bistro, Creatività ↔ Creativita)   |
| `conjunction` | &/and/et/und/y/e interchange                                     |
| `spelling`    | British/American variants (centre ↔ center)                      |
| `word_reorder`| Same tokens in different order                                   |
| `script_form` | Katakana ↔ hiragana (ハナコ ↔ はなこ), small kana variants       |
| `typo`        | Levenshtein distance ≤ 2 (only when no other subtag explains it) |

**For `subset` rows:**

| Subtag           | Meaning                                                        |
|------------------|----------------------------------------------------------------|
| `branch_suffix`  | Brand + store/location name (very common in JP/TH data)        |
| `parenthetical`  | Name + parenthetical reading/disambiguation                    |
| `biz_suffix`     | Legal suffix added/removed (LLC, GmbH, SRL, Inc, ...)         |
| `seo_junk`       | SEO keywords in the longer name (hours, directions, near me)   |
| `facility_suffix` | Bus stop, ATM, substation appended                            |
| `descriptor`     | Additional business description (catch-all)                    |

Subtag frequency from `name_subtag_summary.csv` (counts may exceed Tier 1 totals because rows can
carry multiple subtags):

**Normalization subtags** (238 rows; percentages reflect how many rows carry each subtag,
and can exceed 100% because a single row may carry multiple subtags):

| Subtag        | Count | % of Norm. Rows |
|---------------|-------|-----------------|
| `punctuation` | 85    | 35.7%           |
| `spacing`     | 76    | 31.9%           |
| `typo`        | 37    | 15.5%           |
| `word_reorder`| 26    | 10.9%           |
| `diacritic`   | 19    | 8.0%            |
| `conjunction` | 15    | 6.3%            |
| `script_form` | 1     | 0.4%            |
| `spelling`    | 1     | 0.4%            |

Punctuation and spacing dominate normalization conflicts. Typo at 37 rows reflects the long tail
of 1–2 character differences that no other normalizer catches (Thai spelling variants, small kana,
minor letter substitutions). Conjunction and diacritic differences are present but less common.
Script-form and British/American spelling variants are rare in this sample.

**Subset subtags** (600 rows):

| Subtag           | Count | % of Subset Rows |
|------------------|-------|------------------|
| `descriptor`     | 442   | 73.7%            |
| `biz_suffix`     | 52    | 8.7%             |
| `branch_suffix`  | 46    | 7.7%             |
| `parenthetical`  | 36    | 6.0%             |
| `facility_suffix`| 29    | 4.8%             |
| `seo_junk`       | 1     | 0.2%             |

The `descriptor` catch-all accounts for 74% of subsets, reflecting the wide variety of ways one
source adds context to a core name (branch numbers, department names, service lists, owner names).
`biz_suffix` (LLC, GmbH, etc.) and `branch_suffix` (Japanese/Thai store names) are the next most
common. `facility_suffix` catches appended bus stop (バス停) and ATM designations. SEO junk is
negligible in name data — note that some SEO-flagged words like "menu" or "best" can also be
legitimate parts of a business name (e.g., a restaurant called "Best Menu"). These false positives
are not a problem because the SEO flag is diagnostic only; actual SEO-stuffed names are caught
as subsets when the shorter side contains the core name without the keywords.

#### Output Files

`name_tier1_summary.csv` — Count and percentage of each Tier 1 label across all conflict rows.

`name_subtag_summary.csv` — Frequency of each Tier 2 subtag, grouped by its parent Tier 1 label.
Since subtags are semicolon-delimited and a row can carry multiple, counts here may exceed the Tier 1
row count (each subtag is counted independently).

`name_all_conflicts_labeled.csv` — All 1083 conflict rows with `tier1`, `tier2_subtags`, both name
values, length/word-count differentials, address/city/state/category context, confidence scores, and
`sources`/`base_sources` for provider identity analysis. Also includes diagnostic boolean flags
(`alt_has_biz_suffix`, `base_has_seo`, etc.) for downstream feature engineering. Sorted by tier1 →
subtags → length differential for systematic inspection.

`name_genuinely_different_inspect.csv` — The subset of conflict rows labeled `genuinely_different`.
This is the **golden dataset population** for name reconciliation: the rows where normalization
cannot resolve the conflict and human judgment is required.

### 3. Technical Notes — Multilingual Unicode Handling

Working with place names across multiple scripts (Latin, CJK, Thai, Korean, Cyrillic, Arabic)
introduces Unicode normalization challenges that are not obvious from Latin-only data. This section
documents three patterns encountered during development, as reference for anyone building text
normalization pipelines across scripts.

**Note 1: Punctuation stripping must be Unicode-category-aware.**

A common approach to stripping punctuation is `[^a-zA-Z0-9\s]`, which keeps only ASCII letters,
digits, and whitespace. This destroys every non-Latin character — CJK ideographs, Japanese kana,
Thai, Korean Hangul, Cyrillic, and Arabic are all silently removed. The correct approach is to
filter by Unicode character category: keep L (Letter), N (Number), and M (Mark) from all scripts,
strip only P (Punctuation) and S (Symbol).

**Note 2: Accent stripping must distinguish Latin diacritics from script-essential marks.**

Unicode represents accented Latin characters as a base letter plus a combining mark (e.g. `é` =
`e` + combining acute accent). Stripping all combining marks removes Latin accents as intended, but
also removes marks that are linguistically meaningful in other scripts. In Japanese, the dakuten
(゙) is a combining mark that voices consonants — stripping it turns `バ` (ba) into `ハ` (ha),
changing the character's pronunciation and meaning entirely. In Thai, tone marks (่ ้ ๊ ๋) are
combining marks that determine which of five tones a syllable carries — stripping them changes
word meaning (e.g., `ห้วย` "stream" loses its tone mark and becomes ambiguous). The fix is to
only strip combining marks in the Latin Combining Diacritical Marks block (U+0300..U+036F),
leaving Japanese, Thai, Korean, Arabic, and other script-specific marks intact.

**Note 3: Fullwidth spaces (U+3000) are visually identical to ASCII spaces.**

CJK text commonly uses the fullwidth ideographic space (U+3000) instead of the ASCII space
(U+0020). These render identically in most fonts but are different codepoints. NFKD normalization
converts U+3000 → U+0020, so after normalization both forms are identical. Any subtag detection
or diagnostic logic that operates on already-normalized forms will miss this difference entirely.
The fix is to also check raw forms with whitespace collapsing before checking normalized forms.

**Verification**: The test suite (`test_v2.py`) validates the normalization pipeline against 41
test cases covering all Tier 1 labels, CJK/Thai/Korean scripts, and the patterns described above.

### 4. Casing Patterns

Script: `scripts/names/08_name_structure.py`  
Output: `analysis/names/name_casing_summary.csv`

Among conflict rows, casing behavior breaks down as:

| Pattern                  | Count | % of Conflicts |
|--------------------------|-------|----------------|
| Both mixed/title case    | 976   | 90.12%         |
| Casing only (no other diff) | 58 | 5.36%         |
| Base all-caps, alt not   | 32    | 2.95%          |
| Alt all-caps, base not   | 6     | 0.55%          |
| Alt all-lower, base not  | 6     | 0.55%          |
| Base all-lower, alt not  | 5     | 0.46%          |

**Interpretation**: 90% of conflicts have mixed or title casing on both sides — casing alone rarely
explains disagreement. The 58 casing-only rows (5.4%) are trivially resolvable. Among the remaining
conflicts with asymmetric casing, base is more likely to be all-caps (2.95% vs 0.55%), consistent with
certain upstream providers storing names in uppercase.

### 5. Manual Inspection — Observations by Conflict Type

The following observations are from manual review of `name_all_conflicts_labeled.csv`, organized by
Tier 1 and Tier 2 labels. Each subsection documents patterns, edge cases, and open questions about
how a normalization pipeline should handle them.

#### Casing Only (58 rows)

Most cases are straightforward: `CVS Pharmacy` vs `CVS pharmacy`, `Honda of Jonesboro` vs
`Honda Of Jonesboro`, `Subway` vs `SUBWAY`. But several raise the question of whether casing is
the owner's stylistic choice:

- `ecoATM` vs `Ecoatm` — the camelCase is intentional branding
- `IndianOil` vs `Indianoil` — same pattern
- `OXXO` vs `Oxxo`, `bp` vs `BP` — all-caps/lowercase is the brand identity
- `CockTailz Fine Wine and Spirits` vs `Cocktailz Fine Wine and Spiritz` — mixed stylization
- `PuroClean` vs `Puroclean` — compound word casing

How do we know when capitalization is an abbreviation versus a stylistic choice? There is no
reliable automated signal for this. A rule that "prefer title case" would silently damage branded
names like `ecoATM` or `bp`.

Language-specific casing conventions add further complexity. French and Italian articles and
prepositions are conventionally lowercased in names: `Fleurs d'Alain` vs `Fleurs D'Alain`,
`Osteria del Tempo Perso` vs `Osteria Del Tempo Perso`. These follow grammar rules, not owner
preference. In Japanese, Western brand text tends to be uppercase by convention:
`セルフ写真館BLANC` vs `セルフ写真館Blanc`.

#### Normalization Equivalent — Conjunction (15 rows)

The conjunction normalizer works well. Open question: should the golden record prefer `&` universally,
or preserve the original language's conjunction (`e` in Italian, `y` in Spanish, `und` in German)?

One approach: use the language of the name attribute rather than GPS coordinates. A French-language
name in Texas should still use `et` if that is what the business uses. GPS coordinates can help as a
tiebreaker when the name language is ambiguous, but should not override name-level language signals.

#### Normalization Equivalent — Diacritic (19 rows)

Clear cases: `Imobiliária Alegro` vs `Imobiliaria Alegro` — accent should be preserved in languages
that use it. But edge cases arise when a word exists in multiple languages: `Café de l'Harmonie` vs
`Cafe de l'Harmonie` — is the accent French (required) or English-stylized (optional)?

Proposed approach: if the surrounding name text is in a language that uses the accent, keep it
(`Café` in a French name). If the name is English with a borrowed word, the owner may have chosen
either form. As with conjunctions, the name's own language is a stronger signal than GPS. If an
Italian café uses English branding with an accented `Café`, that may be intentional stylization
that cannot be resolved without owner input.

#### Normalization Equivalent — Punctuation (85 rows)

This is the most rule-friendly category. Observations by punctuation type:

**Dashes as separators**: Very common, easily normalized. `Farmers Insurance - David Hiney` vs
`Farmers Insurance David Hiney`, `Maricopa County Sheriff's Office - District III Substation` vs
`Maricopa County Sheriff's Office District III Substation`. Standard: drop separator dashes.
But dashes *within* compound words may reflect owner's choice: `Grill-Ecke` vs `Grillecke` (German
compound).

**Abbreviation dots**: `Dana Stampi s.r.l.` vs `Dana Stampi SRL`, `D.P.T.` vs `DPT`. Standard:
strip dots from abbreviations. Cultural note: `s.r.l.` is the conventional Italian form, `SRL` is
the database-normalized form. Keeping dots vs stripping is a formatting preference.

**Apostrophes**: Should be preserved — they carry meaning. `Aherne's` vs `Ahernes`, `Fredson's`
vs `Fredsons`, `L'ynara Brautmode` vs `Lynara Brautmode`, `Dunkin' Donuts` vs `Dunkin Donuts`.
Standard: prefer the form with the apostrophe.

**Quotation marks**: Likely drop. `Centro Aperto Polivalente per minori "LOL"` vs
`Centro Aperto Polivalente per Minori Lol`, `Friseur Salon "Zur alten Wache"` vs
`Friseur Salon "Alte Wache"` (the quotes are incidental — the real difference is the name inside
them, making this genuinely different).

**Plus signs and special characters**: `Gas` vs `Gas+`, `PostalAnnex+` vs `PostalAnnex`,
`Brothers Mechanical Services` vs `Brothers Mechanical Services®`. These are branding elements.
Standard: strip `+`, `®`, `™` for normalization but flag as owner-decided for the golden record.

**Exclamation marks**: `Maloserá` vs `Maloserá!` — likely owner's stylistic choice.

**Japanese nakaguro (・)**: `ビジネスホテル・キャッスル` vs `ビジネスホテルキャッスル` — the
nakaguro separates loanwords in katakana. Both forms are standard. Standard: strip for comparison,
prefer the nakaguro form in the golden record as it aids readability.

**Thai parentheses**: `โตโยต้า ลีสซิ่ง ประเทศไทย` vs `โตโยต้า ลิสซิ่ง(ประเทศไทย)` — this
looks like punctuation to English speakers, but there is also a Thai spelling difference
(`ลีสซิ่ง` vs `ลิสซิ่ง`) making it more than just parentheses.

**Extra conjunction in one side**: `Müller & Egerer Bäckerei Konditorei` vs
`Müller & Egerer Bäckerei & Konditorei` — one side has an `&` the other omits. This falls outside
conjunction normalization (which handles `and` ↔ `&` substitution, not insertion/deletion).

#### Normalization Equivalent — Spacing (76 rows)

Generally clean. Compound split/join cases are well-handled: `PhotoColorLab` vs `Photo Color Lab`,
`Dance4Life` vs `Dance 4 Life`. Japanese spacing differences (presence/absence of spaces between
words) are correctly caught.

#### Normalization Equivalent — Typo (37 rows)

Open question: could a typo dictionary or fuzzy-match library improve resolution? Levenshtein catches
1–2 character differences, but has no concept of common misspellings.

Edge cases:

- False flag: `Gimnasio R&C` vs `Gimnasio RYC` — the conjunction normalizer converts `&` to `and`
  but does not catch `&` → `Y` inside abbreviations where `Y` is the Spanish conjunction. Consider
  expanding conjunction handling to detect single-letter conjunction substitutions within words.
- Small kana: `ミカモラィディングクラブ` vs `ミカモライディングクラブ` — the small `ィ` vs full `イ`
  is a 1-character difference caught by Levenshtein but is actually a script-form issue (nonstandard
  small kana usage).
- Fullwidth Latin: `ヘアーサロンａ‐ｃｕｂｕ` vs `ヘアーサロンa‐cubu` — fullwidth ASCII vs halfwidth.
  Currently caught by typo because NFKD normalization handles the conversion before Levenshtein runs,
  but the remaining dash difference pushes it to typo.

#### Subset — Business Suffix (52 rows)

Not recommended for the normalization pipeline. Whether a name includes `LLC`, `Inc`, `GmbH`, or
`SRL` is partly legal identity, partly owner preference. Stripping suffixes for comparison is useful
(and the subset detection already handles this), but the golden record should preserve or omit them
based on policy rather than normalization rules.

#### Subset — Branch Suffix (46 rows)

This is where the dataset's Japanese and Thai representation becomes prominent. The pattern is
consistent: one side has the brand name, the other has brand + branch/store location.

Japanese examples:
- `百十` vs `百十 なんばこめじるし店` (brand vs Namba Komejirushi branch)
- `JINS` vs `JINS イオンモール宮崎店` (brand vs Aeon Mall Miyazaki branch)
- `ローソン` vs `ローソン いわき下好間店` (Lawson vs Lawson Iwaki branch)
- `カレット` vs `カレット洋菓子店 矢田店` (Carette vs Carette Confectionery Yada branch)
- `セブンイレブン` vs `セブンイレブン 波崎土合南店` (7-Eleven vs 7-Eleven Hasaki branch)
- `ゲオクラスポ蒲郡店` vs `ゲオ` (Geo Claspo Gamagori vs Geo — branch name longer on alt side)

English examples follow the same pattern with `Branch`, `Store`, `Center`, `Plaza`:
`US Bank Branch` vs `US Bank`.

The reconciliation decision is a **policy choice**: prefer the core brand name (shorter, more
portable) or the full branch listing (more specific, better for disambiguation in dense areas).
For Japanese convenience stores and chains where dozens of branches exist in one city, the branch
suffix is arguably necessary for disambiguation.

#### Subset — Facility Suffix (29 rows)

ATMs and bus stops. Japanese bus stops append `バス停`: `粟生団地` vs `粟生団地バス停`,
`東名吉田` vs `東名吉田バス停`. English ATMs: `Barclays` vs `Barclays ATM`.
Standard: prefer the simpler form for the golden record, as the facility type is typically captured
in the `categories` attribute rather than the name.

#### Subset — Parenthetical (36 rows)

Parenthetical content serves different purposes across scripts, and this distinction matters for
reconciliation:

**Thai — alternate name / English transliteration**: Thai listings frequently include an English
rendering or local nickname in parentheses as a disambiguation aid. This is a cultural convention
in Thai directory data, not SEO noise.
- `วิทยาลัยเทคนิคพระนครศรีอยุธยา` vs `วิทยาลัยเทคนิคพระนครศรีอยุธยา (Phra Na Khon Sri Ayutthaya Technical College)`
- `สวนอาหารบ้านตะวันแดง` vs `สวนอาหารบ้านตะวันแดง (Baan Tawundang Resturant)`
- `สะพานนครพิงค์` vs `สะพานนครพิงค์ (Nakhonping Bridge)`
- `วัดวาลุการาม` vs `วัดวาลุการาม (หนองผักบุ้ง)` — Thai temple + village disambiguation

**Japanese — kana reading or tagline**: Japanese uses parentheses for furigana (pronunciation
guide) or descriptive taglines.
- `虎侍我炎（とらじがえん）【筑後吉井紅豚餃子】` vs `虎侍我炎` — kanji name + hiragana reading + product tagline
- `Moana` vs `Moana (モアナ)` — English brand + katakana reading
- `みらい平駅` vs `みらい平駅 (Miraidaira Sta.)` — station name + romanized abbreviation

**English — location or acronym**: Parenthetical content in English names tends to be location
context or acronym expansion.
- `PetSmart` vs `PetSmart Folsom (East Bidwell)` — brand + location
- `Vitality Integrated Programs` vs `Vitality Integrated Programs (VIP)` — name + acronym
- `CIBC Branch (Cash at ATM only)` vs `CIBC` — descriptor in parentheses

Standard: the parenthetical content is informative but not part of the core name. Prefer the
form without parentheses for the golden record, but preserve parenthetical content as metadata
where the schema supports alternate names.

#### Subset — Descriptor (442 rows)

The largest subset category. These are cases where one side adds business description, department
names, service lists, or location qualifiers that the other side omits. Examples:

- `エコモベーカリーヨコハマモトマチ` vs `エコモベーカリー` (Ecomo Bakery Yokohama Motomachi vs Ecomo Bakery)
- `Clarkson Eyecare Florida` vs `Clarkson Eyecare` (location qualifier)
- `โรงแรมพร3 #ขอนแก่น` vs `โรงแรมพร 3` (hotel + hashtag city name vs just hotel)

In most cases the shorter form is the core business name and the longer form is a listing-specific
elaboration. Standard: prefer the shorter core name. However, this is a policy decision — the owner
may prefer the more specific form.

#### Genuinely Different (187 rows)

These are rows where the two sides provide semantically different names that no normalization
can reconcile. Manual inspection reveals several recurring patterns:

**Different brand names for the same entity**: `Citibanamex 30 Av. Playa Del Carmen` vs `Citibank`
— the Mexican subsidiary name vs the global brand. `Concord Foot & Ankle Center` vs `Concord Feet`
— same place, different naming conventions.

**Different locations entirely**: `Sport Clips Haircuts of Panama City - Cahall's Deli Plaza` vs
`Sport Clips Haircuts of Lynn Haven` — same chain, different cities. This may indicate a matching
error upstream rather than a name reconciliation problem.

**Same entity, different naming conventions**: `Barclays ATM` vs `Barclays Bank Cash Machine`,
`Mishicot Fire Dept` vs `Mishicot Volunteer Fire Depart` — the same place described differently by
two providers.

**Shared prefix with different qualifiers**: `Profile Publishing Location 1` vs
`Profile Publishing Location Name - Suite` — neither name contains the other. Both sides append
different qualifiers to a shared prefix. This is the key distinction from `subset`, where one name
is fully contained in the other.

**Japanese — same brand, different branch encoding**: `ヤマト運輸 YamatoTransport` vs
`ヤマト運輸 伊達センター` — one side appends an English transliteration, the other appends a
Japanese branch name (Date Center). Neither contains the other.
`ゴルフパートナーpga大宮店` vs `ゴルフパートナー PGATOURSUPERSTORE大宮店` — same store, but one
abbreviates the brand and the other uses the full name.

**Borderline cases that could arguably be other labels:**

- `สำนักงานอธิการบดี ม.รามคำแหง` vs `สำนักงานอธิการบดี มหาวิทยาลัยรามคำแหง` — `ม.` is a
  standard Thai abbreviation for `มหาวิทยาลัย` (university). This is not a semantic difference
  but an abbreviation expansion that the normalizer cannot detect without a Thai abbreviation
  lookup table. Similar patterns likely exist for Japanese honorifics and common abbreviations.
- `B&B Hôtels` vs `B&B Hôtel Lyon Ouest Tassin` — brand vs brand + location. This looks like
  a subset but the brand name itself differs (`Hôtels` plural vs `Hôtel` singular), so substring
  containment fails.
- `元妙古觀` vs `元妙古观 Yuanmiao Temple` — traditional vs simplified Chinese characters plus
  an English transliteration. Character-set normalization (traditional ↔ simplified Chinese) is
  not currently implemented.

**Test/placeholder data**: `PUBLIC location 324234 #%&*` vs `PUBLIC LOCATION NAME EXTERNALID NAME`
— these are not real place names and indicate test data that was not filtered from the dataset.

For the majority of genuinely different rows, neither side is obviously "correct" — both represent
valid names for the place from different providers' perspectives. These require human review for
golden dataset labeling. The reconciliation system should either select one based on external
signals (provider reliability, recency) or abstain.

### 6. Staged Normalization Pipeline

Script: `scripts/names/09_name_normalization.py`  
Outputs: `analysis/names/name_normalization_staged.csv`, `analysis/names/name_remaining_conflicts.csv`

Analogous to the phone normalization pipeline (`06_phone_normalization.py`), this script applies
progressively stronger normalization rules and measures how apparent conflict drops at each stage.
Each stage is cumulative (includes all prior stages), so conflict count can only decrease —
the pipeline is **monotonic**.

| Stage  | Rule                              | Conflict Count | Conflict Rate | Improvement vs Prior |
|--------|-----------------------------------|----------------|---------------|----------------------|
| S0     | Raw primary name comparison       | 1083           | 54.15%        | —                    |
| S1     | Casing (lowercase)                | 1025           | 51.25%        | 5.36%                |
| S2     | Unicode (fullwidth + diacritics)  | 1001           | 50.05%        | 2.34%                |
| S3     | Punctuation stripped              | 935            | 46.75%        | 6.59%                |
| S4     | Spaces stripped                   | 867            | 43.35%        | 7.27%                |
| S5     | Conjunctions unified              | 854            | 42.70%        | 1.50%                |
| S6     | Spelling normalized               | 853            | 42.65%        | 0.12%                |
| S7     | Katakana→hiragana                 | 852            | 42.60%        | 0.12%                |
| S8     | Word reorder (sorted)             | 826            | 41.30%        | 3.05%                |
| S9     | Typo detection (Levenshtein ≤ 2)  | 768            | 38.40%        | 7.02%                |
| Subset | One name contained in the other   | 176            | 8.80%         | 77.08%               |

Percentages are based on 2000 total rows. Of the 1083 original primary-name conflicts:

| Disposition              | Rows | % of Conflicts | Meaning                                       |
|--------------------------|------|----------------|-----------------------------------------------|
| Resolved by normalization| 315  | 29.1%          | Same name after formatting noise is stripped   |
| Subset (policy decision) | 592  | 54.7%          | One name is contained in the other             |
| Genuinely different      | 176  | 16.3%          | Irreducible conflict requiring human review    |

**Interpretation**

**Raw string comparison overstates name conflict by approximately 6x.** After applying
all normalization stages and subset detection, apparent conflict drops from 54.2% to 8.8%.

**The largest single improvement (S4, 7.27%) comes from space normalization**, reflecting the
dataset's heavy Japanese and Thai representation where word boundary conventions differ between
sources. Punctuation stripping (S3, 6.59%) is the second largest, driven by dash-as-separator
and abbreviation-dot patterns across Latin scripts.

**Typo detection (S9, 7.02%) resolves a meaningful tail** of 1–2 character differences —
Thai spelling variants, small kana, and minor misspellings that no other normalizer catches.

**Subset detection accounts for the majority of remaining conflicts** — 592 of 768 post-
normalization conflicts (77%) are cases where one name is contained in the other (brand vs
brand+branch, name vs name+parenthetical, etc.). These are not formatting noise — they are
genuine data differences where one source includes more information. Reconciliation requires
a **policy decision**: prefer the shorter core name or the longer specific listing.

**The remaining 176 rows (8.8% of all rows, 16.3% of conflicts) are genuinely different names**
requiring human review or abstention. These represent the golden dataset population for name
reconciliation.

`name_remaining_conflicts.csv` exports all 1083 original conflicts with their final disposition
(`normalized`, `subset`, or `different`), raw names, normalized forms, address/category context,
confidence, and source providers — the complete audit trail for inspection.

The following subsections document the design decisions behind each stage, based on the manual
inspection in Section 5.

#### Stage 0: Raw comparison

Baseline conflict count on extracted primary names. 1083 conflicts (54.15% of 2000 rows).

#### Stage 1: Casing normalization

Lowercase both sides. Resolves: `ROSSMANN` ↔ `Rossmann`, `CVS Pharmacy` ↔ `CVS pharmacy`.

Does **not** resolve owner-stylized casing (`ecoATM`, `IndianOil`). These are acknowledged
as information loss, but casing cannot be reliably preserved without an external brand database.
Language-specific casing rules (French `d'`/`del`, Japanese preference for uppercase Western text)
are also lost here but are formatting preferences rather than semantic content.

#### Stage 2: Unicode normalization

NFKD → NFC (fullwidth → ASCII), strip Latin diacritics. Resolves: `ａ` → `a`, `é` → `e`,
fullwidth space → ASCII space.

Open question: diacritics in borrowed words (`Café` in English context). Proposed rule: strip for
comparison, prefer the accented form in the golden record when the name language uses that accent.

#### Stage 3: Punctuation stripping

Remove dashes, dots, quotes, nakaguro (・), `®`, `™`, `+`, `!`. Collapse whitespace.
Resolves: `Farmers Insurance - David Hiney` ↔ `Farmers Insurance David Hiney`,
`Dana Stampi s.r.l.` ↔ `Dana Stampi SRL`, `ビジネスホテル・キャッスル` ↔ `ビジネスホテルキャッスル`.

Apostrophes: **preserve** — they carry linguistic meaning (`Aherne's`, `L'ynara`, `Dunkin'`).

Open question: dashes within compound words (`Grill-Ecke` vs `Grillecke`, `A-1 Dental` vs
`A1 Dental`) — these may be owner's choice.

#### Stage 4: Space normalization

Strip all spaces and compare. Resolves: `Photo Color Lab` ↔ `PhotoColorLab`,
`Dance 4 Life` ↔ `Dance4Life`, `からみそラーメン ふくろう` ↔ `からみそラーメンふくろう`.

This is the most aggressive normalization stage. It collapses all word boundary information.

#### Stage 5: Conjunction normalization

Unify `&`/`and`/`et`/`und`/`y`/`e` → canonical form. Resolves: `Howarth Timber and Building Supplies`
↔ `Howarth Timber & Building Supplies`, `Acqua e Sapone` ↔ `Acqua & Sapone`.

Open question: should the golden record use `&` universally, or preserve the language-appropriate
conjunction? Proposed: preserve `&` for English, preserve the native conjunction for other languages,
use name language as the primary signal (not GPS).

#### Stage 6: Spelling normalization

British → American English. Resolves: `centre` → `center`, `defence` → `defense`.

Rarely fires in this dataset (1 row), but included for completeness.

#### Stage 7: Script-form normalization (Japanese)

Katakana → hiragana. Japanese has two phonetic scripts that represent the same sounds with different
characters (see katakana/hiragana explanation in Section 2). Converting all katakana to hiragana before
comparing catches cases where one source uses one script and the other uses the other.
Resolves: `コインランドリーハナコ` ↔ `コインランドリーはなこ` (both read "Coin Laundry Hanako").

**This must come before word reorder** — sorting characters requires katakana and hiragana to
already be unified, otherwise `ハナコ` and `はなこ` sort to different positions and the reorder
stage cannot match them.

#### Stage 8: Word reorder

Sort all characters alphabetically and compare. Builds on Stage 7 so that katakana/hiragana
differences have already been resolved before sorting.
Resolves: `Colombo Cristoforo` ↔ `Cristoforo Colombo`.

**Note on subset detection:** Sorting is used only for normalization-equivalent detection. Subset
detection operates on Stage 7 (unsorted) and Stage 4 (space-stripped) forms, because sorting
destroys substring containment — `ろーそん` sorted becomes `そろんー`, which is no longer
contained in the sorted longer name.

#### Stage 9: Typo detection

Levenshtein distance ≤ 2 with similarity ≥ 0.85, on strings of 5+ characters. These conservative
thresholds catch single transpositions, dropped letters, or character substitutions while avoiding
false positives on short strings (see Levenshtein explanation in Section 2).
Resolves: `คลีนิคบ้านหมอ` ↔ `คลีนิกบ้านหมอ` (Thai spelling variant),
`ミカモラィディングクラブ` ↔ `ミカモライディングクラブ` (small kana variant).

Typo detection runs on Stage 7 forms (readable, unsorted) rather than Stage 8 (sorted), because
Levenshtein on sorted characters measures character-set difference, not actual edit distance.

#### After normalization: subset detection

Once normalization is complete, check whether one normalized name is contained in the other.
This check runs on Stage 7 (hiragana-normalized) and Stage 4 (space-stripped) forms — not Stage 8
(sorted) — because sorting destroys substring containment.

This identifies brand-vs-branch, parenthetical, and descriptor patterns. The reconciliation
decision for subsets is a policy choice (prefer shorter core name vs longer specific listing),
not a normalization decision.

#### Remaining conflicts: genuinely different

The 176 rows that survive all 9 normalization stages and are not subsets represent the irreducible
conflict population. These require either human review, external verification, or abstention.

### 7. Golden Dataset Selection

Script: `scripts/names/10_name_golden_candidates.py`  
Outputs: `analysis/names/name_golden_candidates.csv`, `analysis/names/name_golden_summary.csv`

This script applies concrete selection rules to every row and produces a recommended golden
name for each place. For each row, the output contains the raw alt and base names, the
selected golden name, which side it came from (`alt` / `base` / `agreement` / `abstain`),
and the reason it was selected.

#### Selection Rules for Casing and Normalization Conflicts (296 rows)

When two names are the same after normalization, the script picks the better-formatted version.
Rules are applied in priority order — the first rule that differentiates the two sides wins.

**Rule 1 — Branded casing.** Detects camelCase and internal capitalization: `ecoATM`, `IndianOil`,
`PuroClean`, `PhotoColorLab`, `McDonald's`. Works by scanning each word for a lowercase→uppercase
transition (the `o→A` in `ecoATM`). If one side has branded casing and the other doesn't, the
branded version wins. This is the highest-priority rule because branded casing is an intentional
design choice that all other rules would destroy.

Known edge cases: `Del Moro` (D→M transition looks branded but isn't), `Ters Corner`,
`Nova Cordis`. These are false positives where a title-cased two-word name happens to have a
lowercase→uppercase boundary at the word break. The false positive rate is low (~3 rows).

**Rule 2 — Apostrophe quality.** Prefers linguistically valid apostrophes: `Aherne's` over
`Ahernes`, `Dunkin' Donuts` over `Dunkin Donuts`, `L'ynara Brautmode` over `Lynara Brautmode`.
Rejects grammatically invalid apostrophes: `Ongkeco'S` (capital after apostrophe mid-word),
`La' Ziza` (apostrophe before space with short prefix).

**Rule 3 — Accented form.** Prefers the side with more Latin accents: `Café de l'Harmonie`
over `Cafe de l'Harmonie`, `Imobiliária Alegro` over `Imobiliaria Alegro`. Accents carry
linguistic information — stripping them loses data.

Trade-off: accents currently win over casing quality. `Auto-école De L'etoile` beats
`Auto-Ecole de l'Etoile` because it has more accents, despite worse casing on `De` and `L'etoile`.
An ML model could weigh both factors simultaneously; rules must pick one.

Note: accents are preserved even in English-context names like `Wildberry Pancakes and Café`.
This is intentional — if the business included the accent, it is part of their name.

**Rule 4 — Nakaguro (Japanese).** Prefers the katakana separator dot (・) for readability:
`ビジネスホテル・キャッスル` over `ビジネスホテルキャッスル`.

**Rule 5 — Abbreviation periods.** Prefers: `Mr. Roof Louisville` over `Mr Roof Louisville`,
`Mark A. Hammer` over `Mark A Hammer`.

**Rule 6 — Compound dashes.** Preserves intentional hyphenated names: `Save-A-Lot` over
`Save A Lot`, `A-1 Dental` over `A1 Dental`.

**Rule 7 — Casing quality score.** A point-based scorer that evaluates:
- French/Italian/Spanish particles (`d'`, `del`, `di`, `de`, `von`) should be lowercase
  when not the first word: `Fleurs d'Alain` over `Fleurs D'Alain`, `Osteria del Tempo Perso`
  over `Osteria Del Tempo Perso`
- English prepositions (`of`, `and`, `in`, `at`) should be lowercase: `City of Santee` preferred
- Short all-caps words (≤4 chars) are likely abbreviations and get a bonus: `OXXO` over `Oxxo`,
  `HDFC Bank` over `Hdfc Bank`, `BP` over `bp`
- Long all-caps words (>4 chars) are penalized as shouting: `Rossmann` over `ROSSMANN`,
  `Shell` over `SHELL`, `Raqsa Radiadores` over `RAQSA Radiadores`
- Title case on content words gets a bonus: `Un Sogno Verde` over `Un sogno verde`
- Japanese convention: uppercase Western text in CJK-mixed names gets a strong bonus:
  `セルフ写真館BLANC` over `セルフ写真館Blanc`

**Rule 8 — Compound over spaced.** Prefers the unsplit form: `PhotoColorLab` over
`Photo Color Lab`, `LloydsPharmacy` over `Lloyds Pharmacy`. If someone wrote it as one word,
it was probably intentional. Exception: trailing numbers prefer the spaced form
(`pickleball 406` over `pickleball406`).

For Japanese, this means preferring the no-space form, which is the conventional writing style.

**Rule 9 — Shorter.** If all else ties, prefer the shorter name (less noise).

**Abstain.** If every rule ties (both sides score identically on every metric), the row is
flagged for human review. This typically happens with Thai and Japanese typo variants where
both spellings are plausible: `วัดสถารศ` vs `วัดสถารส`, `คลีนิคบ้านหมอ` vs `คลีนิกบ้านหมอ`,
`コインランドリーはなこ` vs `コインランドリーハナコ`.

#### Selection Rules for Subset Conflicts (600 rows)

When one name is contained in the other, the script decides whether to keep the shorter
core name or the longer specific listing.

**Rule 1 — CJK/Thai: prefer longer.** Japanese branch names (`JINS イオンモール宮崎店`),
Thai transliterations, kana readings (`Moana (モアナ)`), and bus stop suffixes
(`西野山団地 バス停`) are all essential for disambiguation. The longer form is always
preferred for CJK and Thai scripts.

**Rule 2 — Generic short name: prefer longer.** If the shorter name is ≤6 characters or a
single word (`Sushi`, `Prince`, `CFE`), it is not a viable standalone business name.
Prefer the longer form. Parenthetical and pipe content (`(Cash at ATM only)`, `| OshKosh`)
is stripped before length evaluation.

**Rule 3 — Business-type descriptor: prefer longer.** If the extra content contains a word
that describes what the place IS (from a curated list: Hotel, Bar, Café, Spa, Bistro,
Supermarket, Salon, Hospital, Museum, School, etc.), the longer name is more informative.
`Southland Casino Hotel` over `Southland Casino`, `Giant Eagle Supermarket` over
`Giant Eagle`, `Calico Jack's Bistro` over `Calico Jacks`.

**Rule 4 — Latin default: prefer shorter.** For multi-word Latin names where no special
rule fires, the shorter form is the core business name. `Emerson Fence` over
`Emerson Fence Inc`, `Farmers Insurance` over `Farmers Insurance David Hiney`.

#### Known Limitations and Edge Cases

The rule-based approach handles approximately **90% of name conflicts correctly** based on
manual review of all 2000 rows. The remaining ~10% fall into categories that genuinely
require semantic understanding:

**Location vs business-type ambiguity (the primary gap).** The extra content in subset
conflicts can be either a business-type descriptor (Hotel, Supermarket — keep it) or a
location qualifier (Marseille, Florida — drop it). Rules cannot reliably distinguish between
them. Examples where rules fail:

- `Tumi` vs `TUMI Champs-Elysees` — Champs-Elysees is a location, should prefer shorter
- `Walmart` vs `Walmart Azle` — Azle is a location, should prefer shorter
- `Schlotzsky's` vs `Schlotzsky's (Colony Way - Madison, MS)` — location in parentheses
- `BP` vs `BP America` — America is not a useful qualifier

But the same rule that would drop locations would also incorrectly drop:
- `Kip McGrath` vs `Kip McGrath Hammersmith` — Hammersmith is location AND disambiguation
- `Victoria Coiffure` vs `Victoria Coiffure Florissant` — same problem

This is the single largest gap in the rule-based approach and the clearest case for an
ML/SLM component: classify the extra content as **business-type** (keep), **location**
(usually drop, sometimes keep for disambiguation), or **noise** (drop).

**ALL CAPS in shorter name.** When the shorter name is ALL CAPS and the longer name has
better casing: `MID COUNTY LANES` vs `Mid County Lanes and Entertainment`,
`POLE DANCE AVEC MOI` vs `Pole Dance avec Moi Marseille`. Rules prefer shorter (core name)
but the shorter name has worse formatting. This is irreconcilable without making the casing
rule override the subset rule, which causes regressions elsewhere (picking longer names
that include locations). Documented as a known trade-off.

**Accent vs casing trade-off.** `Auto-école De L'etoile` (more accents, worse casing) vs
`Auto-Ecole de l'Etoile` (fewer accents, better casing). Rules prioritize accents because
they carry linguistic meaning. An ML model could weigh both simultaneously.

**Typo variants.** Thai and Japanese spelling variants where both forms exist in real usage
(`คลีนิค` vs `คลินิก`, `วัดสถารศ` vs `วัดสถารส`) cannot be resolved without a native-
speaker dictionary or corpus frequency data. The system correctly abstains on these.

**Special characters as branding.** `Gas` vs `Gas+`, `PostalAnnex` vs `PostalAnnex+` —
the `+` may be part of the brand identity or just punctuation noise. No general rule exists.

**THE YARD, LLC.** Both `THE` (3 chars) and `YARD` (4 chars) score as short abbreviations,
so the ALL CAPS version wins. Ideally the golden record would be `The Yard` without the
comma or `LLC`, but constructing a name from parts of both sides is a different (harder)
problem than selecting between them.

#### Where ML/SLM Would Add Value

The golden candidates CSV provides labeled training data for a hybrid approach. The specific
gaps where ML adds value:

1. **Extra content classification.** Given a core name and extra content, classify the extra
   as: business-type (keep), location (usually drop), or noise (drop). A small language model
   fine-tuned on the `extra_content` column could handle this with high accuracy.

2. **Casing reconstruction.** Given a name in unknown casing, produce the correct cased form.
   This requires knowledge of brand names (`ecoATM`), language conventions (`d'Alain`), and
   abbreviations (`HDFC`). A model trained on correct-casing examples from the golden dataset.

3. **Typo resolution.** Given two similar spellings, determine which is correct using corpus
   frequency or dictionary lookup. Especially valuable for Thai and Japanese where both
   spellings may appear in real listings.

4. **Name construction.** Instead of selecting between two existing names, construct the best
   name from parts of both (e.g., take the core name from one side and the business type from
   the other). This is beyond selection and requires generation.

#### Summary

Of 2000 rows in the dataset:

| Outcome                     | Rows | % of Total | Meaning                                      |
|-----------------------------|------|------------|----------------------------------------------|
| Agreement (no conflict)     | 917  | 45.9%      | Both sides identical — golden name is obvious |
| Rule-selected with confidence| ~850| ~42.5%     | Rules produce a defensible selection          |
| Rule-selected with caveats  | ~50  | ~2.5%      | Selection is plausible but edge cases exist   |
| Abstain (human review)      | ~180 | ~9.0%      | Rules cannot determine the better name        |

The rule-based system covers **~88% of rows with a confident selection** and honestly
flags the remaining ~12% for human review or ML augmentation. The `name_golden_candidates.csv`
output provides the full audit trail: every row has a selected name, a source, and a reason,
enabling row-by-row review and correction.

### 8. Confidence

**Confidence is not analyzed for names.** Per the phone analysis conclusion, `confidence` measures
place existence, not attribute quality. The same structural limitations (base clustering at 1.0,
small gaps, no relationship to attribute correctness) apply equally to names. Confidence analysis
is not repeated here.

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
