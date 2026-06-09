"""FDA Orphan Drug Designations enrichment (non-blocking).

Source: FDA OOPD "Search Orphan Drug Designations and Approvals"
(accessdata.fda.gov/scripts/opdlisting/oopd/). There is no JSON API; the search
is a ColdFusion form behind Akamai bot management. We:
  1. open the search page to obtain Akamai session cookies (_abck, bm_sz),
  2. POST the search form (GET is blocked) for each drug's generic name,
  3. parse the "Detailed" text output into structured designation records,
  4. cache the raw HTML per drug to data/raw/orphan/.

If the site is unreachable, orphan_status falls back to "unknown" and the rest
of the pipeline proceeds (the brief treats orphan as enrichment).
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from . import util

BASE = "https://www.accessdata.fda.gov/scripts/opdlisting/oopd/"
RESULTS = BASE + "OOPD_Results.cfm"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_OPENER = None
_AVAILABLE: Optional[bool] = None


def _opener():
    global _OPENER
    if _OPENER is None:
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        op.addheaders = [("User-Agent", _UA), ("Referer", BASE)]
        try:
            op.open(BASE, timeout=40).read()  # prime Akamai cookies
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] orphan: could not open OOPD search page: {e}")
        _OPENER = op
    return _OPENER


def _query_html(generic: str) -> Optional[str]:
    """POST the OOPD form for ``generic``; cache + return raw HTML."""
    cache = util.RAW_ORPHAN / (util.slug(generic) + ".html")
    if cache.exists():
        return cache.read_text()
    fields = {
        "Product_name": generic, "sponsor_name": "", "Designation": "",
        "Search_param": "DESDATE",
        "Designation_Start_Date": "01/01/1983", "Designation_End_Date": "12/31/2026",
        "Output_Format": "Detailed", "RecordsPerPage": "300",
        "Sort_order": "Date_Order", "newSearch": "1",
    }
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        RESULTS, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    for attempt in range(4):
        try:
            html = _opener().open(req, timeout=60).read().decode("utf-8", "replace")
            cache.write_text(html)
            return html
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                print(f"  [warn] orphan query failed for {generic}: {e}")
            import time
            time.sleep(2 + attempt)
    return None


_FIELD = lambda label, chunk, nxt: (  # noqa: E731
    (re.search(label + r":\s*(.+?)\s+(?:" + nxt + r"):", chunk, re.S) or [None, None])[1]
)


def _parse(html: str, generic: str) -> List[Dict[str, Any]]:
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    chunks = re.split(r"Result Number:\s*\d+", text)[1:]
    norm_target = util.normalize_name(generic)
    out: List[Dict[str, Any]] = []
    for c in chunks:
        gen = _FIELD("Generic Name", c, "Trade Name|Date Designated|Orphan Designation")
        if not gen:
            continue
        # keep only rows whose generic matches the queried ingredient
        if norm_target and norm_target not in util.normalize_name(gen):
            continue
        designation = _FIELD("Orphan Designation", c, "Orphan Designation Status")
        status = _FIELD("Orphan Designation Status", c, "FDA Orphan Approval Status|Sponsor")
        appr_status = _FIELD("FDA Orphan Approval Status", c, "Marketing Approval Date|Sponsor|Approved Labeled Indication")
        m_date = re.search(r"Marketing Approval Date:\s*([\d/]+)", c)
        d_date = re.search(r"Date Designated:\s*([\d/]+)", c)
        out.append({
            "generic": gen.strip(),
            "designation": (designation or "").strip(),
            "designation_status": (status or "").strip(),
            "approval_status": (appr_status or "").strip(),
            "date_designated": d_date.group(1) if d_date else None,
            "marketing_approval_date": m_date.group(1) if m_date else None,
            "approved": bool(m_date) or "approved" in (status or "").lower(),
        })
    return out


def orphan_for(drug: Dict[str, Any]) -> Dict[str, Any]:
    """Return an orphan summary for a cohort drug.

    orphan_status in: orphan_approved | designated_not_approved | none | unknown
    """
    global _AVAILABLE
    # query by the first/primary ingredient token (most specific, avoids combos)
    tokens = drug.get("ingredients") or util.ingredient_tokens(drug["generic"])
    primary = (tokens[0] if tokens else drug["generic"]).lower()
    html = _query_html(primary)
    if html is None or "Orphan Designation" not in html:
        if _AVAILABLE is None:
            _AVAILABLE = html is not None and "Orphan" in (html or "")
        if not html:
            return {"orphan_status": "unknown", "n_orphan_designations": 0,
                    "n_orphan_approved": 0, "orphan_designations": []}
    _AVAILABLE = True
    recs = _parse(html, primary)
    approved = [r for r in recs if r["approved"]]
    distinct_approved = {r["designation"].lower().rstrip(".") for r in approved if r["designation"]}
    if not recs:
        status = "none"
    elif approved:
        status = "orphan_approved"
    else:
        status = "designated_not_approved"
    return {
        "orphan_status": status,
        "n_orphan_designations": len(recs),
        "n_orphan_approved": len(approved),
        "n_distinct_orphan_indications_approved": len(distinct_approved),
        "serial_orphan_candidate": len(distinct_approved) >= 2,
        "orphan_designations": recs[:40],
    }


def _validate():
    for d in [
        {"brand": "Imbruvica", "generic": "ibrutinib"},
        {"brand": "Calquence", "generic": "acalabrutinib"},
        {"brand": "Eliquis", "generic": "apixaban"},
        {"brand": "Revlimid", "generic": "lenalidomide"},
    ]:
        s = orphan_for(d)
        print(f"{d['brand']:12s} status={s['orphan_status']:24s} "
              f"desig={s['n_orphan_designations']} approved={s['n_orphan_approved']} "
              f"distinct_appr={s.get('n_distinct_orphan_indications_approved')} "
              f"serial={s.get('serial_orphan_candidate')}")


if __name__ == "__main__":
    _validate()
