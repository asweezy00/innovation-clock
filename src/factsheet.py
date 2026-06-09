"""Generate the publication-quality fact sheet (HTML -> PDF) in two forms:
  * factsheet.pdf            — the 3-page fact sheet
  * {OUTPUT_NAME}            — the 5-page upload deliverable (pages 1-3 identical
                              + a 2-page "Data & Methods" / "Reproduce" appendix)

Pulls headline numbers from data/processed/headline_stats.json and policy facts
(with source URLs) from data/raw/policy_facts.json. Figures (and the dashboard
screenshot) are embedded as base64 so the HTML is self-contained; rendered to PDF
with Playwright (Chromium). Set REPO_URL / DASHBOARD_URL below before final render.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Dict

from . import util

FIG_DIR = util.ROOT / "factsheet" / "figures"
HTML_OUT = util.ROOT / "factsheet" / "factsheet.html"
PDF_OUT = util.ROOT / "factsheet" / "factsheet.pdf"
STATS = util.PROCESSED / "headline_stats.json"
POLICY = util.RAW / "policy_facts.json"

# ---- Upload deliverable config (fill before final render) ----
REPO_URL = "https://github.com/asweezy00/innovation-clock"   # public GitHub repo URL
DASHBOARD_URL = "https://asweezy00.github.io/innovation-clock/"  # GitHub Pages (root redirects to dashboard/)
OUTPUT_NAME = "Shahid_Abdullah_Innovation_Clock.pdf"
UPLOAD_PDF = util.ROOT / "factsheet" / OUTPUT_NAME
FULL_HTML = util.ROOT / "factsheet" / "factsheet_full.html"
DASH_SHOT = FIG_DIR / "dashboard_screenshot.png"


def _img(name: str) -> str:
    p = FIG_DIR / name
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def _link(url: str, placeholder_label: str):
    """Return (html, is_placeholder). A TODO/empty url renders a visible chip."""
    if not url or url.strip().lower().startswith("todo"):
        return (f'<span style="background:#fdecea;color:#b3261e;padding:1px 7px;'
                f'border-radius:4px;font-weight:700">[{placeholder_label}]</span>', True)
    return (f'<a href="{url}">{url}</a>', False)


def capture_dashboard_screenshot():
    """Best-effort: render dashboard/index.html headless -> figures/dashboard_screenshot.png.
    Non-blocking: returns the path on success, else None (caller renders a placeholder)."""
    dash = util.ROOT / "dashboard" / "index.html"
    if not dash.exists():
        print("  [warn] dashboard/index.html not found; screenshot skipped")
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] dashboard screenshot skipped (playwright unavailable): {e}")
        return None
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1200, "height": 820})
            pg.goto(f"file://{dash}")
            pg.wait_for_timeout(2500)            # let D3 load from CDN + render
            try:
                pg.select_option("#drug", "Imbruvica")
                pg.wait_for_timeout(700)
            except Exception:  # noqa: BLE001
                pass
            pg.screenshot(path=str(DASH_SHOT))
            b.close()
        print(f"  Captured dashboard screenshot -> {DASH_SHOT.name}")
        return DASH_SHOT
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] dashboard screenshot failed: {e}")
        return None


def _b(x):
    return f"${x/1e9:.1f}B" if x else "n/a"


def _fact(facts, topic_contains):
    for f in facts:
        if topic_contains.lower() in f["topic"].lower():
            return f
    return {}


def _appendix_html(warnings: list) -> str:
    """Two appendix pages (4-5) reusing the existing CSS classes. Exact copy per spec."""
    repo_html, repo_ph = _link(REPO_URL, "add repo link")
    dash_html, dash_ph = _link(DASHBOARD_URL, "add dashboard link")
    if repo_ph:
        warnings.append("REPO_URL is still TODO — rendered '[add repo link]' placeholder")
    if dash_ph:
        warnings.append("DASHBOARD_URL is still TODO — rendered '[add dashboard link]' placeholder")
    shot = _img("dashboard_screenshot.png")
    if shot:
        shot_html = f'<img class="fig" src="{shot}" style="max-width:96%"/>'
    else:
        shot_html = ('<div class="box" style="text-align:center;color:#b3261e;'
                     'padding:48px 10px;font-weight:700">[dashboard screenshot]</div>')
        warnings.append("dashboard screenshot unavailable — rendered '[dashboard screenshot]' placeholder")

    return f"""
<section class="pagebreak">
  <div class="eyebrow">Appendix A · Data &amp; Methods</div>
  <h2 class="kicker" style="border:none;font-size:17px;margin:2px 0 1px">Data &amp; Methods</h2>
  <p class="dek" style="margin-bottom:9px"><i>How this was built — and the data-cleaning decisions behind every number.</i></p>

  <p style="margin:0 0 9px"><b>Sources.</b> FDA Drugs@FDA via openFDA (approval dates; application type, where NDA = small
  molecule and BLA = biologic; and efficacy supplements as the new-indication signal); CMS Medicare Part&nbsp;D and Part&nbsp;B
  Spending by Drug (latest-year, 2023, gross spend); FDA Orphan Drug Designations (OOPD); and CMS's published negotiated-drug
  lists and Maximum Fair Prices.</p>

  <div class="box">
    <h3>What "cleaning" actually meant here</h3>
    <ul>
      <li>openFDA's brand/generic index is empty on many originator applications — a brand search for "Eliquis" returns nothing.
      Resolution keys off active-ingredient tokens, unions the results, and keeps only NDA/BLA originator applications
      (dropping ANDA generics).</li>
      <li>Drugs carry multiple applications (reformulations). Year&nbsp;0 is anchored to the earliest original approval,
      defeating the trap of a 2022 reformulation masquerading as the launch (e.g., Imbruvica's true 2013 approval).</li>
      <li>New indications = approved FDA efficacy supplements, deduplicated by date across each molecule's applications —
      a documented proxy that captures most new-disease approvals but can include some line/population expansions.</li>
      <li>Part&nbsp;B carries no manufacturer column (it is HCPCS-coded), so a drug's Part&nbsp;B spend is summed across its
      HCPCS rows, while Part&nbsp;D uses the single "Overall" row to avoid double-counting. The FDA↔CMS join is
      exact-then-fuzzy (token-sort ≥ 88) after salt/form normalization.</li>
      <li>Orphan status is pulled from the FDA OOPD database (no public API, behind bot protection), resolved per ingredient;
      "serial-orphan" status further requires no approved non-orphan indication (which is why Lenvima is excluded but
      Calquence, Imbruvica, Ofev, Pomalyst qualify).</li>
    </ul>
  </div>

  <div class="callout">
    <h3>Honest limitations</h3>
    <p style="margin:0">Efficacy supplements are a proxy for new indications; Cycle&nbsp;3 (2028) Maximum Fair Prices are not
    yet published and are left null (never imputed); insulin is classified as a biologic after FDA's 2020 BLA transition
    (a modality edge case); and the top-50 "negotiation-eligible" set is an approximation from spend data.</p>
  </div>

  <p style="margin:10px 0 0"><b>Reproducibility.</b> Every figure and statistic regenerates from cached public data via a
  single command, so the same inputs always produce the same numbers. A full data dictionary and a findings log showing the
  computation behind each headline number accompany the project; both are available on request.</p>
</section>

<section class="pagebreak">
  <div class="eyebrow">Appendix B · Reproduce &amp; explore</div>
  <h2 class="kicker" style="border:none;font-size:17px;margin:2px 0 7px">Reproduce &amp; explore</h2>
  {shot_html}
  <p class="figcap">Interactive dashboard — each drug's approval-to-indication timeline against its negotiation clock,
  with spend, modality, and orphan status in the side panel.</p>
  <div class="box">
    <ul>
      <li><b>Interactive dashboard:</b> {dash_html} — select any drug to see its approval-to-indication timeline against its
      negotiation clock, with spend, modality, and orphan status; or compare the full negotiated cohort at a glance.</li>
      <li><b>Two analysis-ready datasets:</b> <code>innovation_clock_master.csv</code> (one row per drug × indication event)
      and <code>innovation_clock_summary.csv</code> (one row per drug), each with a documented data dictionary.</li>
      <li><b>Fully reproducible:</b> every figure and statistic is generated from cached public data (FDA + CMS) by a single
      command, so the same inputs always produce the same numbers. Code and full methodology available on request.</li>
    </ul>
  </div>
  <div class="foot">Appendix · The Innovation Clock · self-contained work sample · built from public FDA &amp; CMS data</div>
</section>
"""


def build_html(stats: Dict[str, Any], policy: Dict[str, Any],
               with_appendix: bool = False, warnings: list = None) -> str:
    s = stats
    facts = policy["facts"]
    sm = s["distribution"].get("small molecule", {})
    bio = s["distribution"].get("biologic", {})
    epic = _fact(facts, "EPIC would block")
    myth = _fact(facts, "myth")
    phrma = _fact(facts, "PhRMA")
    proj = _fact(facts, "Industry projections")
    kff = _fact(facts, "KFF")
    obbba = _fact(facts, "OBBBA orphan provision")
    cbo = _fact(facts, "CBO")
    rule = _fact(facts, "timing rule (pill")

    fig1, fig2, fig3 = _img("fig1_innovation_clock.png"), _img("fig2_spend_vs_time.png"), _img("fig3_distribution.png")

    npc = _fact(facts, "NPC")
    epic_act = _fact(facts, "EPIC Act (H.R.")
    if warnings is None:
        warnings = []
    # Stable inline citation numbers; every one is referenced at least once below.
    cited = [("rule", rule), ("epic_act", epic_act), ("obbba", obbba), ("cbo", cbo),
             ("myth", myth), ("epic", epic), ("phrma", phrma), ("proj", proj),
             ("npc", npc), ("kff", kff)]
    num = {k: i + 1 for i, (k, _) in enumerate(cited)}
    src_items = [f"<li><b>[{num[k]}]</b> <span>{f.get('source_org','')}</span> — "
                 f"<a href='{f.get('source_url','')}'>{f.get('source_url','')}</a></li>"
                 for k, f in cited]
    cms = policy.get("cms_sources", {})
    for label, u in [("CMS Drug Price Negotiation", cms.get("negotiation_program")),
                     ("CMS Part D Spending by Drug", cms.get("part_d_spending")),
                     ("CMS Part B Spending by Drug", cms.get("part_b_spending")),
                     ("FDA Drugs@FDA / openFDA", cms.get("openfda_drugsfda")),
                     ("FDA Orphan Drug Designations", cms.get("fda_orphan"))]:
        if u:
            src_items.append(f"<li><b>[data]</b> <span>{label}</span> — <a href='{u}'>{u}</a></li>")
    src_html = "".join(src_items)

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page {{ size: letter; margin: 14mm 15mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: Georgia, 'Times New Roman', serif; color:#1d1d1f; font-size:10.3px; line-height:1.5; margin:0; }}
h1,h2,h3,.eyebrow,.stat-big,.kicker {{ font-family: 'Helvetica Neue', Arial, sans-serif; }}
.eyebrow {{ text-transform:uppercase; letter-spacing:2px; font-size:8.5px; color:#1b6ca8; font-weight:700; }}
h1 {{ font-size:22px; margin:3px 0 2px; letter-spacing:-0.4px; line-height:1.05; }}
.dek {{ font-size:10.8px; color:#444; margin:0 0 7px; max-width:94%; }}
.rule {{ height:2.5px; background:#1b6ca8; width:100%; margin:5px 0 9px; }}
.hero {{ display:flex; gap:14px; align-items:center; background:#f4f7fa; border:1px solid #e0e8ef; border-radius:8px; padding:10px 14px; margin-bottom:9px; }}
.stat-big {{ font-size:33px; font-weight:800; color:#1b6ca8; line-height:0.95; white-space:nowrap; }}
.stat-cap {{ font-size:10.5px; color:#333; }}
.cols {{ column-count:2; column-gap:18px; }}
.cols p {{ margin:0 0 8px; }}
img.fig {{ width:100%; border:1px solid #e6e6e6; border-radius:5px; margin:4px 0; }}
.figcap {{ font-size:8.6px; color:#666; font-family:'Helvetica Neue',Arial,sans-serif; margin:0 0 12px; }}
table {{ width:100%; border-collapse:collapse; font-family:'Helvetica Neue',Arial,sans-serif; font-size:9.2px; margin:6px 0 4px; }}
th,td {{ text-align:left; padding:5px 7px; border-bottom:1px solid #e6e6e6; }}
th {{ background:#f4f7fa; color:#1b6ca8; text-transform:uppercase; letter-spacing:.5px; font-size:8.2px; }}
.callout {{ background:#fdf3ec; border-left:4px solid #d4761f; border-radius:0 6px 6px 0; padding:11px 14px; margin:12px 0; }}
.callout h3 {{ margin:0 0 5px; color:#d4761f; font-size:12px; }}
.two {{ display:flex; gap:14px; }}
.box {{ flex:1; border:1px solid #e6e6e6; border-radius:6px; padding:11px 13px; }}
.box.shows {{ border-top:3px solid #1b6ca8; }} .box.contested {{ border-top:3px solid #d4761f; }}
.box h3 {{ margin:0 0 6px; font-size:11.5px; }}
.box ul {{ margin:0; padding-left:15px; }} .box li {{ margin-bottom:5px; }}
h2.kicker {{ font-size:13px; color:#1d1d1f; margin:16px 0 4px; border-bottom:1px solid #ddd; padding-bottom:3px; }}
.src {{ font-family:'Helvetica Neue',Arial,sans-serif; font-size:7.7px; color:#555; }}
.src ul {{ list-style:none; padding:0; margin:4px 0; column-count:1; }}
.src li {{ margin-bottom:2px; word-break:break-all; }} .src a {{ color:#1b6ca8; text-decoration:none; }}
.src span {{ color:#222; font-weight:600; }}
.pagebreak {{ break-before:page; }}
.foot {{ font-family:'Helvetica Neue',Arial,sans-serif; font-size:8px; color:#888; border-top:1px solid #ddd; margin-top:10px; padding-top:6px; }}
small.cite {{ color:#1b6ca8; }}
</style></head><body>

<div class="eyebrow">Medicare · Drug Pricing · Innovation Policy</div>
<h1>The Innovation Clock</h1>
<p class="dek">When do America's most expensive Medicare drugs earn their clinical value — and how does that timing collide
with the Inflation Reduction Act's price-negotiation deadline?</p>
<div class="rule"></div>

<div class="hero">
  <div><div class="stat-big">{s['sm_in_window_count']} of {s['sm_negotiated']}</div></div>
  <div class="stat-cap"><b>negotiated small-molecule <u>drugs</u> gained a brand-new FDA-approved indication during their year&nbsp;7–9 window</b>
  — the very years the IRA's negotiation clock cuts short for pills. Separately, <b>{s['pct_all_after_clock']}% of new <u>indications</u></b>
  across the {s['n_negotiated']} negotiated drugs arrived <i>after</i> the drug's negotiation clock would already be running. Those drugs
  account for <b>~{_b(s['negotiated_total_spend'])}</b> in gross Medicare spending (Part&nbsp;D + Part&nbsp;B, {s['spend_year']}).</div>
</div>

<img class="fig" src="{fig1}"/>
<p class="figcap"><b>Figure 1.</b> Each lane is an IRA-negotiated drug, from first FDA approval (year 0) to its most recent new indication.
Dots are new indications (FDA efficacy supplements); the diamond is the negotiation clock — year&nbsp;9 for small molecules (NDA),
year&nbsp;13 for biologics (BLA). The shaded band is the period when Medicare's negotiated price is in effect. Biologics keep
earning indications years past the point where small molecules are already price-controlled.</p>

<div class="pagebreak"></div>
<div class="cols">
<p>The IRA lets Medicare negotiate prices for its highest-spend, single-source drugs. But the clock runs differently by
<b>modality</b>: a small-molecule pill (FDA "NDA") can be selected at year&nbsp;7 with a negotiated price at year&nbsp;9, while a
biologic ("BLA") is shielded until year&nbsp;11/13.<small class="cite"> [{num['rule']}]</small> That four-year gap is the contested
"<b>pill penalty</b>." Why does timing matter for value? Because drugs rarely arrive fully formed — they accumulate new approved
uses for years. In this cohort, small-molecule indications land a median of <b>{sm.get('median_years','—')} years</b> after launch,
and <b>{sm.get('pct_back_half','—')}%</b> arrive in the back half of the pre-clock window. Roughly <b>{sm.get('pct_after_clock','—')}%</b>
of small-molecule indications — and <b>{bio.get('pct_after_clock','—')}%</b> of biologic indications — are approved only
<i>after</i> the negotiation clock has struck. The policy question is whether negotiating a pill's price at year&nbsp;9 chills the
late-stage research that produces those additional indications — or whether that fear is, as critics put it, overstated.</p>
</div>

<h2 class="kicker">Spend, longevity, and the modality split</h2>
<img class="fig" src="{fig2}" style="max-width:74%"/>
<p class="figcap"><b>Figure 2.</b> Latest-year Medicare spend vs. how long each of the <b>40 negotiated drugs</b> keeps earning new indications.
Biologics (amber) cluster to the right — they keep expanding well past year&nbsp;13 — while the highest-spend small molecules
(e.g. Eliquis, Ozempic, Jardiance) reach their negotiation clock at year&nbsp;9.</p>

<p class="figcap" style="margin-bottom:2px"><b>Table.</b> New indications by modality across the 40 negotiated drugs (# = efficacy-supplement events; 30 small molecules + 10 biologics).</p>
<table>
<tr><th>Modality</th><th># new indications</th><th>Median yrs to indication</th><th>% in back half of window</th><th>% after the clock</th></tr>
<tr><td>Small molecule — clock yr 9</td><td>{sm.get('n_indications','—')}</td><td>{sm.get('median_years','—')}</td><td>{sm.get('pct_back_half','—')}%</td><td>{sm.get('pct_after_clock','—')}%</td></tr>
<tr><td>Biologic — clock yr 13</td><td>{bio.get('n_indications','—')}</td><td>{bio.get('median_years','—')}</td><td>{bio.get('pct_back_half','—')}%</td><td>{bio.get('pct_after_clock','—')}%</td></tr>
</table>

<div class="callout">
<h3>Rare-disease angle</h3>
<p style="margin:0">Of the negotiated cohort, <b>{s['negotiated_with_orphan']}</b> drugs carry at least one FDA-approved orphan
(rare-disease) indication, and <b>{s['negotiated_multi_orphan']}</b> carry two or more. The <b>One Big Beautiful Bill Act</b>
(signed July&nbsp;4, 2025) now exempts "serial orphan" drugs — multiple rare-disease indications and <i>no</i> non-orphan approval —
and resets their negotiation clock to first non-orphan approval.<small class="cite"> [{num['obbba']}]</small> Applying that stricter test
(multiple orphan indications <i>and</i> no approved non-orphan indication), <b>{s['serial_orphan_strict_count']}</b> negotiated drugs
({', '.join(s['serial_orphan_strict']) if s['serial_orphan_strict'] else '—'}) plausibly qualify — Lenvima is excluded because it
also treats renal cell and endometrial carcinoma (non-orphan). CBO estimated the expanded carve-out will cost Medicare roughly
<b>{cbo.get('numeric_value','$8.8B')}</b>.<small class="cite"> [{num['cbo']}]</small></p>
</div>

<div class="pagebreak"></div>
<h2 class="kicker">What the data shows · what remains contested</h2>
<div class="two">
  <div class="box shows">
    <h3>What the data shows</h3>
    <ul>
      <li><b>{s['sm_in_window_count']} of {s['sm_negotiated']}</b> negotiated small-molecule <u>drugs</u> gained a new indication in years 7–9 — pills <i>do</i> keep earning clinical value as the clock closes.</li>
      <li>Biologics keep approving new uses far longer: <b>{bio.get('pct_after_clock','—')}%</b> of their <u>indications</u> land after year 13, vs <b>{sm.get('pct_after_clock','—')}%</b> for pills after year 9.</li>
      <li><b>Independent corroboration:</b> a peer-reviewed NPC study (Patterson et al., 2024) found <b>25% of oncology drugs</b> got their most recent subsequent indication only after they would be negotiation-eligible — closely matching this cohort's own <b>~{s['pct_all_after_clock']}%</b>.<small class="cite"> [{num['npc']}]</small></li>
      <li>The 40 negotiated drugs account for <b>~{_b(s['negotiated_total_spend'])}</b> in gross Medicare spending (Part D + Part B, {s['spend_year']}), <i>computed from CMS Spending-by-Drug data</i> — not CMS's official per-cycle totals, which use different 12-month windows.</li>
      <li>An EPIC-style 11-year rule moves <i>only</i> the small-molecule clock — biologics already sit at year 11. Under it, Medicare could <b>not</b> have negotiated <b>{s['epic_blocked_count']} of the {s['epic_sm_total']}</b> negotiated small molecules — about <b>{_b(s['epic_blocked_spend'])}</b> in spend.<small class="cite"> [{num['epic_act']}]</small></li>
    </ul>
  </div>
  <div class="box contested">
    <h3>What remains contested</h3>
    <ul>
      <li><b>Industry (PhRMA/PHAR, 2023):</b> 61% of the 31 cancer drugs approved 2006–2012 gained at least one new indication after launch, and ~40% of those arrived 7+ years out — inside the window the year-9 clock truncates.<small class="cite"> [{num['phrma']}]</small></li>
      <li><b>Industry projection:</b> a University of Chicago analysis projects roughly <b>188 fewer small-molecule medicines</b> as a result of the 9-vs-13 gap.<small class="cite"> [{num['proj']}]</small></li>
      <li><b>Critics (Public Citizen):</b> call the penalty a "myth," noting small-molecule venture investment has not fallen since the program passed.<small class="cite"> [{num['myth']}]</small> An EPIC delay, they find, would have blocked {epic.get('numeric_value','5 of the first 10 and 8 of the next 15')} drugs.<small class="cite"> [{num['epic']}]</small></li>
      <li><b>Independent (KFF):</b> drugs that would be ineligible under a delayed (biologic-style) timeline accounted for about two-thirds of Part&nbsp;D spending on the first 25 selected drugs — <b>$61B of $91B</b>.<small class="cite"> [{num['kff']}]</small></li>
    </ul>
  </div>
</div>

<p style="margin-top:12px"><b>Bottom line.</b> The data cut both ways. Small molecules genuinely keep earning new indications inside the
window the clock truncates — the kernel of truth in the innovation-incentive argument. Yet delaying selection to equalize with
biologics would also pull tens of billions of dollars of high-spend drugs out of negotiation. Whether the EPIC Act is an
innovation fix or a windfall depends on which of these effects you weight — and the same dataset supports both readings.</p>

<div class="src">
<b>Sources &amp; methodology</b>
<ul>{src_html}</ul>
<p style="margin:4px 0 0"><b>Cohort:</b> all numbers and figures use the <b>{s['n_negotiated']} IRA-negotiated drugs</b> (Cycles 1–3;
{s['modality_counts'].get('small molecule',0)} small molecule + {s['modality_counts'].get('biologic',0)} biologic). Modality = FDA
application type of the earliest original approval (NDA = small molecule, BLA = biologic). "New indications" = FDA
<i>efficacy supplements</i>, a documented proxy that can include some population/line-of-therapy expansions. <b>Spend</b> = gross
Medicare spending (Part&nbsp;D + Part&nbsp;B, {s['spend_year']}) computed from CMS Spending-by-Drug data — not CMS's official per-cycle
totals. <b>Orphan</b> status is from the real FDA Orphan Drug Designations database; the strict serial-orphan test is a documented
heuristic. Cycle&nbsp;3 Maximum Fair Prices are not yet published. Full methodology &amp; caveats are detailed in the appendix and the live site's Methodology tab.</p>
</div>
<div class="foot">The Innovation Clock · built from public FDA &amp; CMS data · reproduces from <code>python -m src.run_all</code>.</div>
</body></html>"""

    if with_appendix:
        html = html.replace("</body></html>", _appendix_html(warnings) + "\n</body></html>")
    return html


def render_pdf(html_path, pdf_out) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] playwright not available: {e}")
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{html_path}")
            page.pdf(path=str(pdf_out), format="Letter", print_background=True,
                     margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            browser.close()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] PDF render failed: {e}")
        return False


def run() -> Dict[str, Any]:
    stats = json.loads(STATS.read_text())
    policy = json.loads(POLICY.read_text())
    warnings: list = []

    # capture the dashboard screenshot for the appendix (best-effort, non-blocking)
    capture_dashboard_screenshot()

    # (a) the original 3-page fact sheet (unchanged)
    html3 = build_html(stats, policy, with_appendix=False)
    HTML_OUT.write_text(html3)
    ok3 = render_pdf(HTML_OUT, PDF_OUT)
    if ok3:
        print(f"Wrote {PDF_OUT.name} ({PDF_OUT.stat().st_size//1024} KB, 3 pages)")

    # (b) the 5-page upload deliverable (pages 1-3 identical + 2 appendix pages)
    html5 = build_html(stats, policy, with_appendix=True, warnings=warnings)
    FULL_HTML.write_text(html5)
    ok5 = render_pdf(FULL_HTML, UPLOAD_PDF)
    if ok5:
        print(f"Wrote {UPLOAD_PDF.name} ({UPLOAD_PDF.stat().st_size//1024} KB, upload deliverable)")
    else:
        print("  Upload PDF not rendered. Run: python -m playwright install chromium")

    if warnings:
        print("  [placeholders] " + "; ".join(warnings))
    return {"html": str(HTML_OUT), "pdf": str(PDF_OUT) if ok3 else None,
            "upload_pdf": str(UPLOAD_PDF) if ok5 else None, "warnings": warnings,
            "repo_url": REPO_URL, "dashboard_url": DASHBOARD_URL}


if __name__ == "__main__":
    run()
