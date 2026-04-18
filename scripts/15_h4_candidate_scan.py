"""
15_h4_candidate_scan.py — Programmatic scan for H4 (compound extra-content) candidates

Purpose:
    Search the full 602 subset-conflict rows in name_golden_candidates.csv for cases
    where extra_content contains BOTH a business-type term AND a location indicator.
    These are candidates for H4 name construction — neither the long nor short name
    is the ideal canonical form.

    The existing 31 candidates in h4_construction_candidates.csv were found during
    manual inspection. This script applies systematic heuristics to find additional
    ones that manual review may have missed, and outputs them for human verification.

Method — two-phase heuristic filter:

    Phase 1 (business-type signal):
        Any word in extra_content appears in BIZ_VOCAB (the same extended vocabulary
        used in 11b_name_baselines.py, plus additional domain terms).

    Phase 2 (location signal):
        At least one of:
        a) extra_content contains a word that appears title-cased in the long name
           (proper noun detection, same heuristic as rule baseline)
        b) extra_content contains a spatial preposition pattern: "in X", "de X",
           "- X", "/ X" where X starts with an uppercase letter
        c) extra_content contains a known city/region suffix keyword

    Both phases must pass → flagged as candidate.

    Additionally: rows where only Phase 1 passes (business type, no location) are
    output separately as "business_type_only" — these are correctly handled by H1
    (keep longer) but may contain edge cases worth reviewing.

Outputs:
    analysis/names/h4_scan_candidates.csv     — new compound candidates (both phases)
    analysis/names/h4_scan_biz_only.csv       — rows with business type, no location
    analysis/names/h4_scan_summary.txt        — summary of scan results

Usage:
    python 15_h4_candidate_scan.py
    python 15_h4_candidate_scan.py --min-biz-words 1 --verbose
"""

import argparse
import re
from pathlib import Path

import pandas as pd

ROOT           = Path(__file__).parent.parent
GOLDEN_PATH    = ROOT / "analysis/names/name_golden_candidates.csv"
EXISTING_PATH  = ROOT / "analysis/names/h4_construction_candidates.csv"
OUT_NEW        = ROOT / "analysis/names/h4_scan_candidates.csv"
OUT_BIZ_ONLY   = ROOT / "analysis/names/h4_scan_biz_only.csv"
OUT_SUMMARY    = ROOT / "analysis/names/h4_scan_summary.txt"


# ── Vocabulary ────────────────────────────────────────────────────────────────
# From 11b_name_baselines.py BIZ_FULL, plus additional terms found in H4 analysis

BIZ_VOCAB = {
    # Accommodations
    "hotel", "motel", "inn", "resort", "lodge", "hostel", "suites", "apartments",
    # Food & drink
    "bar", "pub", "tavern", "lounge", "brewery", "winery", "cafe", "bistro",
    "diner", "eatery", "canteen", "restaurant", "pizzeria", "steakhouse", "grill",
    "kitchen", "buffet", "deli", "bakery", "bistrot", "ristorante", "trattoria",
    "sushi", "lanches",
    # Health & wellness
    "spa", "salon", "barbershop", "clinic", "pharmacy", "medical", "dental",
    "veterinary", "orthodontist", "dentist", "natatorium", "hospice", "therapists",
    "physiotherapie", "praxis", "therapien",
    # Retail
    "supermarket", "market", "mall", "plaza", "shop", "store", "boutique",
    "outlet", "centre", "center", "florists", "cosmetics", "acessorios",
    # Culture & education
    "museum", "gallery", "theater", "cinema", "studio", "school", "university",
    "institute", "academy", "kirjasto",
    # Services
    "gym", "fitness", "bank", "insurance", "agency", "agent", "advisor",
    "dance", "photography", "design", "transport", "care", "community",
    "arena", "photo", "lab", "propane", "chocolate", "bulbs", "prosthetics",
    "orthotics", "senior", "retirement",
    # Business/professional services
    "fachmarkt", "immobilien", "sachverstandige", "engenharia", "estacionamento",
    "saude", "terraza", "vibrationstechnik", "autofficina", "ankauf", "verkauf",
    # H4-specific: compound-type terms found in candidates
    "opticians", "audiologists", "hospice", "training", "domicile", "serviceburo",
    "geschäftsstelle", "contrôle", "technique", "automobile", "bacaro",
    "kfz-prüfstelle", "zerspanungstechnik", "รีสอร์ท",
    # Generic business-type indicators often in compounds
    "services", "solutions", "group", "consulting", "management", "logistics",
    "construction", "engineering", "technologies", "systems", "associates",
    "partners", "industries", "enterprises", "international",
    # Car / automotive
    "rental", "dealership", "garage", "autohaus",
}

# Spatial prepositions that indicate a location follows
SPATIAL_PREPS = re.compile(
    r'\b(in|de|del|da|at|near|von|im|en|af|v|w)\s+[A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝ]',
    re.IGNORECASE,
)

# Separator + Capitalized word (e.g. "- Beaverton", "/ Lyon", "| Toronto")
SEP_CAP = re.compile(r'[-/|–]\s*[A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝ][a-z]{2,}')


def has_biz_signal(extra: str) -> tuple[bool, set]:
    """Return (has_biz, matching_words)."""
    words = set(re.findall(r'\b\w+\b', extra.lower()))
    matches = words & BIZ_VOCAB
    return bool(matches), matches


def has_location_signal(extra: str, long_name: str, biz_matches: set) -> tuple[bool, str]:
    """Return (has_loc, reason).

    Location detection deliberately excludes words that matched as business-type terms:
    a single word like "hotel" appearing as "Hotel" in long_name is not a location signal —
    it's the same word that triggered Phase 1. We only want words that are SEPARATELY
    capitalized proper nouns not in the business vocabulary.
    """
    # (a) spatial preposition pattern
    if SPATIAL_PREPS.search(extra):
        return True, "spatial_prep"

    # (b) separator + capitalized word (e.g. "- Beaverton", "/ Lyon")
    if SEP_CAP.search(extra):
        return True, "sep_cap"

    # (c) proper noun: lowercase word in extra_content appears title-cased in long_name,
    # BUT only if the word is not itself a business-type term (avoids self-matching).
    ec_words = [w for w in re.findall(r'\b[a-z]{3,}\b', extra.lower())
                if w not in BIZ_VOCAB and w not in biz_matches]
    for w in ec_words:
        capitalized = w[0].upper() + w[1:]
        if re.search(r'\b' + re.escape(capitalized) + r'\b', long_name):
            return True, f"proper_noun:{w}"

    return False, ""


def main():
    parser = argparse.ArgumentParser(description="H4 candidate scan — find compound extra-content rows")
    parser.add_argument("--verbose", action="store_true", help="Print each flagged row")
    args = parser.parse_args()

    # Load data
    df = pd.read_csv(GOLDEN_PATH)
    subset = df[df["conflict_type"] == "subset"].copy()
    subset["extra_content"] = subset["extra_content"].fillna("").astype(str)

    # Determine long/short name for each row
    # In golden candidates: alt_name and base_name; extra_content is the suffix
    # The "selected_source" tells us which was preferred, but for H4 we just need
    # the longer and shorter names. Use len to determine.
    subset["short_name"] = subset.apply(
        lambda r: r["alt_name"] if len(str(r["alt_name"])) <= len(str(r["base_name"])) else r["base_name"],
        axis=1,
    )
    subset["long_name"] = subset.apply(
        lambda r: r["base_name"] if len(str(r["alt_name"])) <= len(str(r["base_name"])) else r["alt_name"],
        axis=1,
    )

    # Load existing candidates to de-duplicate
    existing = pd.read_csv(EXISTING_PATH)
    existing_keys = set(zip(existing["short_name"].str.strip().str.lower(),
                            existing["long_name"].str.strip().str.lower()))

    # Scan
    compound_candidates = []
    biz_only_rows = []

    for _, row in subset.iterrows():
        extra     = row["extra_content"]
        long_name = str(row["long_name"])
        short     = str(row["short_name"])
        key       = (short.strip().lower(), long_name.strip().lower())

        if not extra.strip():
            continue

        has_biz, biz_matches = has_biz_signal(extra)
        has_loc, loc_reason  = has_location_signal(extra, long_name, biz_matches)

        if has_biz and has_loc:
            is_existing = key in existing_keys
            rec = {
                "short_name":    short,
                "long_name":     long_name,
                "extra_content": extra,
                "biz_matches":   ", ".join(sorted(biz_matches)),
                "loc_reason":    loc_reason,
                "already_in_h4": is_existing,
                "city":          row.get("city", ""),
                "id":            row.get("id", ""),
            }
            compound_candidates.append(rec)
            if args.verbose and not is_existing:
                print(f"  NEW compound: {short!r} | {long_name!r}")
                print(f"    extra: {extra!r}  biz={biz_matches}  loc={loc_reason}")

        elif has_biz and not has_loc:
            biz_only_rows.append({
                "short_name":    short,
                "long_name":     long_name,
                "extra_content": extra,
                "biz_matches":   ", ".join(sorted(biz_matches)),
                "city":          row.get("city", ""),
            })

    # Results
    df_compound = pd.DataFrame(compound_candidates)
    df_biz_only = pd.DataFrame(biz_only_rows)

    new_compound = df_compound[~df_compound["already_in_h4"]] if len(df_compound) else df_compound
    already_found = df_compound[df_compound["already_in_h4"]] if len(df_compound) else df_compound

    summary_lines = [
        f"H4 candidate scan — {len(subset)} subset rows in name_golden_candidates.csv",
        f"",
        f"Phase results:",
        f"  Compound candidates (biz + loc): {len(df_compound)}",
        f"    Already in h4_construction_candidates.csv: {len(already_found)}",
        f"    NEW candidates not yet in h4 set:          {len(new_compound)}",
        f"  Business-type only (no location signal):     {len(df_biz_only)}",
        f"  No signal (unclassifiable by heuristic):     {len(subset) - len(df_compound) - len(df_biz_only)}",
        f"",
        f"New compound candidates:",
    ]

    if len(new_compound) > 0:
        for _, r in new_compound.iterrows():
            summary_lines.append(
                f"  {r['short_name']!r:35s} | extra={r['extra_content']!r} | biz={r['biz_matches']} | loc={r['loc_reason']}"
            )
    else:
        summary_lines.append("  (none — all compound-signal rows already in h4 set)")

    summary_text = "\n".join(summary_lines)
    print(summary_text)

    # Save
    if len(df_compound):
        df_compound.to_csv(OUT_NEW, index=False)
        print(f"\nSaved compound candidates → {OUT_NEW}")

    if len(df_biz_only):
        df_biz_only.to_csv(OUT_BIZ_ONLY, index=False)
        print(f"Saved biz-only rows       → {OUT_BIZ_ONLY}")

    OUT_SUMMARY.write_text(summary_text)
    print(f"Saved summary             → {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
