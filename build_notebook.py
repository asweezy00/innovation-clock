"""Build (and the caller executes) notebooks/innovation_clock.ipynb — a single
notebook that shows the code, the data, the inline plots, and the results summary
together. Reuses the cached pipeline data so it runs offline in seconds.
"""
import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

cells = []
md = lambda s: cells.append(new_markdown_cell(s))
co = lambda s: cells.append(new_code_cell(s))

md("""# The Innovation Clock — code, analysis & results in one place

**When do America's most expensive Medicare drugs earn their clinical value — and how does that timing collide with the Inflation Reduction Act's price-negotiation deadline?**

This notebook reproduces the whole analysis end-to-end from cached public data (FDA Drugs@FDA, CMS Medicare spending, CMS negotiation fact sheets, FDA orphan designations). Every section shows the code *and* its output — tables, inline plots, and the results summary.

**The clock (current law, 2026):** a small-molecule drug (FDA **NDA**) can have its Medicare price negotiated starting **year 9** after approval; a biologic (**BLA**) is shielded until **year 13**. That 4-year gap is the contested *"pill penalty."*
""")

md("## 0 · Setup")
co("""import os, sys, json, inspect, datetime as dt
# run from the repo root so `import src...` and the cached data resolve
if os.path.basename(os.getcwd()) == "notebooks":
    os.chdir("..")
sys.path.insert(0, os.getcwd())

import pandas as pd
import matplotlib.pyplot as plt
%matplotlib inline
pd.set_option("display.max_columns", 40)
pd.set_option("display.width", 160)

from src import util, fetch_fda, cohort, analyze

# restrained policy-report palette (matches the dashboard + fact sheet)
C_SM, C_BIO, C_CLOCK, C_AFTER = "#1b6ca8", "#d4761f", "#444444", "#e8b4b8"
color = lambda m: C_BIO if m == "biologic" else C_SM

# load the processed pipeline outputs
master  = pd.read_csv(util.PROCESSED / "innovation_clock_master.csv")
summary = pd.read_csv(util.PROCESSED / "innovation_clock_summary.csv")
payload = json.loads((util.PROCESSED / "dashboard_data.json").read_text())
policy  = json.loads((util.RAW / "policy_facts.json").read_text())

print("master rows :", len(master))
print("summary rows:", len(summary))
print("drugs (json):", len(payload["drugs"]), "| spend year:", payload["spend_year"])""")

md("""## 1 · The cohort

The cohort is the **union** of (A) the IRA negotiation Cycles 1–3 (40 unique molecules; lists + Maximum Fair Prices are cited constants verified vs CMS/KFF) and (B) the top-50 Medicare Part D drugs by latest-year gross spend.""")
co("""print("Cohort composition")
print("  unique molecules     :", len(summary))
print("  IRA-negotiated       :", int(summary.in_negotiated.sum()))
print("  in top-50 Part D     :", int(summary.in_top_spend.sum()))
print("  by primary IRA cycle :", summary.dropna(subset=['ira_cycle']).groupby('ira_cycle').size().to_dict())
print("  modality split       :", summary.modality.value_counts(dropna=False).to_dict())

# negotiated drugs with their clock, MFP, and spend
neg = (summary[summary.in_negotiated]
       .assign(spend_B=lambda d: (d.total_medicare_spend_latest_usd/1e9).round(2))
       [["drug_brand","drug_generic","modality","clock_year","ira_cycle","mfp_usd","spend_B","orphan_status"]]
       .sort_values(["ira_cycle","modality","drug_brand"]).reset_index(drop=True))
neg""")

md("""## 2 · FDA resolution — the crux

Mapping a brand to the right FDA application is the hard part: openFDA's `openfda` block is empty on many originator NDAs/BLAs, so brand/generic searches *miss the original*. The fix is to search `products.active_ingredients.name`, keep only NDA/BLA originators, anchor **year 0** to the earliest original approval, and read new indications from **efficacy supplements**. Live demo (from cache):""")
co("""for t in [{"brand":"Eliquis","generic":"apixaban"},
          {"brand":"Imbruvica","generic":"ibrutinib"},
          {"brand":"Enbrel","generic":"etanercept"}]:
    r = fetch_fda.build_drug_record(t)
    print(f"{t['brand']:10s} apps={r['matched_app_numbers']}")
    print(f"           anchor={r['anchor_app']} @ {r['anchor_date']} -> {r['modality']} (clock yr {r['clock_year']}), "
          f"{len(r['events'])} new-indication events")
    print("           first events:", [(str(e['date']), e['years_after_launch']) for e in r['events'][:3]])
print("\\nNote: Imbruvica anchors to the 2013 ORIGINAL (NDA205552), not its 2022 reformulation — the reformulation trap the resolver avoids.")""")
co("""# the resolver itself
print(inspect.getsource(fetch_fda.resolve_apps))""")

md("""## 3 · The processed datasets

`innovation_clock_master.csv` is **long** (one row per drug × indication event); `innovation_clock_summary.csv` is **wide** (one row per drug).""")
co("""print("MASTER (long) — one row per drug x indication event")
master.head(6)""")
co("""print("SUMMARY (wide) — one row per drug")
summary.head(6)""")

md("## 4 · Headline analysis")
co("""stats = analyze.compute(master, summary)
sm, bio = stats["distribution"]["small molecule"], stats["distribution"]["biologic"]

print(f"Cohort: {stats['n_cohort']} molecules ({stats['n_negotiated']} negotiated) | spend year {stats['spend_year']}")
print(f"Resolved {stats['n_resolved']} / unresolved {stats['n_unresolved']}\\n")
print(f"1) Negotiated small molecules gaining an indication in the yr 7-9 window: "
      f"{stats['sm_in_window_count']} of {stats['sm_negotiated']}")
print(f"2) % of new indications approved AFTER the clock: small molecule {sm['pct_after_clock']}%, "
      f"biologic {bio['pct_after_clock']}% (all {stats['pct_all_after_clock']}%)")
print(f"3) Negotiated-cohort Medicare spend: ${stats['negotiated_total_spend']/1e9:.1f}B "
      f"(broader 64-drug union, context only: ${stats['union_total_spend']/1e9:.1f}B)")
print(f"4) Orphan: {stats['negotiated_with_orphan']} negotiated drugs w/ >=1 orphan indication; "
      f"strict serial-orphan = {stats['serial_orphan_strict_count']} {stats['serial_orphan_strict']}")
print(f"5) EPIC 11-yr rule (small molecules only) would block {stats['epic_blocked_count']} of {stats['epic_sm_total']} "
      f"negotiated small molecules (${stats['epic_blocked_spend']/1e9:.1f}B)")

pd.DataFrame([
    {"modality":"small molecule (clock 9)", **sm},
    {"modality":"biologic (clock 13)", **bio},
]).set_index("modality")""")

md("""## 5 · The signature visual — the Innovation Clock

Each lane is an IRA-negotiated drug, from first approval (year 0) to its most recent new indication. Dots are new indications; the diamond is the negotiation clock (yr 9 small molecule / yr 13 biologic); the shaded band is the price-controlled period. Biologics keep earning indications well past where small molecules are already price-controlled.""")
co("""drugs = [d for d in payload["drugs"] if d["modality"] and d["in_negotiated"]]
drugs.sort(key=lambda d: (d["modality"] != "small molecule", d["original_approval_date"]))
yrs = lambda d: [i["years_after_launch"] for i in d["indications"] if i["years_after_launch"] is not None]

n = len(drugs)
fig, ax = plt.subplots(figsize=(9, 0.23*n + 1.2))
xmax = max(max(yrs(d) + [d["clock_year"]]) for d in drugs) + 1  # never clip late indications
n_sm = sum(1 for d in drugs if d["modality"] == "small molecule")
# shade each block's actual price-controlled region (SM from yr 9, biologic from yr 13)
ax.axvspan(9, xmax, ymin=(n - n_sm + 0.5)/(n + 2.6), ymax=(n + 0.5)/(n + 2.6), color=C_AFTER, alpha=0.12)
ax.axvspan(13, xmax, ymin=0.4/(n + 2.6), ymax=(n - n_sm + 0.5)/(n + 2.6), color=C_AFTER, alpha=0.12)
for v, c in [(9, C_SM), (13, C_BIO)]:
    ax.axvline(v, color=c, ls=":", lw=1, alpha=0.7)
for i, d in enumerate(drugs):
    y = n - i
    ax.plot([0, max(yrs(d) + [d["clock_year"]])], [y, y], color="#ddd", lw=0.8, zorder=1)
    for v in yrs(d):
        after = v >= d["clock_year"]
        ax.scatter(v, y, s=24, color=color(d["modality"]),
                   edgecolor=(C_CLOCK if after else "none"), lw=0.7,
                   alpha=0.95 if after else 0.7, zorder=4)
    ax.scatter(d["clock_year"], y, s=42, marker="d", color=C_CLOCK, zorder=5)
    ax.text(-0.4, y, d["brand"], ha="right", va="center", fontsize=7)
ax.text(9, n+1.2, "clock yr 9", color=C_SM, fontsize=8, ha="center")
ax.text(13, n+2.0, "clock yr 13", color=C_BIO, fontsize=8, ha="center")
ax.set(xlim=(0, xmax), ylim=(0, n+2.6), yticks=[], xlabel="Years after first FDA approval")
ax.set_title("The Innovation Clock: new indications vs. the Medicare negotiation deadline", loc="left")
for s in ("top","right","left"): ax.spines[s].set_visible(False)
plt.tight_layout(); plt.show()""")

md("## 6 · Spend vs. how long a drug keeps earning new indications")
co("""fig, ax = plt.subplots(figsize=(9, 5.2))
for mod, c in (("small molecule", C_SM), ("biologic", C_BIO)):
    pts = [(max(yrs(d) + [0]), d["total_spend"]/1e9, d) for d in payload["drugs"]
           if d["modality"] == mod and d["total_spend"] and d["in_negotiated"]]  # 40 negotiated
    ax.scatter([p[0] for p in pts], [p[1] for p in pts],
               s=[50 if p[2]["in_negotiated"] else 28 for p in pts],
               color=c, alpha=0.7, edgecolor="white", lw=0.6, label=mod)
    for x, yv, d in sorted(pts, key=lambda t: -t[1])[:6]:
        ax.annotate(d["brand"], (x, yv), fontsize=7, xytext=(3,3), textcoords="offset points")
for v, c in [(9, C_SM), (13, C_BIO)]: ax.axvline(v, color=c, ls=":", lw=1, alpha=0.6)
ax.set_yscale("log")
ax.set(xlabel="Years from approval to most recent new indication",
       ylabel="Latest-year Medicare spend ($B, log scale)")
ax.set_title("Spend vs. indication longevity, by modality", loc="left")
ax.legend(frameon=False); ax.grid(axis="y", color="#eee")
for s in ("top","right"): ax.spines[s].set_visible(False)
plt.tight_layout(); plt.show()""")

md("## 7 · When new indications are approved (distribution)")
co("""fig, ax = plt.subplots(figsize=(9, 4.2))
all_vals = [v for d in payload["drugs"] if d["modality"] and d["in_negotiated"] for v in yrs(d)]
bins = range(0, int(max(all_vals)) + 2)  # extend past the oldest event so no indication is dropped
for mod, c in (("small molecule", C_SM), ("biologic", C_BIO)):
    vals = [v for d in payload["drugs"] if d["modality"] == mod and d["in_negotiated"] for v in yrs(d)]
    ax.hist(vals, bins=bins, color=c, alpha=0.55, label=f"{mod} (n={len(vals)})")
ax.axvline(9, color=C_SM, ls=":", lw=1.3); ax.axvline(13, color=C_BIO, ls=":", lw=1.3)
ax.set(xlabel="Years after approval that a new indication was granted", ylabel="# new indications")
ax.set_title("When new indications land, by modality", loc="left")
ax.legend(frameon=False)
for s in ("top","right"): ax.spines[s].set_visible(False)
plt.tight_layout(); plt.show()""")

md("""## 8 · Balance check — what an EPIC-style 11-year rule would do

The EPIC Act would push **small-molecule** *selection* from year 7 to year 11. Biologics already sit at year 11, so EPIC cannot remove them — the counterfactual is small-molecule-only. Of the **30 negotiated small molecules**, those < 11 years past approval at selection would become **unreachable** (Public Citizen's published "5 of the first 10, 8 of the next 15" counts all selected drugs; the blocked ones are the small molecules).  """)
co("""ebc = {int(k): v for k, v in stats["epic_by_cycle"].items()}
fig, ax = plt.subplots(figsize=(7, 3.6))
cyc = [1, 2, 3]
tot = [ebc[c]["n_sm"] for c in cyc]      # negotiated SMALL MOLECULES per cycle
blk = [ebc[c]["blocked"] for c in cyc]
ax.bar(cyc, tot, color="#dfe7ee", label="negotiated small molecules")
ax.bar(cyc, blk, color=C_SM, label="blocked under 11-yr rule")
for c in cyc:
    ax.text(c, ebc[c]["blocked"]+0.2, f"{ebc[c]['blocked']}/{ebc[c]['n_sm']}", ha="center", fontsize=10, color=C_CLOCK)
ax.set(xticks=cyc, xticklabels=[f"Cycle {c}" for c in cyc], ylabel="# small molecules")
ax.set_title(f"EPIC 11-yr rule (small molecules only): {stats['epic_blocked_count']} of {stats['epic_sm_total']} blocked "
             f"(${stats['epic_blocked_spend']/1e9:.1f}B)", loc="left")
ax.legend(frameon=False)
for s in ("top","right"): ax.spines[s].set_visible(False)
plt.tight_layout(); plt.show()

print("Small molecules unreachable under an 11-yr selection rule (years past approval at selection):")
pd.DataFrame(stats["epic_blocked"], columns=["drug","yrs_at_selection","cycle"])""")

md("## 9 · Rare-disease (orphan) cut")
co("""orph = (summary[summary.in_negotiated & (summary.orphan_status != "none")]
        [["drug_brand","modality","orphan_status","serial_orphan_candidate",
          "n_orphan_indications_approved","ira_cycle"]]
        .sort_values(["serial_orphan_candidate","n_orphan_indications_approved"], ascending=False)
        .reset_index(drop=True))
print(f"Negotiated drugs with >=1 approved orphan indication: {stats['negotiated_with_orphan']}")
print(f"Multi-orphan (>=2 distinct): {stats['negotiated_multi_orphan']}")
print(f"Strict serial-orphan (no non-orphan approval -> OBBBA-exempt): {stats['serial_orphan_strict']}")
orph""")

md("""## 10 · Results summary — the data cut both ways

**What the data shows**
- Pills *do* keep earning clinical value as the clock closes — most negotiated small molecules gained a new indication in their yr 7–9 window.
- Biologics keep approving new uses far longer, well past year 13.
- The negotiated cohort is a very large slice of Medicare spending — real, immediate savings at stake.
- An EPIC-style delay would have pulled ~half of these drugs out of negotiation.

**What remains contested**
- *Industry (PhRMA):* the pill penalty discourages post-approval research; many cancer-drug indications come 7+ years out.
- *Critics (Public Citizen):* call it a "myth" — small-molecule investment hasn't fallen since the program passed.
- *Independent (KFF):* for 2005–2009 small molecules, the 4-year gap was worth ~a third of first-13-year revenue.

The same dataset supports both readings — which is exactly why the policy fight is live.""")
co("""print("CITED POLICY FACTS (both sides) — statement [source]\\n")
for f in policy["facts"]:
    print(f"• [{f['topic']}] {f['statement']}")
    print(f"    — {f['source_org']} ({f.get('source_date','')}) {f['source_url']}\\n")""")

md("""## 11 · The other deliverables

- **Interactive dashboard:** `dashboard/index.html` (self-contained D3 — pick any drug, or "Compare all").
- **Fact sheet:** `factsheet/factsheet.pdf` (~3 pages, both charts, balanced framing, cited sources).
- **Reproduce everything:** `python -m src.run_all` (offline from cached raw data).

Previews below.""")
co("""from IPython.display import Image, display
for p in ["docs/img/dashboard_single.png", "docs/img/factsheet_p1.png"]:
    if os.path.exists(p):
        display(Image(filename=p, width=760))""")

nb = new_notebook(cells=cells, metadata={
    "kernelspec": {"name": "innovation-clock", "display_name": "Python (innovation-clock)", "language": "python"},
    "language_info": {"name": "python"},
})
import os
os.makedirs("notebooks", exist_ok=True)
nbf.write(nb, "notebooks/innovation_clock.ipynb")
print("wrote notebooks/innovation_clock.ipynb with", len(cells), "cells")
