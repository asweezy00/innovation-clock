"""Define the analysis cohort = union of (A) IRA negotiation Cycles 1-3 and
(B) the top Medicare Part D drugs by latest-year gross spend.

The Cycle 1-3 drug lists and Maximum Fair Prices (MFPs) are CURATED CONSTANTS,
each verified against primary CMS fact sheets and cross-checked vs KFF on
2026-06-07 (see SOURCES and data/raw/policy_facts.json). They are baked in --
not scraped at runtime -- so the pipeline is deterministic and offline-capable;
CMS HTML/PDF layouts change and are not reliably machine-parseable. The dynamic,
fetched-at-runtime data are FDA approvals (fetch_fda), CMS spend (fetch_cms),
and orphan status (fetch_orphan).

MFP_USD values are the CMS-published 30-day-supply-equivalent negotiated prices.
Cycle 3 MFPs are null by design: CMS does not publish them until Nov 30, 2026
(effective Jan 1, 2028). NEVER substitute an unverified number for null.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import util
from . import fetch_cms

RETRIEVED = "2026-06-07"

# --- Cycle 1: IPAY 2026, MFP effective Jan 1 2026 (announced Aug 15 2024) -----
SRC_C1 = "https://www.cms.gov/files/document/fact-sheet-negotiated-prices-initial-price-applicability-year-2026.pdf"
CYCLE1: List[Dict[str, Any]] = [
    {"brand": "Eliquis", "generic": "apixaban", "mfp_usd": 231, "list_usd": 521, "part": "Part D", "mfr": "Bristol Myers Squibb"},
    {"brand": "Jardiance", "generic": "empagliflozin", "mfp_usd": 197, "list_usd": 573, "part": "Part D", "mfr": "Boehringer Ingelheim"},
    {"brand": "Xarelto", "generic": "rivaroxaban", "mfp_usd": 197, "list_usd": 517, "part": "Part D", "mfr": "Janssen"},
    {"brand": "Januvia", "generic": "sitagliptin", "mfp_usd": 113, "list_usd": 527, "part": "Part D", "mfr": "Merck"},
    {"brand": "Farxiga", "generic": "dapagliflozin", "mfp_usd": 178.50, "list_usd": 556, "part": "Part D", "mfr": "AstraZeneca"},
    {"brand": "Entresto", "generic": "sacubitril/valsartan", "mfp_usd": 295, "list_usd": 628, "part": "Part D", "mfr": "Novartis"},
    {"brand": "Enbrel", "generic": "etanercept", "mfp_usd": 2355, "list_usd": 7106, "part": "Part D", "mfr": "Amgen/Immunex"},
    {"brand": "Imbruvica", "generic": "ibrutinib", "mfp_usd": 9319, "list_usd": 14934, "part": "Part D", "mfr": "Pharmacyclics (AbbVie/J&J)"},
    {"brand": "Stelara", "generic": "ustekinumab", "mfp_usd": 4695, "list_usd": 13836, "part": "Part D", "mfr": "Janssen"},
    {"brand": "NovoLog", "generic": "insulin aspart", "mfp_usd": 119, "list_usd": 495, "part": "Part D", "mfr": "Novo Nordisk",
     "aliases": ["Fiasp", "NovoLog FlexPen", "NovoLog PenFill", "Fiasp FlexTouch"]},
]

# --- Cycle 2: IPAY 2027, MFP effective Jan 1 2027 (prices announced Nov 25 2025) -
SRC_C2 = "https://www.cms.gov/files/document/fact-sheet-negotiated-prices-ipay-2027.pdf"
CYCLE2: List[Dict[str, Any]] = [
    {"brand": "Ozempic", "generic": "semaglutide", "mfp_usd": 274, "list_usd": 959, "part": "Part D", "mfr": "Novo Nordisk", "aliases": ["Rybelsus", "Wegovy"]},
    {"brand": "Trelegy Ellipta", "generic": "fluticasone furoate/umeclidinium/vilanterol", "mfp_usd": 175, "list_usd": 654, "part": "Part D", "mfr": "GSK"},
    {"brand": "Xtandi", "generic": "enzalutamide", "mfp_usd": 7004, "list_usd": 13480, "part": "Part D", "mfr": "Astellas"},
    {"brand": "Pomalyst", "generic": "pomalidomide", "mfp_usd": 8650, "list_usd": 21744, "part": "Part D", "mfr": "Bristol Myers Squibb"},
    {"brand": "Ofev", "generic": "nintedanib", "mfp_usd": 6350, "list_usd": 12622, "part": "Part D", "mfr": "Boehringer Ingelheim"},
    {"brand": "Ibrance", "generic": "palbociclib", "mfp_usd": 7871, "list_usd": 15741, "part": "Part D", "mfr": "Pfizer"},
    {"brand": "Linzess", "generic": "linaclotide", "mfp_usd": 136, "list_usd": 539, "part": "Part D", "mfr": "AbbVie"},
    {"brand": "Calquence", "generic": "acalabrutinib", "mfp_usd": 8600, "list_usd": 14228, "part": "Part D", "mfr": "AstraZeneca"},
    {"brand": "Austedo", "generic": "deutetrabenazine", "mfp_usd": 4093, "list_usd": 6623, "part": "Part D", "mfr": "Teva", "aliases": ["Austedo XR"]},
    {"brand": "Breo Ellipta", "generic": "fluticasone furoate/vilanterol", "mfp_usd": 67, "list_usd": 397, "part": "Part D", "mfr": "GSK"},
    {"brand": "Xifaxan", "generic": "rifaximin", "mfp_usd": 1000, "list_usd": 2696, "part": "Part D", "mfr": "Salix"},
    {"brand": "Vraylar", "generic": "cariprazine", "mfp_usd": 770, "list_usd": 1376, "part": "Part D", "mfr": "AbbVie"},
    {"brand": "Tradjenta", "generic": "linagliptin", "mfp_usd": 78, "list_usd": 488, "part": "Part D", "mfr": "Boehringer Ingelheim", "renegotiation_cycle": 3},
    {"brand": "Janumet", "generic": "sitagliptin/metformin", "mfp_usd": 80, "list_usd": 526, "part": "Part D", "mfr": "Merck", "aliases": ["Janumet XR"]},
    {"brand": "Otezla", "generic": "apremilast", "mfp_usd": 1650, "list_usd": 4722, "part": "Part D", "mfr": "Amgen", "aliases": ["Otezla XR"]},
]

# --- Cycle 3: IPAY 2028, selected Jan 27 2026; MFPs NOT yet published (null) ---
# First-ever Part B drugs included. Tradjenta is renegotiation (already in C2).
SRC_C3 = "https://www.cms.gov/files/document/factsheet-medicare-negotiation-selected-drug-list-ipay-2028.pdf"
CYCLE3: List[Dict[str, Any]] = [
    {"brand": "Anoro Ellipta", "generic": "umeclidinium/vilanterol", "mfp_usd": None, "part": "Part D", "mfr": "GSK"},
    {"brand": "Biktarvy", "generic": "bictegravir/emtricitabine/tenofovir alafenamide", "mfp_usd": None, "part": "Part D", "mfr": "Gilead"},
    {"brand": "Botox", "generic": "onabotulinumtoxinA", "mfp_usd": None, "part": "Part B", "mfr": "AbbVie", "first_part_b": True},
    {"brand": "Cimzia", "generic": "certolizumab pegol", "mfp_usd": None, "part": "Part B", "mfr": "UCB", "first_part_b": True},
    {"brand": "Cosentyx", "generic": "secukinumab", "mfp_usd": None, "part": "Part D", "mfr": "Novartis"},
    {"brand": "Entyvio", "generic": "vedolizumab", "mfp_usd": None, "part": "Part B", "mfr": "Takeda", "first_part_b": True},
    {"brand": "Erleada", "generic": "apalutamide", "mfp_usd": None, "part": "Part D", "mfr": "Johnson & Johnson"},
    {"brand": "Kisqali", "generic": "ribociclib", "mfp_usd": None, "part": "Part D", "mfr": "Novartis"},
    {"brand": "Lenvima", "generic": "lenvatinib", "mfp_usd": None, "part": "Part D", "mfr": "Eisai"},
    {"brand": "Orencia", "generic": "abatacept", "mfp_usd": None, "part": "Part B", "mfr": "Bristol Myers Squibb", "first_part_b": True},
    {"brand": "Rexulti", "generic": "brexpiprazole", "mfp_usd": None, "part": "Part D", "mfr": "Otsuka"},
    {"brand": "Trulicity", "generic": "dulaglutide", "mfp_usd": None, "part": "Part D", "mfr": "Eli Lilly"},
    {"brand": "Verzenio", "generic": "abemaciclib", "mfp_usd": None, "part": "Part D", "mfr": "Eli Lilly"},
    {"brand": "Xeljanz", "generic": "tofacitinib", "mfp_usd": None, "part": "Part D", "mfr": "Pfizer", "aliases": ["Xeljanz XR"]},
    # Xolair: classified Part B under the "majority of gross spending" definition;
    # CMS's press release headlines only 4 Part B drugs (Botox/Cimzia/Orencia/Entyvio).
    # See METHODOLOGY.md. Spend is looked up in BOTH Part B and Part D regardless.
    {"brand": "Xolair", "generic": "omalizumab", "mfp_usd": None, "part": "Part B", "mfr": "Genentech/Novartis", "first_part_b": "contested"},
]

SOURCES = {
    1: {"src": SRC_C1, "effective_year": 2026, "selected": "2023-08-29", "prices": "2024-08-15"},
    2: {"src": SRC_C2, "effective_year": 2027, "selected": "2025-01-17", "prices": "2025-11-25"},
    3: {"src": SRC_C3, "effective_year": 2028, "selected": "2026-01-27", "prices": "pending (by 2026-11-30)"},
}


def _norm_record(d: Dict[str, Any], cycle: int) -> Dict[str, Any]:
    rec = dict(d)
    rec["ira_cycle"] = cycle
    rec["ira_effective_year"] = SOURCES[cycle]["effective_year"]
    rec["source_url"] = SOURCES[cycle]["src"]
    rec["ingredients"] = util.ingredient_tokens(d["generic"])
    rec["ingredient_key"] = util.ingredient_set(d["generic"])
    rec.setdefault("part", "Part D")
    rec.setdefault("mfp_usd", None)
    return rec


def negotiated_cohort() -> List[Dict[str, Any]]:
    """All IRA-selected drugs (Cycles 1-3), deduped by ingredient set.

    A drug selected in multiple cycles (e.g. Tradjenta: Cycle 2 selection +
    Cycle 3 renegotiation) is recorded once under its EARLIEST cycle, with the
    renegotiation noted.
    """
    by_key: Dict[frozenset, Dict[str, Any]] = {}
    for cycle, lst in ((1, CYCLE1), (2, CYCLE2), (3, CYCLE3)):
        for d in lst:
            rec = _norm_record(d, cycle)
            key = rec["ingredient_key"]
            if key in by_key:
                # already selected in an earlier cycle -> note later cycle
                prev = by_key[key]
                prev.setdefault("also_cycles", []).append(cycle)
            else:
                by_key[key] = rec
    return list(by_key.values())


def build_cohort(top_n: int = 50, target_max: int = 70) -> List[Dict[str, Any]]:
    """Union of negotiated cohort + top-N Part D drugs by spend.

    Returns a list of cohort records. ``in_negotiated`` / ``in_top_spend`` flags
    record why each drug is included.
    """
    cohort: Dict[frozenset, Dict[str, Any]] = {}
    brand_index: Dict[str, frozenset] = {}  # normalized brand/alias -> ingredient_key
    for rec in negotiated_cohort():
        rec["in_negotiated"] = True
        rec["in_top_spend"] = False
        rec["cohort_source"] = "IRA Cycle %d" % rec["ira_cycle"]
        cohort[rec["ingredient_key"]] = rec
        for b in [rec["brand"]] + rec.get("aliases", []):
            nb = util.normalize_name(b)
            if nb:
                brand_index[nb] = rec["ingredient_key"]

    # (B) top Part D by spend. Match to a negotiated drug by ingredient set OR by
    # brand name (CMS abbreviates combo ingredients, so brand is the safer key).
    for d in fetch_cms.top_part_d(top_n):
        key = util.ingredient_set(d["generic"])
        nb = util.normalize_name(d["brand"])
        match_key = key if key in cohort else brand_index.get(nb)
        if match_key is not None and match_key in cohort:
            cohort[match_key]["in_top_spend"] = True
            cohort[match_key]["part_d_spend_hint"] = d["spend"]
            continue
        if not key:
            continue
        if len(cohort) >= target_max:
            continue
        cohort[key] = {
            "brand": d["brand"], "generic": d["generic"],
            "ingredients": util.ingredient_tokens(d["generic"]),
            "ingredient_key": key,
            "ira_cycle": None, "ira_effective_year": None, "mfp_usd": None,
            "part": "Part D", "mfr": None, "source_url": None,
            "in_negotiated": False, "in_top_spend": True,
            "cohort_source": "Top-%d Part D spend" % top_n,
            "part_d_spend_hint": d["spend"],
        }
    return list(cohort.values())


def _validate():
    neg = negotiated_cohort()
    print(f"Negotiated cohort (unique molecules): {len(neg)}")
    cyc = {1: 0, 2: 0, 3: 0}
    for r in neg:
        cyc[r["ira_cycle"]] += 1
    print(f"  by primary cycle: {cyc}")
    reneg = [r for r in neg if r.get("renegotiation_cycle") or r.get("also_cycles")]
    print(f"  multi-cycle/renegotiation: {[r['brand'] for r in reneg]}")
    coh = build_cohort()
    print(f"\nFull cohort (union w/ top-50 Part D): {len(coh)} unique molecules")
    print(f"  negotiated & in top-spend: {sum(1 for r in coh if r['in_negotiated'] and r['in_top_spend'])}")
    print(f"  top-spend only (non-negotiated): {sum(1 for r in coh if not r['in_negotiated'])}")
    print("  sample non-negotiated top-spend drugs:")
    for r in [r for r in coh if not r["in_negotiated"]][:12]:
        print(f"     {r['brand']} ({r['generic']})  ~${r.get('part_d_spend_hint',0)/1e9:.2f}B")


if __name__ == "__main__":
    _validate()
