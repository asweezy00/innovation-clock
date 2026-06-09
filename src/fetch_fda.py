"""Resolve cohort drugs to their FDA applications and extract the timeline of
new-indication (efficacy supplement) events.

THE CRUX (see docs/METHODOLOGY.md):
  * Resolve via ``products.active_ingredients.name`` -- the openFDA ``openfda``
    block is empty on many originator NDAs/BLAs, so brand/generic searches miss
    the original application (e.g. ELIQUIS brand search 404s; apixaban generic
    search returns only ANDAs). The active-ingredient field is populated on the
    originator record itself and is the reliable key.
  * Keep only NDA/BLA originator apps; drop ANDA generics.
  * A molecule may have several NDAs/BLAs -> anchor YEAR 0 to the EARLIEST
    ORIG+AP submission across all matched apps.
  * New indications = SUPPL + AP + class EFFICACY, deduped by date across apps.
  * Modality from the ANCHOR application prefix: NDA -> small molecule (clock 9),
    BLA -> biologic (clock 13).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from . import util

DRUGSFDA = "drug/drugsfda.json"
LABEL = "drug/label.json"


def _search(endpoint: str, expr: str, limit: int = 100) -> Dict[str, Any]:
    """Cached openFDA search. ``expr`` is the value of the search= parameter."""
    url = util.fda_url(endpoint, {"search": expr, "limit": limit})
    tag = util.slug(endpoint.split("/")[-1].replace(".json", "") + "__" + expr)
    cache = util.RAW_FDA / (tag + ".json")
    data = util.get_json(url, cache)
    return data or {"results": []}


def _parse_date(yyyymmdd: Optional[str]) -> Optional[dt.date]:
    if not yyyymmdd or len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        return None
    try:
        return dt.date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))
    except ValueError:
        return None


def _app_ingredient_set(app: Dict[str, Any]) -> frozenset:
    names = set()
    for prod in app.get("products", []) or []:
        for ing in prod.get("active_ingredients", []) or []:
            n = util.normalize_name(ing.get("name"))
            if n:
                names.add(n)
    return frozenset(names)


def _is_efficacy(sub: Dict[str, Any]) -> bool:
    code = (sub.get("submission_class_code") or "").upper()
    desc = (sub.get("submission_class_code_description") or "").upper()
    return code == "EFFICACY" or "EFFICACY" in desc


def resolve_apps(drug: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the originator (NDA/BLA) application records that belong to ``drug``.

    ``drug`` keys used: brand, generic, optional ``ingredients`` (list of
    normalized tokens) and optional ``manual_apps`` (explicit app numbers).
    """
    brand = drug["brand"]
    generic = drug["generic"]
    expected = frozenset(drug.get("ingredients") or util.ingredient_tokens(generic))

    # Gather candidate application records from several search angles, union by
    # application_number. active_ingredients.name is primary; brand/generic are
    # cheap fallbacks that occasionally surface extra reformulation apps.
    searches: List[str] = []
    for tok in expected:
        searches.append('products.active_ingredients.name:"%s"' % tok)
    searches.append('openfda.brand_name:"%s"' % brand.upper())
    searches.append('openfda.generic_name:"%s"' % generic.upper())
    for app_no in drug.get("manual_apps", []) or []:
        searches.append('application_number:"%s"' % app_no)

    candidates: Dict[str, Dict[str, Any]] = {}
    for expr in searches:
        for res in _search(DRUGSFDA, expr).get("results", []):
            app_no = res.get("application_number", "")
            if app_no and app_no not in candidates:
                candidates[app_no] = res

    manual = set(drug.get("manual_apps", []) or [])
    matched: List[Dict[str, Any]] = []
    for app_no, res in candidates.items():
        if not app_no.startswith(("NDA", "BLA")):
            continue  # drop ANDA generics + others
        if app_no in manual:
            matched.append(res)
            continue
        app_ings = _app_ingredient_set(res)
        # Match when the expected ingredient set is contained in the app's
        # ingredients (handles combos: both members must be present) OR the
        # brand matches (covers odd ingredient spellings).
        brand_hit = util.normalize_name(brand) in {
            util.normalize_name(b) for b in (res.get("openfda", {}).get("brand_name") or [])
        }
        if (expected and expected <= app_ings) or brand_hit:
            matched.append(res)
    return matched


def build_drug_record(drug: Dict[str, Any]) -> Dict[str, Any]:
    """Compute anchor approval, modality, and the list of indication events."""
    apps = resolve_apps(drug)
    app_numbers = sorted({a["application_number"] for a in apps})

    # Anchor = earliest ORIG + AP across all matched apps.
    orig_dates: List[tuple] = []  # (date, app_number)
    for a in apps:
        for sub in a.get("submissions", []) or []:
            if sub.get("submission_type") == "ORIG" and sub.get("submission_status") == "AP":
                d = _parse_date(sub.get("submission_status_date"))
                if d:
                    orig_dates.append((d, a["application_number"]))
    anchor_date: Optional[dt.date] = None
    anchor_app: Optional[str] = None
    if orig_dates:
        anchor_date, anchor_app = min(orig_dates, key=lambda x: x[0])

    modality = clock_year = None
    if anchor_app:
        if anchor_app.startswith("BLA"):
            modality, clock_year = "biologic", 13
        else:
            modality, clock_year = "small molecule", 9

    # Efficacy supplements across all matched apps, deduped by date.
    events: Dict[dt.date, Dict[str, Any]] = {}
    for a in apps:
        for sub in a.get("submissions", []) or []:
            if sub.get("submission_type") == "SUPPL" and sub.get("submission_status") == "AP" and _is_efficacy(sub):
                d = _parse_date(sub.get("submission_status_date"))
                if not d or (anchor_date and d < anchor_date):
                    continue
                if d not in events:
                    events[d] = {
                        "date": d,
                        "app_number": a["application_number"],
                        "submission_number": sub.get("submission_number"),
                    }
    event_list = [events[k] for k in sorted(events)]
    for ev in event_list:
        ev["years_after_launch"] = (
            round((ev["date"] - anchor_date).days / 365.25, 2) if anchor_date else None
        )

    return {
        "brand": drug["brand"],
        "generic": drug["generic"],
        "matched_app_numbers": app_numbers,
        "anchor_app": anchor_app,
        "anchor_date": anchor_date,
        "modality": modality,
        "clock_year": clock_year,
        "events": event_list,
        "n_apps": len(apps),
    }


def fetch_indication_text(drug: Dict[str, Any]) -> Optional[str]:
    """Best-effort indications_and_usage text from the label endpoint."""
    for expr in (
        'openfda.brand_name:"%s"' % drug["brand"].upper(),
        'openfda.generic_name:"%s"' % drug["generic"].upper(),
    ):
        res = _search(LABEL, expr, limit=1).get("results", [])
        if res:
            txt = res[0].get("indications_and_usage")
            if isinstance(txt, list):
                txt = " ".join(txt)
            if txt:
                return " ".join(txt.split())[:1200]
    return None


# --- Validation harness ----------------------------------------------------
def _validate():
    tests = [
        {"brand": "Eliquis", "generic": "apixaban"},
        {"brand": "Enbrel", "generic": "etanercept"},
        {"brand": "Calquence", "generic": "acalabrutinib"},
        {"brand": "Imbruvica", "generic": "ibrutinib"},
        {"brand": "Entresto", "generic": "sacubitril; valsartan"},
    ]
    for t in tests:
        rec = build_drug_record(t)
        print(f"\n=== {t['brand']} ({t['generic']}) ===")
        print(f"  apps: {rec['matched_app_numbers']}")
        print(f"  anchor: {rec['anchor_app']} @ {rec['anchor_date']} "
              f"-> {rec['modality']} (clock yr {rec['clock_year']})")
        print(f"  indication events: {len(rec['events'])}")
        for ev in rec["events"]:
            print(f"     {ev['date']}  +{ev['years_after_launch']:>5}y  "
                  f"{ev['app_number']} suppl#{ev['submission_number']}")


if __name__ == "__main__":
    _validate()
