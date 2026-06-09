"""Single entrypoint: reproduce the entire Innovation Clock package end to end.

    python -m src.run_all                # full pipeline (offline from cached raw)
    python -m src.run_all --refresh      # ignore cache and refetch everything
    python -m src.run_all --no-orphan    # skip the orphan enrichment layer

Stages: build dataset -> analyze -> charts -> dashboard -> fact sheet, then
print a run summary (headline stats, resolved/unresolved drugs, data gaps, and
any human actions required).
"""
from __future__ import annotations

import argparse
import json

from . import util, build_dataset, analyze, charts, dashboard, factsheet


def _b(x):
    return f"${x/1e9:.1f}B" if x else "n/a"


def main():
    ap = argparse.ArgumentParser(description="Build the Innovation Clock package.")
    ap.add_argument("--refresh", action="store_true", help="ignore cache, refetch all raw data")
    ap.add_argument("--no-orphan", action="store_true", help="skip orphan enrichment")
    ap.add_argument("--top-n", type=int, default=50, help="top-N Part D drugs to union into the cohort")
    args = ap.parse_args()

    if args.refresh:
        import shutil
        for p in (util.RAW_FDA, util.RAW_CMS, util.RAW_ORPHAN):
            shutil.rmtree(p, ignore_errors=True)
            p.mkdir(parents=True, exist_ok=True)
        print("[refresh] cleared raw caches; will refetch.\n")

    print("=" * 70)
    print("THE INNOVATION CLOCK — full pipeline")
    print("=" * 70)

    print("\n[1/5] Building dataset (FDA + CMS + orphan)...")
    ds = build_dataset.run(top_n=args.top_n, with_orphan=not args.no_orphan)

    print("\n[2/5] Analyzing...")
    stats = analyze.run()

    print("\n[3/5] Rendering charts...")
    charts.run()

    print("\n[4/5] Building dashboard...")
    dashboard.run()

    print("\n[5/5] Building fact sheet...")
    fs = factsheet.run()

    _summary(ds, stats, fs)


def _summary(ds, s, fs):
    print("\n" + "=" * 70)
    print("RUN SUMMARY")
    print("=" * 70)

    mc = s["modality_counts"]
    print(f"\nHEADLINE STATISTICS ({s['spend_year']} Medicare spend) — canonical cohort = {s['n_negotiated']} IRA-negotiated drugs:")
    print(f"  • Modality split: {mc.get('small molecule',0)} small molecule + {mc.get('biologic',0)} biologic "
          f"(broader top-50 union = {s['n_union']} drugs, context only).")
    print(f"  • {s['sm_in_window_count']} of {s['sm_negotiated']} negotiated small-molecule DRUGS "
          f"gained a new indication in the yr 7-9 window.")
    print(f"  • {s['pct_all_after_clock']}% of new INDICATIONS ({s['n_events']} events) were approved AFTER the negotiation clock.")
    sm = s["distribution"].get("small molecule", {}); bio = s["distribution"].get("biologic", {})
    print(f"  • % indications after clock: small molecule {sm.get('pct_after_clock')}%, biologic {bio.get('pct_after_clock')}%.")
    print(f"  • Negotiated-cohort Medicare spend: {_b(s['negotiated_total_spend'])} "
          f"(our aggregation of CMS Spending-by-Drug data; broader union {_b(s['union_total_spend'])}).")
    print(f"  • Orphan: {s['negotiated_with_orphan']} negotiated drugs have >=1 orphan indication; "
          f"{s['serial_orphan_strict_count']} are strict serial-orphan ({', '.join(s['serial_orphan_strict']) or 'none'}).")
    ebc = {int(k): v for k, v in s["epic_by_cycle"].items()}
    print(f"  • EPIC 11-yr rule (small molecules only) would block {s['epic_blocked_count']} of {s['epic_sm_total']} "
          f"negotiated small molecules ({_b(s['epic_blocked_spend'])}): "
          f"Cyc1 {ebc[1]['blocked']}/{ebc[1]['n_sm']}, Cyc2 {ebc[2]['blocked']}/{ebc[2]['n_sm']}, Cyc3 {ebc[3]['blocked']}/{ebc[3]['n_sm']}.")

    print(f"\nDRUG RESOLUTION: all {s['n_resolved']}/{s['n_negotiated']} negotiated drugs resolved "
          f"({s['n_union_unresolved']} unresolved in the broader {s['n_union']}-drug union).")
    if ds["unresolved"]:
        for u in ds["unresolved"]:
            print(f"  • UNRESOLVED: {u}")

    print("\nDATA GAPS / CAVEATS (documented in docs/METHODOLOGY.md):")
    print("  • Cycle 3 (IPAY 2028) Maximum Fair Prices are not yet published (mfp_usd = null). Not invented.")
    print("  • 'New indications' = FDA efficacy supplements (a proxy; includes some population/line expansions).")
    print("  • 2 vaccine entries (Arexvy, Shingrix) unresolved: CMS antigen names don't map to FDA ingredients.")
    print("  • Xolair Part B classification is contested (CMS published no official Part B/D split; analysts differ); flagged in cohort.py.")
    print("  • Insulin aspart (NovoLog) resolves as a biologic due to FDA's 2020 insulin BLA transition.")
    print("  • Strict serial-orphan is a label-text heuristic (real OOPD data underneath). Industry figures")
    print("    (PhRMA/PHAR, Univ. of Chicago) are industry-sourced; KFF and NPC/Patterson are independent — all cited.")
    if not s.get("orphan_status_known"):
        print("  • Orphan data unavailable this run -> orphan_status='unknown'. Re-run with network for OOPD.")

    print("\nOUTPUTS:")
    for p in [build_dataset.MASTER_CSV, build_dataset.SUMMARY_CSV,
              analyze.FINDINGS, util.ROOT / "dashboard/index.html",
              factsheet.PDF_OUT, factsheet.UPLOAD_PDF]:
        exists = "OK " if p.exists() else "MISSING"
        print(f"  [{exists}] {p.relative_to(util.ROOT)}")
    if not fs.get("pdf"):
        print("  [note] PDF not rendered. Run: python -m playwright install chromium")
    print(f"\n  >> UPLOAD DELIVERABLE (5-page, single file): "
          f"{factsheet.UPLOAD_PDF.relative_to(util.ROOT)}")

    # Placeholders / unverified items the user must resolve before sharing
    ph = fs.get("warnings") or []
    print("\nPLACEHOLDERS / ACTIONS BEFORE SHARING:")
    if ph:
        for w in ph:
            print(f"  • {w}")
    else:
        print("  • none — appendix links and dashboard screenshot all rendered.")
    print(f"  • Live links in the deliverable:")
    print(f"      dashboard: {fs.get('dashboard_url')}")
    print(f"      repo:      {fs.get('repo_url')}")

    print("\nHUMAN ACTIONS:")
    print("  • Repo is public; dashboard is hosted on GitHub Pages (main / root, root redirects to dashboard/).")
    print("  • To update after changes: git add -A && git commit -m '...' && git push")
    print("\nDone.")


if __name__ == "__main__":
    main()
