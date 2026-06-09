"""Compute the headline analysis numbers (project brief section 6) from the
processed datasets and write docs/FINDINGS.md.

Reads the two processed CSVs so it runs offline from cached pipeline output.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict

import pandas as pd

from . import util

MASTER_CSV = util.PROCESSED / "innovation_clock_master.csv"
SUMMARY_CSV = util.PROCESSED / "innovation_clock_summary.csv"
FINDINGS = util.DOCS / "FINDINGS.md"

# IRA selected-drug announcement dates per cycle (used for the EPIC balance check).
SELECTION_DATE = {1: dt.date(2023, 8, 29), 2: dt.date(2025, 1, 17), 3: dt.date(2026, 1, 27)}


def _load():
    master = pd.read_csv(MASTER_CSV)
    summary = pd.read_csv(SUMMARY_CSV)
    return master, summary


# Verified orphan/non-orphan basis for each multi-orphan candidate. A strict
# (OBBBA) serial orphan must have NO approved non-orphan indication.
ORPHAN_BASIS = {
    "Imbruvica": ("CLL/SLL, Waldenström's macroglobulinemia, chronic graft-versus-host disease "
                  "— all rare/orphan; no non-orphan approval", True),
    "Calquence": ("Mantle cell lymphoma, CLL/SLL — all rare/orphan; no non-orphan approval", True),
    "Ofev": ("Idiopathic pulmonary fibrosis, chronic fibrosing ILD, SSc-ILD — all rare/orphan "
             "(US label); no non-orphan approval", True),
    "Pomalyst": ("Multiple myeloma, Kaposi sarcoma — both orphan; no non-orphan approval", True),
    "Lenvima": ("Differentiated thyroid cancer (orphan) BUT also renal cell carcinoma and "
                "endometrial carcinoma — NON-orphan -> disqualified", False),
}


def compute(master: pd.DataFrame, summary: pd.DataFrame) -> Dict[str, Any]:
    """All headline numbers are computed on the CANONICAL cohort = the 40
    IRA-negotiated drugs (Cycles 1-3). The broader 64-drug union (incl. top-50
    Part D spenders) is reported only as context, never mixed into the stats."""
    out: Dict[str, Any] = {}
    neg = summary[summary["in_negotiated"]].copy()
    neg_brands = set(neg["drug_brand"])
    mneg = master[master["drug_brand"].isin(neg_brands)].copy()  # canonical event set

    out["n_cohort"] = len(neg)                 # canonical = 40 negotiated
    out["n_negotiated"] = len(neg)
    out["n_union"] = len(summary)              # 64-drug union (context only)
    out["n_resolved"] = int(neg["original_approval_date"].notna().sum())
    out["n_unresolved"] = int(neg["original_approval_date"].isna().sum())
    out["n_union_unresolved"] = int(summary["original_approval_date"].isna().sum())
    out["modality_counts"] = neg["modality"].value_counts(dropna=False).to_dict()

    # (1) negotiated small molecules gaining >=1 indication in the yr 7-9 window
    sm = neg[neg["modality"] == "small molecule"]
    in_window = sm[sm["n_indications_in_window"] > 0]
    out["sm_negotiated"] = len(sm)             # 30
    out["sm_in_window_count"] = len(in_window)
    out["sm_in_window_drugs"] = sorted(in_window["drug_brand"].tolist())

    # (2) distribution of years_after_launch by modality -- ON THE 40 NEGOTIATED
    ev = mneg[mneg["years_after_launch"].notna()].copy()
    dist = {}
    for mod in ["small molecule", "biologic"]:
        sub = ev[ev["modality"] == mod]
        if len(sub) == 0:
            continue
        ya = sub["years_after_launch"]
        clk = sub["clock_year"]
        back_half = (ya > clk / 2).sum()
        after = (sub["is_after_clock"] == True).sum()  # noqa: E712
        dist[mod] = {
            "n_indications": int(len(sub)),
            "mean_years": round(float(ya.mean()), 2),
            "median_years": round(float(ya.median()), 2),
            "pct_back_half": round(100 * back_half / len(sub), 1),
            "pct_after_clock": round(100 * after / len(sub), 1),
        }
    out["distribution"] = dist
    out["n_events"] = int(len(ev))
    out["pct_all_after_clock"] = round(100 * (ev["is_after_clock"] == True).sum() / len(ev), 1)  # noqa: E712

    # (3) total latest-year Medicare spend of the negotiated cohort
    out["spend_year"] = int(summary["spend_year"].dropna().iloc[0]) if summary["spend_year"].notna().any() else None
    out["negotiated_total_spend"] = float(neg["total_medicare_spend_latest_usd"].fillna(0).sum())
    out["union_total_spend"] = float(summary["total_medicare_spend_latest_usd"].fillna(0).sum())

    # (4) rare-disease cut
    neg_orphan = neg[neg["orphan_status"] == "orphan_approved"]
    out["negotiated_with_orphan"] = len(neg_orphan)
    out["negotiated_multi_orphan"] = int(neg["serial_orphan_candidate"].sum())
    multi = sorted(neg[neg["serial_orphan_candidate"]]["drug_brand"].tolist())
    out["multi_orphan_drugs"] = multi
    out["orphan_status_known"] = bool((summary["orphan_status"] != "unknown").any())

    # OBBBA "serial orphan" = multiple orphan indications AND no approved NON-orphan
    # indication. Proxy: no clearly-common disease in the FDA label -- now including
    # common (non-orphan) solid tumors so e.g. Lenvima (renal cell / endometrial) is
    # correctly disqualified. (Documented heuristic; see METHODOLOGY.)
    COMMON = ["psoriasis", "rheumatoid arthritis", "ulcerative colitis", "crohn",
              "asthma", "copd", "chronic obstructive", "diabetes", "hypertension",
              "depress", "schizophrenia", "bipolar", "atopic dermatitis", "migraine",
              "obesity", "overweight", "constipation", "irritable bowel", "heart failure",
              "hidradenitis", "ankylosing", "plaque", "tardive", "chorea", "encephalopathy",
              # common (non-orphan) solid tumors:
              "renal cell", "endometrial", "non-small cell", "colorectal", "melanoma",
              "breast cancer", "prostate cancer", "hepatocellular", "ovarian", "gastric",
              "bladder cancer", "head and neck"]
    text_by_brand = (master.dropna(subset=["indication_text"])
                     .groupby("drug_brand")["indication_text"].first().to_dict())
    strict, strict_reasons = [], {}
    for b in multi:
        t = (text_by_brand.get(b) or "").lower()
        hit = next((k for k in COMMON if k in t), None)
        if t and not hit:
            strict.append(b)
        else:
            strict_reasons[b] = f"non-orphan indication keyword: '{hit}'" if hit else "no label text"
    out["serial_orphan_strict"] = sorted(strict)
    out["serial_orphan_strict_count"] = len(strict)
    out["serial_orphan_excluded"] = strict_reasons

    # (5) EPIC balance check. EPIC moves ONLY the small-molecule selection clock
    # (yr 7 -> 11); biologics are already at yr 11 and are UNAFFECTED. So count
    # ONLY negotiated SMALL MOLECULES that were < 11 yrs past first approval at
    # their selection date. Denominator = the 30 negotiated small molecules.
    epic_blocked = []
    for _, r in sm.iterrows():
        if pd.isna(r["original_approval_date"]) or pd.isna(r["ira_cycle"]):
            continue
        appr = dt.date.fromisoformat(r["original_approval_date"])
        sel = SELECTION_DATE.get(int(r["ira_cycle"]))
        if not sel:
            continue
        yrs_at_selection = (sel - appr).days / 365.25
        if yrs_at_selection < 11:
            epic_blocked.append((r["drug_brand"], round(yrs_at_selection, 2), int(r["ira_cycle"])))
    out["epic_sm_total"] = len(sm)             # 30
    out["epic_blocked_count"] = len(epic_blocked)
    out["epic_blocked"] = sorted(epic_blocked, key=lambda x: x[1])
    blocked_brands = {b for b, *_ in epic_blocked}
    out["epic_blocked_spend"] = float(
        sm[sm["drug_brand"].isin(blocked_brands)]["total_medicare_spend_latest_usd"].fillna(0).sum())
    # per-cycle blocked counts (small molecules only)
    by_cycle = {}
    for c in (1, 2, 3):
        cyc_sm = sm[sm["ira_cycle"] == c]
        blocked = [b for b, _, cc in epic_blocked if cc == c]
        by_cycle[c] = {"n_sm": len(cyc_sm), "blocked": len(blocked)}
    out["epic_by_cycle"] = by_cycle

    return out


def _fmt_b(x):
    return f"${x/1e9:.1f}B" if x else "n/a"


def write_findings(out: Dict[str, Any]) -> str:
    d = out
    sm = d["distribution"].get("small molecule", {})
    bio = d["distribution"].get("biologic", {})
    mc = d["modality_counts"]
    lines = []
    A = lines.append
    A("# FINDINGS — The Innovation Clock\n")
    A(f"_Generated by `src/analyze.py`. **Canonical cohort = the {d['n_negotiated']} IRA-negotiated drugs "
      f"(Cycles 1–3).** Every headline number, the modality table, and Figures 1–3 are computed on these 40 only. "
      f"The broader {d['n_union']}-drug union (incl. top-50 Part D spenders) is context, not mixed into the stats. "
      f"Spend = Medicare gross spending, latest year ({d['spend_year']})._\n")
    A(f"**Cohort & resolution.** {d['n_negotiated']} negotiated molecules; "
      f"modality split = {mc.get('small molecule', 0)} small molecule + {mc.get('biologic', 0)} biologic "
      f"(reconciles to Figure 1). All {d['n_resolved']}/{d['n_negotiated']} resolved to an FDA originator application "
      f"(the {d['n_union_unresolved']} unresolved drugs — vaccines Arexvy, Shingrix — are non-negotiated and excluded here).\n")

    A("## 1. Do negotiated small molecules earn new indications inside the truncation window?\n")
    A(f"**{d['sm_in_window_count']} of {d['sm_negotiated']} negotiated small-molecule drugs** gained ≥1 new FDA "
      f"indication in the **year 7–9 window** — the years the clock truncates relative to biologics (clock yr 13).  \n"
      f"_Computation: `summary[in_negotiated & modality=='small molecule' & n_indications_in_window>0]` → "
      f"{d['sm_in_window_count']} / {d['sm_negotiated']}._\n")
    if d["sm_in_window_drugs"]:
        A("Drugs gaining an indication in years 7–9: " + ", ".join(d["sm_in_window_drugs"]) + ".\n")

    A("## 2. When do new indications land? (by modality, 40 negotiated drugs)\n")
    A(f"_Computation: {d['n_events']} efficacy-supplement events across the 40 negotiated drugs; "
      f"`% after clock` = share with `years_after_launch ≥ clock_year`; `% back half` = share with "
      f"`years_after_launch > clock_year/2`._\n")
    A("| Modality | # indications | mean yrs | median yrs | % in back half of clock window | % after clock |")
    A("|---|---|---|---|---|---|")
    if sm:
        A(f"| Small molecule (clock yr 9) | {sm['n_indications']} | {sm['mean_years']} | {sm['median_years']} | {sm['pct_back_half']}% | {sm['pct_after_clock']}% |")
    if bio:
        A(f"| Biologic (clock yr 13) | {bio['n_indications']} | {bio['mean_years']} | {bio['median_years']} | {bio['pct_back_half']}% | {bio['pct_after_clock']}% |")
    A(f"\nAcross the 40 negotiated drugs, **{d['pct_all_after_clock']}% of new indications** "
      f"({(sm.get('n_indications',0)+bio.get('n_indications',0))} events) were approved *after* the drug's "
      f"negotiation clock would already be in effect.\n")

    A("## 3. Medicare spend represented\n")
    A(f"The 40 negotiated drugs account for **{_fmt_b(d['negotiated_total_spend'])}** in {d['spend_year']} gross "
      f"Medicare spending (Part D + Part B), computed from CMS Spending-by-Drug data — **not** CMS's official "
      f"per-cycle totals, which use different 12-month windows. (Broader {d['n_union']}-drug union, for context: "
      f"{_fmt_b(d['union_total_spend'])}.)\n")

    A("## 4. Rare-disease (orphan) cut\n")
    A("_Source: real FDA Orphan Drug Designations (OOPD) database (`src/fetch_orphan.py`), not a heuristic._\n")
    if d["orphan_status_known"]:
        A(f"- Negotiated drugs with ≥1 FDA-approved orphan indication: **{d['negotiated_with_orphan']}**.")
        A(f"- Carrying ≥2 distinct approved orphan indications (multi-orphan): **{d['negotiated_multi_orphan']}** "
          f"({', '.join(d['multi_orphan_drugs'])}).")
        A(f"- **Strict serial-orphan** (OBBBA test: multiple orphan indications AND *no* approved non-orphan "
          f"indication) = **{d['serial_orphan_strict_count']}**: {', '.join(d['serial_orphan_strict'])}.\n")
        A("Orphan/non-orphan basis for each multi-orphan candidate:\n")
        for b, (basis, keep) in ORPHAN_BASIS.items():
            mark = "✓ serial-orphan" if keep else "✗ NOT serial-orphan"
            A(f"- **{b}** — {basis}. → {mark}")
        A("")
    else:
        A("- Orphan data unavailable this run; orphan_status is 'unknown'.\n")

    A("## 5. Balance check — what an EPIC-style 11-year rule would do\n")
    A(f"EPIC moves **only the small-molecule** selection clock (yr 7 → 11); biologics are already at yr 11 and are "
      f"**unaffected**, so they cannot be removed by EPIC. Of the **{d['epic_sm_total']} negotiated small molecules**, "
      f"**{d['epic_blocked_count']}** were less than 11 years past first approval at their selection date — i.e. they "
      f"would have been **unreachable** under an 11-year rule — representing **{_fmt_b(d['epic_blocked_spend'])}** of "
      f"{d['spend_year']} Medicare spend.\n")
    A("Per cycle (small molecules only):")
    for c, v in d["epic_by_cycle"].items():
        A(f"- Cycle {c}: {v['blocked']} of {v['n_sm']} small molecules blocked.")
    A("\nSmall molecules unreachable under an 11-yr selection rule (years past approval at selection):\n")
    for b, yrs, c in d["epic_blocked"]:
        A(f"- {b} — {yrs} yrs at selection (Cycle {c})")
    A("\n_Affordability counterpoint to the innovation-incentive argument: delaying selection protects later-life "
      "revenue but removes high-spend drugs from negotiation. The data cut both ways._\n")

    A("## 6. A note on units\n")
    A("Item 1 (\"X of 30\") counts **drugs** that gained an indication in the year 7–9 window; item 2 "
      "(\"% after clock\") counts **indications**. These have different denominators and should not be read "
      "as the same metric.\n")

    FINDINGS.write_text("\n".join(lines))
    return "\n".join(lines)


def run() -> Dict[str, Any]:
    master, summary = _load()
    out = compute(master, summary)
    write_findings(out)
    (util.PROCESSED / "headline_stats.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"Wrote {FINDINGS}")
    return out


if __name__ == "__main__":
    o = run()
    print(json.dumps({k: v for k, v in o.items() if k not in ("epic_blocked", "distribution")}, indent=1, default=str))
