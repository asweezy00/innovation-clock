"""Discover and fetch CMS Medicare Part D / Part B 'Spending by Drug' datasets.

Dataset UUIDs change yearly, so we DISCOVER them from the CMS open-data catalog
(data.cms.gov/data.json) rather than hardcoding. Raw API pages are cached so
reruns are offline.

Provides:
  * discover_datasets()  -> {'part_d': {...}, 'part_b': {...}}
  * load_spending(part)  -> pandas DataFrame of per-drug latest-year spend
  * top_part_d(n)        -> top-N Part D drugs by latest gross spend
  * spend_for(brand, generic, part) -> latest-year total spend (fuzzy join)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd

from . import util

CATALOG_URL = "https://data.cms.gov/data.json"
DATA_API = "https://data.cms.gov/data-api/v1/dataset/{uuid}/data"

# Exact catalog titles for the ANNUAL (not Quarterly) datasets.
TITLES = {
    "part_d": "Medicare Part D Spending by Drug",
    "part_b": "Medicare Part B Spending by Drug",
}

_CACHE: Dict[str, Any] = {}


def discover_datasets() -> Dict[str, Dict[str, Any]]:
    """Find Part D & Part B annual dataset UUIDs + latest spend year."""
    if "datasets" in _CACHE:
        return _CACHE["datasets"]
    catalog = util.get_json(CATALOG_URL, util.RAW_CMS / "catalog_data.json", sleep=0.0)
    out: Dict[str, Dict[str, Any]] = {}
    for key, title in TITLES.items():
        match = None
        for d in catalog.get("dataset", []):
            if d.get("title", "").strip().lower() == title.lower():
                match = d
                break
        if not match:
            print(f"  [warn] CMS catalog: '{title}' not found")
            continue
        uuid = None
        for dist in match.get("distribution", []):
            au = dist.get("accessURL") or ""
            m = re.search(r"/dataset/([0-9a-f-]{36})/data", au)
            if m:
                uuid = m.group(1)
                break
        out[key] = {
            "title": title,
            "uuid": uuid,
            "modified": match.get("modified"),
            "landing": match.get("landingPage"),
        }
    _CACHE["datasets"] = out
    return out


def _fetch_all_rows(uuid: str, tag: str, page: int = 5000) -> List[Dict[str, Any]]:
    """Paginate the data-api, caching each page."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{DATA_API.format(uuid=uuid)}?size={page}&offset={offset}"
        cache = util.RAW_CMS / f"{tag}__off{offset}.json"
        batch = util.get_json(url, cache, sleep=0.2)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def _latest_spend_year(cols: List[str]) -> Optional[str]:
    years = sorted({m.group(1) for c in cols for m in [re.search(r"Tot_Spndng_(\d{4})", c)] if m})
    return years[-1] if years else None


def load_spending(part: str) -> pd.DataFrame:
    """Return a tidy DataFrame: brand, generic, mftr, spend (latest year), year."""
    cache_key = f"df_{part}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    ds = discover_datasets().get(part)
    if not ds or not ds.get("uuid"):
        print(f"  [warn] no CMS dataset for {part}")
        return pd.DataFrame()
    rows = _fetch_all_rows(ds["uuid"], f"{part}_spending")
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    year = _latest_spend_year(list(df.columns))
    spend_col = f"Tot_Spndng_{year}"
    # Part D has per-manufacturer rows + an 'Overall' aggregate; keep Overall.
    if "Mftr_Name" in df.columns and (df["Mftr_Name"] == "Overall").any():
        df = df[df["Mftr_Name"] == "Overall"].copy()
    df = df[df[spend_col].notna()].copy()
    df["spend"] = pd.to_numeric(df[spend_col], errors="coerce")
    df = df[df["spend"].notna()]
    out = pd.DataFrame({
        "brand": df["Brnd_Name"].astype(str).str.strip(),
        "generic": df.get("Gnrc_Name", "").astype(str).str.strip(),
        "spend": df["spend"],
        "spend_year": int(year),
        "norm_brand": df["Brnd_Name"].map(util.normalize_name),
        "norm_generic": df.get("Gnrc_Name", "").map(util.normalize_name),
    }).sort_values("spend", ascending=False).reset_index(drop=True)
    _CACHE[cache_key] = out
    return out


def top_part_d(n: int = 50) -> List[Dict[str, Any]]:
    """Top-N Part D drugs by latest-year gross spend (Overall rows).

    Heuristic for 'negotiation-eligible': single brand-name drugs (brand differs
    from generic, i.e. not a commodity generic, not a supply item). True IRA
    eligibility also requires 7+ yrs on market with no generic/biosimilar -- we
    document that approximation in METHODOLOGY.md.
    """
    df = load_spending("part_d")
    if df.empty:
        return []
    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        nb, ng = r["norm_brand"], r["norm_generic"]
        if not nb or nb == ng:
            continue  # drop commodity generics / supplies
        if any(k in r["brand"].lower() for k in ("needle", "syringe", "lancet", "alcohol", "swab", "strip")):
            continue
        out.append({"brand": r["brand"], "generic": r["generic"], "spend": float(r["spend"])})
        if len(out) >= n:
            break
    return out


def spend_for(brand: str, generic: str, part: str, aliases: Optional[List[str]] = None,
              threshold: int = 88) -> Optional[float]:
    """Latest-year total Medicare spend for the *negotiated unit* of a drug.

    A CMS-negotiated drug is a brand FAMILY, not a single SKU: Part D 'Overall'
    rows are split across device/strength variants (Enbrel / Enbrel Mini /
    Enbrel SureClick) and, where CMS bundles them, across distinct brands of the
    same molecule (Ozempic / Rybelsus / Wegovy; NovoLog / Fiasp). We therefore
    SUM the family rather than taking one representative row.

    A Part D 'Overall' row joins the unit when it is single-source (brand differs
    from generic, excluding authorized generics and commodity rows) AND either
      * its brand equals the drug's brand or a curated CMS-bundle alias, or
      * its brand is a device/strength variant of one of those (``stem + ' ...'``)
        carrying the SAME active ingredient (so the biphasic 'NovoLog Mix 70-30'
        and the Kisqali-Femara co-pack, which have different ingredients, are
        excluded).
    Part B is HCPCS-coded with no manufacturer/Overall column, so its rows are
    summed across the matched HCPCS codes (brand or generic match).
    """
    from rapidfuzz import fuzz, process

    df = load_spending(part)
    if df.empty:
        return None
    nb, ng = util.normalize_name(brand), util.normalize_name(generic)
    stems = {nb} | {util.normalize_name(a) for a in (aliases or [])}
    stems.discard("")

    if part == "part_b":
        # HCPCS rows: one drug spans several codes -> sum brand/generic matches.
        rows = df[(df["norm_brand"].isin(stems)) | ((df["norm_generic"] == ng) & (ng != ""))]
        if not rows.empty:
            return float(rows["spend"].sum())
    else:
        single_source = df["norm_brand"] != df["norm_generic"]
        exact = df["norm_brand"].isin(stems)
        variant = df["norm_brand"].apply(lambda b: any(b.startswith(s + " ") for s in stems)) \
            & (df["norm_generic"] == ng) & (ng != "")
        fam = df[single_source & (exact | variant)]
        if not fam.empty:
            return float(fam["spend"].sum())
        # fall back to a same-ingredient single-source match if brand naming differs
        gen = df[single_source & (df["norm_generic"] == ng) & (ng != "")]
        if not gen.empty:
            return float(gen["spend"].sum())

    # fuzzy fallback (rare): nearest brand, then nearest generic
    choices = df["norm_brand"].tolist()
    if nb and choices:
        best = process.extractOne(nb, choices, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= threshold:
            return float(df.iloc[best[2]]["spend"])
    if ng:
        gchoices = df["norm_generic"].tolist()
        best = process.extractOne(ng, gchoices, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= threshold:
            return float(df.iloc[best[2]]["spend"])
    return None


def _validate():
    ds = discover_datasets()
    for k, v in ds.items():
        print(f"{k}: {v['title']}  uuid={v['uuid']}  modified={v['modified']}")
    dfd = load_spending("part_d")
    print(f"\nPart D rows (Overall): {len(dfd)}  latest year {dfd['spend_year'].iloc[0]}")
    print("Top 10 Part D by spend:")
    for d in top_part_d(10):
        print(f"   ${d['spend']/1e9:6.2f}B  {d['brand']} ({d['generic']})")
    for b, g in [("Eliquis", "apixaban"), ("Enbrel", "etanercept"), ("Keytruda", "pembrolizumab")]:
        print(f"  spend_for {b}: PartD={spend_for(b,g,'part_d')}  PartB={spend_for(b,g,'part_b')}")


if __name__ == "__main__":
    _validate()
