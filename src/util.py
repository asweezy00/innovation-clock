"""Shared utilities: cached HTTP, name normalization, paths.

All network access in the pipeline funnels through ``get_json`` so that every
raw response is cached to disk. Once the cache is warm, reruns are fully
offline and deterministic (a requirement of the project brief).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
RAW_FDA = RAW / "fda"
RAW_CMS = RAW / "cms"
RAW_ORPHAN = RAW / "orphan"
PROCESSED = DATA / "processed"
DOCS = ROOT / "docs"

for _p in (RAW_FDA, RAW_CMS, RAW_ORPHAN, PROCESSED, DOCS):
    _p.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "innovation-clock-research/1.0 (Medicare IRA drug-timing analysis; "
    "contact: research@example.org)"
)

# openFDA API key is optional; raises the rate limit if present.
OPENFDA_API_KEY = os.environ.get("OPENFDA_API_KEY", "").strip()


def slug(text: str, maxlen: int = 80) -> str:
    """Filesystem-safe slug for cache filenames."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    if len(s) > maxlen:
        h = hashlib.sha1(text.encode()).hexdigest()[:8]
        s = s[:maxlen] + "_" + h
    return s or "query"


def get_json(
    url: str,
    cache_path: Path,
    *,
    sleep: float = 0.3,
    max_retries: int = 5,
    timeout: int = 45,
    ok_404: bool = True,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """GET ``url`` as JSON with on-disk caching, retry/backoff, and etiquette.

    Returns parsed JSON, or ``None`` when the resource legitimately has no
    data (HTTP 404 with ``ok_404``). Cached responses are returned verbatim
    and incur no network call.
    """
    cache_path = Path(cache_path)
    if cache_path.exists() and not force:
        try:
            return json.loads(cache_path.read_text())
        except json.JSONDecodeError:
            pass  # corrupt cache -> refetch

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload))
            time.sleep(sleep)  # be polite between live calls
            return payload
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 404 and ok_404:
                # openFDA returns 404 for "no matching results" -> cache empty.
                empty = {"meta": {"results": {"total": 0}}, "results": []}
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(empty))
                time.sleep(sleep)
                return empty
            if e.code == 400:
                # Malformed query for ONE search angle (e.g. a combo generic with
                # punctuation). Don't crash the pipeline -> empty, logged, and let
                # the other search angles resolve the drug.
                print(f"  [warn] 400 Bad Request (skipping this query): {url}")
                empty = {"meta": {"results": {"total": 0}}, "results": [], "_bad_request": True}
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(empty))
                time.sleep(sleep)
                return empty
            if e.code in (429, 500, 502, 503, 504):
                wait = min(2 ** attempt, 30) + 0.3 * attempt
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
            continue
    print(f"  [warn] giving up on {url}: {last_err}")
    return None


def fda_url(endpoint: str, params: Dict[str, Any]) -> str:
    if OPENFDA_API_KEY:
        params = {**params, "api_key": OPENFDA_API_KEY}
    return f"https://api.fda.gov/{endpoint}?" + urllib.parse.urlencode(params)


# --- Name normalization (used for FDA resolution + CMS join) ----------------
# Salt / form suffixes stripped so "DAPAGLIFLOZIN PROPANEDIOL" == "DAPAGLIFLOZIN".
_SALTS = {
    "HYDROCHLORIDE", "HCL", "SULFATE", "SODIUM", "CALCIUM", "MESYLATE",
    "MALEATE", "FUMARATE", "ACETATE", "PHOSPHATE", "POTASSIUM", "BROMIDE",
    "CITRATE", "TARTRATE", "SUCCINATE", "PROPANEDIOL", "DIPROPIONATE",
    "BESYLATE", "TOSYLATE", "HYDROBROMIDE", "MONOHYDRATE", "DIHYDRATE",
    "HEMIFUMARATE", "BITARTRATE", "PAMOATE", "XINAFOATE", "DISOPROXIL",
    "ETEXILATE", "ALAFENAMIDE", "TROMETHAMINE", "OROTATE", "CHLORIDE",
    "DIMALEATE", "AND", "MONOHYDROCHLORIDE", "ANHYDROUS",
    "ESYLATE", "ERBUMINE", "HUMAN", "HUM", "REC", "ANLOG", "ANALOG", "CF",
}
_SUFFIX_TAGS = re.compile(
    r"\b(ER|XR|SR|CR|LA|HFA|ODT|DR|PHARM|PACK|KIT|"
    r"INJECTION|TABLET|CAPSULE|SOLUTION|SUSPENSION)\b",
    re.I,
)


def normalize_name(name: Optional[str]) -> str:
    """Uppercase, drop salts/forms/punctuation -> canonical token for matching."""
    if not name:
        return ""
    s = name.upper()
    s = _SUFFIX_TAGS.sub(" ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    tokens = [t for t in s.split() if t and t not in _SALTS and not t.isdigit()]
    return " ".join(tokens).strip()


def ingredient_tokens(generic: str) -> List[str]:
    """Split a (possibly combination) generic name into normalized ingredients."""
    parts = re.split(r"[;/,+]| AND ", generic.upper())
    out: List[str] = []
    for p in parts:
        n = normalize_name(p)
        if n:
            out.append(n)
    return out


def ingredient_set(generic: str) -> frozenset:
    return frozenset(ingredient_tokens(generic))
