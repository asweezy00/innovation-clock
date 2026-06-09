"""Assemble the cohort into the two processed datasets.

Outputs:
  data/processed/innovation_clock_master.csv  -- LONG: one row per (drug x
      indication event). Drugs with zero efficacy supplements get a single row
      with null event fields so they are not lost.
  data/processed/innovation_clock_summary.csv -- WIDE: one row per drug.

Also writes data/processed/dashboard_data.json (consumed by charts + dashboard)
and prints sanity-check warnings.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd

from . import util, cohort, fetch_fda, fetch_cms, fetch_orphan

MASTER_CSV = util.PROCESSED / "innovation_clock_master.csv"
SUMMARY_CSV = util.PROCESSED / "innovation_clock_summary.csv"
JSON_OUT = util.PROCESSED / "dashboard_data.json"


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def assemble(top_n: int = 50, with_orphan: bool = True,
             with_indication_text: bool = True) -> Dict[str, Any]:
    drugs = cohort.build_cohort(top_n=top_n)
    print(f"Assembling {len(drugs)} cohort drugs...")
    records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    unresolved: List[str] = []

    for i, d in enumerate(drugs, 1):
        brand, generic = d["brand"], d["generic"]
        fda = fetch_fda.build_drug_record({"brand": brand, "generic": generic,
                                           "ingredients": d.get("ingredients")})
        if not fda["anchor_date"]:
            unresolved.append(f"{brand} ({generic})")
            warnings.append(f"[unresolved] {brand}: 0 originator apps / no ORIG-AP date")

        aliases = d.get("aliases")
        part_d = fetch_cms.spend_for(brand, generic, "part_d", aliases=aliases)
        part_b = fetch_cms.spend_for(brand, generic, "part_b", aliases=aliases)
        if part_d is None and d.get("part_d_spend_hint"):
            part_d = d["part_d_spend_hint"]
        total_spend = sum(x for x in (part_d, part_b) if x)

        orphan = {"orphan_status": "unknown", "serial_orphan_candidate": False,
                  "n_orphan_designations": 0, "n_orphan_approved": 0,
                  "n_distinct_orphan_indications_approved": 0}
        if with_orphan:
            try:
                orphan = fetch_orphan.orphan_for({"brand": brand, "generic": generic,
                                                  "ingredients": d.get("ingredients")})
            except Exception as e:  # noqa: BLE001
                warnings.append(f"[orphan] {brand}: {e}")

        indication_text = None
        if with_indication_text:
            try:
                indication_text = fetch_fda.fetch_indication_text({"brand": brand, "generic": generic})
            except Exception:  # noqa: BLE001
                pass

        clock = fda["clock_year"]
        src_urls = "; ".join(filter(None, [
            d.get("source_url"), cohort.SOURCES.get(d.get("ira_cycle"), {}).get("src") if d.get("ira_cycle") else None,
            "https://api.fda.gov/drug/drugsfda.json",
        ]))

        rec = {
            "drug": d, "fda": fda, "orphan": orphan,
            "part_d_spend": part_d, "part_b_spend": part_b, "total_spend": total_spend,
            "indication_text": indication_text, "source_urls": src_urls,
        }
        records.append(rec)

        # sanity: modality must match anchor prefix; approval precedes events
        if fda["anchor_date"]:
            for ev in fda["events"]:
                if ev["date"] < fda["anchor_date"]:
                    warnings.append(f"[sanity] {brand}: event {ev['date']} precedes approval {fda['anchor_date']}")
        if i % 10 == 0:
            print(f"  ...{i}/{len(drugs)}")

    return {"records": records, "warnings": warnings, "unresolved": unresolved,
            "spend_year": 2023}


def _window(clock: Optional[int]):
    return (clock - 2, clock) if clock else (None, None)


def to_frames(assembled: Dict[str, Any]):
    spend_year = assembled["spend_year"]
    master_rows: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    for rec in assembled["records"]:
        d, fda, orphan = rec["drug"], rec["fda"], rec["orphan"]
        clock = fda["clock_year"]
        wlo, whi = _window(clock)
        anchor = fda["anchor_date"]
        events = fda["events"]

        base = {
            "drug_brand": d["brand"], "drug_generic": d["generic"],
            "active_ingredient": "; ".join(d.get("ingredients") or []),
            "fda_application_number": fda["anchor_app"],
            "modality": fda["modality"],
            "original_approval_date": _iso(anchor),
            "clock_year": clock,
            "orphan_status": orphan["orphan_status"],
            "ira_cycle": d.get("ira_cycle"),
            "mfp_usd": d.get("mfp_usd"),
            "part_d_spend_latest_usd": rec["part_d_spend"],
            "part_b_spend_latest_usd": rec["part_b_spend"],
            "spend_year": spend_year,
            "source_urls": rec["source_urls"],
        }

        # LONG rows
        if events:
            for ev in events:
                ya = ev["years_after_launch"]
                master_rows.append({**base,
                    "indication_event_date": _iso(ev["date"]),
                    "years_after_launch": ya,
                    "indication_text": rec["indication_text"],
                    "is_after_clock": (ya >= clock) if (ya is not None and clock) else None,
                    "event_app_number": ev["app_number"],
                })
        else:
            master_rows.append({**base,
                "indication_event_date": None, "years_after_launch": None,
                "indication_text": rec["indication_text"], "is_after_clock": None,
                "event_app_number": None})

        # WIDE row
        yrs = [ev["years_after_launch"] for ev in events if ev["years_after_launch"] is not None]
        n_after = sum(1 for y in yrs if clock and y >= clock)
        n_window = sum(1 for y in yrs if wlo is not None and wlo <= y <= whi)
        last_year = None
        if events and anchor:
            last_year = max(ev["date"].year for ev in events)
        summary_rows.append({
            "drug_brand": d["brand"], "drug_generic": d["generic"],
            "active_ingredient": "; ".join(d.get("ingredients") or []),
            "fda_application_number": fda["anchor_app"],
            "all_app_numbers": "; ".join(fda["matched_app_numbers"]),
            "modality": fda["modality"], "clock_year": clock,
            "original_approval_date": _iso(anchor),
            "ira_cycle": d.get("ira_cycle"),
            "ira_effective_year": d.get("ira_effective_year"),
            "mfp_usd": d.get("mfp_usd"),
            "in_negotiated": d.get("in_negotiated", False),
            "in_top_spend": d.get("in_top_spend", False),
            "cohort_source": d.get("cohort_source"),
            "part": d.get("part"),
            "orphan_status": orphan["orphan_status"],
            "serial_orphan_candidate": orphan.get("serial_orphan_candidate", False),
            "n_orphan_indications_approved": orphan.get("n_distinct_orphan_indications_approved", 0),
            "part_d_spend_latest_usd": rec["part_d_spend"],
            "part_b_spend_latest_usd": rec["part_b_spend"],
            "total_medicare_spend_latest_usd": rec["total_spend"] or None,
            "spend_year": spend_year,
            "n_indications_total": len(events),
            "n_indications_after_clock": n_after,
            "n_indications_in_window": n_window,
            "window_lo_yr": wlo, "window_hi_yr": whi,
            "last_indication_year": last_year,
            "source_urls": rec["source_urls"],
        })

    return pd.DataFrame(master_rows), pd.DataFrame(summary_rows)


def _json_payload(assembled, summary_df) -> Dict[str, Any]:
    drugs = []
    for rec in assembled["records"]:
        d, fda, orphan = rec["drug"], rec["fda"], rec["orphan"]
        drugs.append({
            "brand": d["brand"], "generic": d["generic"],
            "modality": fda["modality"], "clock_year": fda["clock_year"],
            "original_approval_date": _iso(fda["anchor_date"]),
            "application_number": fda["anchor_app"],
            "ira_cycle": d.get("ira_cycle"), "mfp_usd": d.get("mfp_usd"),
            "in_negotiated": d.get("in_negotiated", False),
            "in_top_spend": d.get("in_top_spend", False),
            "orphan_status": orphan["orphan_status"],
            "serial_orphan_candidate": orphan.get("serial_orphan_candidate", False),
            "part_d_spend": rec["part_d_spend"], "part_b_spend": rec["part_b_spend"],
            "total_spend": rec["total_spend"] or None,
            "indications": [
                {"date": _iso(ev["date"]), "years_after_launch": ev["years_after_launch"]}
                for ev in fda["events"]
            ],
        })
    return {"spend_year": assembled["spend_year"], "drugs": drugs}


def run(top_n: int = 50, with_orphan: bool = True) -> Dict[str, Any]:
    assembled = assemble(top_n=top_n, with_orphan=with_orphan)
    master_df, summary_df = to_frames(assembled)
    master_df.to_csv(MASTER_CSV, index=False)
    summary_df.to_csv(SUMMARY_CSV, index=False)
    payload = _json_payload(assembled, summary_df)
    JSON_OUT.write_text(json.dumps(payload, indent=1))
    print(f"\nWrote {MASTER_CSV.name}: {len(master_df)} rows")
    print(f"Wrote {SUMMARY_CSV.name}: {len(summary_df)} rows")
    print(f"Wrote {JSON_OUT.name}: {len(payload['drugs'])} drugs")
    if assembled["unresolved"]:
        print(f"\nUNRESOLVED ({len(assembled['unresolved'])}): {assembled['unresolved']}")
    return {"master": master_df, "summary": summary_df,
            "warnings": assembled["warnings"], "unresolved": assembled["unresolved"],
            "payload": payload}


if __name__ == "__main__":
    out = run()
    print(f"\nWarnings: {len(out['warnings'])}")
    for w in out["warnings"][:30]:
        print("  ", w)
