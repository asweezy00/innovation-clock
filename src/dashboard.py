"""Generate dashboard/index.html — a single self-contained, multi-tab site:
  * Dashboard  — the interactive D3 "Innovation Clock"
  * Fact Sheet — the web-rendered fact sheet (figures + findings + PDF download)
  * Methodology — the full methodology, rendered from docs/METHODOLOGY.md

Processed data is embedded as a JS object (no external fetch -> no CORS, opens
via file://). D3 v7 is loaded from CDN. No localStorage/sessionStorage.
"""
from __future__ import annotations

import base64
import json
import re

from . import util, factsheet

JSON_IN = util.PROCESSED / "dashboard_data.json"
STATS_IN = util.PROCESSED / "headline_stats.json"
POLICY_IN = util.RAW / "policy_facts.json"
METHODOLOGY_MD = util.DOCS / "METHODOLOGY.md"
FIG_DIR = util.ROOT / "factsheet" / "figures"
OUT = util.ROOT / "dashboard" / "index.html"

REPO_URL = factsheet.REPO_URL
PDF_HREF = "../factsheet/" + factsheet.OUTPUT_NAME  # repo is served whole on Pages


def _img(name: str) -> str:
    p = FIG_DIR / name
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def _fact(facts, sub):
    for f in facts:
        if sub.lower() in f["topic"].lower():
            return f
    return {}


def _bn(x):
    return f"${x/1e9:.1f}B" if x else "n/a"


# ---------------------------------------------------------------- Fact Sheet tab
def _factsheet_section(s, policy) -> str:
    facts = policy["facts"]
    sm = s["distribution"].get("small molecule", {})
    bio = s["distribution"].get("biologic", {})
    mc = s.get("modality_counts", {})
    phrma, proj, npc = _fact(facts, "PhRMA"), _fact(facts, "Industry projections"), _fact(facts, "NPC")
    myth, epic, kff = _fact(facts, "myth"), _fact(facts, "EPIC would block"), _fact(facts, "KFF")
    rule, epic_act = _fact(facts, "timing rule (pill"), _fact(facts, "EPIC Act (H.R.")
    obbba, cbo = _fact(facts, "OBBBA orphan provision"), _fact(facts, "CBO")
    cited = [("rule", rule), ("epic_act", epic_act), ("obbba", obbba), ("cbo", cbo),
             ("myth", myth), ("epic", epic), ("phrma", phrma), ("proj", proj),
             ("npc", npc), ("kff", kff)]
    num = {k: i + 1 for i, (k, _) in enumerate(cited)}
    src_items = "".join(
        f"<li><b>[{num[k]}]</b> <span>{f.get('source_org','')}</span> — "
        f"<a href='{f.get('source_url','')}' target='_blank' rel='noopener'>{f.get('source_url','')}</a></li>"
        for k, f in cited)
    cms = policy.get("cms_sources", {})
    for label, u in [("CMS Drug Price Negotiation", cms.get("negotiation_program")),
                     ("CMS Part D Spending by Drug", cms.get("part_d_spending")),
                     ("CMS Part B Spending by Drug", cms.get("part_b_spending")),
                     ("FDA Drugs@FDA / openFDA", cms.get("openfda_drugsfda")),
                     ("FDA Orphan Drug Designations", cms.get("fda_orphan"))]:
        if u:
            src_items += f"<li><b>[data]</b> <span>{label}</span> — <a href='{u}' target='_blank' rel='noopener'>{u}</a></li>"

    return f"""
<div class="article">
  <div class="eyebrow">Fact Sheet · Medicare · Drug Pricing</div>
  <h1 class="fs-title">The Innovation Clock</h1>
  <p class="fs-dek">When do America's most expensive Medicare drugs earn their clinical value — and how does that timing
  collide with the Inflation Reduction Act's price-negotiation deadline?</p>
  <a class="btn-pdf" href="{PDF_HREF}" target="_blank" rel="noopener">⬇ Download the 5-page PDF fact sheet</a>

  <div class="fs-hero">
    <div class="fs-stat-big">{s['sm_in_window_count']} of {s['sm_negotiated']}</div>
    <div class="fs-stat-cap"><b>negotiated small-molecule drugs gained a brand-new FDA-approved indication in their
    year&nbsp;7–9 window</b> — the very years the IRA's negotiation clock cuts short for pills. Separately,
    <b>{s['pct_all_after_clock']}% of new indications</b> across the {s['n_negotiated']} negotiated drugs arrived
    <i>after</i> the clock would already be running. Those drugs account for <b>~{_bn(s['negotiated_total_spend'])}</b>
    in gross Medicare spending (Part&nbsp;D + Part&nbsp;B, {s['spend_year']}).</div>
  </div>

  <img class="fs-fig" src="{_img('fig1_innovation_clock.png')}" alt="Innovation Clock timeline"/>
  <p class="fs-cap"><b>Figure 1.</b> Each lane is an IRA-negotiated drug, from first FDA approval (year 0) to its most recent
  new indication. Dots are new indications; the diamond is the negotiation clock (yr&nbsp;9 small molecule, yr&nbsp;13 biologic);
  the shaded band is the price-controlled period.</p>

  <table class="fs-table">
    <tr><th>Modality</th><th># new indications</th><th>Median yrs</th><th>% in back half</th><th>% after clock</th></tr>
    <tr><td>Small molecule — clock yr 9</td><td>{sm.get('n_indications','—')}</td><td>{sm.get('median_years','—')}</td><td>{sm.get('pct_back_half','—')}%</td><td>{sm.get('pct_after_clock','—')}%</td></tr>
    <tr><td>Biologic — clock yr 13</td><td>{bio.get('n_indications','—')}</td><td>{bio.get('median_years','—')}</td><td>{bio.get('pct_back_half','—')}%</td><td>{bio.get('pct_after_clock','—')}%</td></tr>
  </table>
  <p class="fs-cap">Computed on the {s['n_negotiated']} negotiated drugs ({mc.get('small molecule',0)} small molecule + {mc.get('biologic',0)} biologic); {s.get('n_events','—')} efficacy-supplement events.</p>

  <div class="fs-twofig">
    <figure><img class="fs-fig" src="{_img('fig2_spend_vs_time.png')}" alt="Spend vs time"/>
      <figcaption class="fs-cap"><b>Figure 2.</b> Spend vs. how long each drug keeps earning new indications.</figcaption></figure>
    <figure><img class="fs-fig" src="{_img('fig3_distribution.png')}" alt="Distribution"/>
      <figcaption class="fs-cap"><b>Figure 3.</b> When new indications are approved, by modality.</figcaption></figure>
  </div>

  <div class="fs-callout">
    <h3>Rare-disease angle</h3>
    <p>Of the negotiated cohort, <b>{s['negotiated_with_orphan']}</b> drugs carry ≥1 FDA-approved orphan indication and
    <b>{s['negotiated_multi_orphan']}</b> carry two or more. The One Big Beautiful Bill Act (July&nbsp;2025) exempts
    "serial-orphan" drugs — multiple rare-disease indications and <i>no</i> non-orphan approval.<small> [{num['obbba']}]</small>
    Under that stricter test, <b>{s['serial_orphan_strict_count']}</b> qualify ({', '.join(s['serial_orphan_strict'])});
    Lenvima is excluded for its non-orphan renal-cell and endometrial indications. CBO scored the carve-out at
    <b>{cbo.get('numeric_value','$8.8B')}</b>.<small> [{num['cbo']}]</small></p>
  </div>

  <h2 class="fs-h2">What the data shows · what remains contested</h2>
  <div class="fs-two">
    <div class="fs-box shows">
      <h3>What the data shows</h3>
      <ul>
        <li><b>{s['sm_in_window_count']} of {s['sm_negotiated']}</b> negotiated small-molecule <u>drugs</u> gained a new indication in years 7–9.</li>
        <li>Biologics keep approving new uses far longer: <b>{bio.get('pct_after_clock','—')}%</b> of their <u>indications</u> land after year 13, vs <b>{sm.get('pct_after_clock','—')}%</b> for pills after year 9.</li>
        <li><b>Independent corroboration:</b> a peer-reviewed NPC study (2024) found <b>25% of oncology drugs</b> got their most recent subsequent indication only after negotiation eligibility — close to this cohort's <b>~{s['pct_all_after_clock']}%</b>.<small> [{num['npc']}]</small></li>
        <li>An EPIC-style 11-yr rule moves <i>only</i> the small-molecule clock — biologics already sit at year 11. Under it, Medicare could <b>not</b> have negotiated <b>{s['epic_blocked_count']} of the {s['epic_sm_total']}</b> negotiated small molecules (~<b>{_bn(s['epic_blocked_spend'])}</b>).<small> [{num['epic_act']}]</small></li>
      </ul>
    </div>
    <div class="fs-box contested">
      <h3>What remains contested</h3>
      <ul>
        <li><b>Industry (PhRMA/PHAR, 2023):</b> 61% of the 31 cancer drugs approved 2006–2012 gained ≥1 new indication after launch, ~40% of those 7+ years out.<small> [{num['phrma']}]</small></li>
        <li><b>Industry projection:</b> a University of Chicago analysis projects ~<b>188 fewer small-molecule medicines</b> from the 9-vs-13 gap.<small> [{num['proj']}]</small></li>
        <li><b>Critics (Public Citizen):</b> call the penalty a "myth";<small> [{num['myth']}]</small> an EPIC delay would have blocked {epic.get('numeric_value','5 of 10 and 8 of 15')} drugs.<small> [{num['epic']}]</small></li>
        <li><b>Independent (KFF):</b> drugs ineligible under a delayed timeline were ~two-thirds of Part&nbsp;D spend on the first 25 selected drugs — <b>$61B of $91B</b>.<small> [{num['kff']}]</small></li>
      </ul>
    </div>
  </div>
  <p class="fs-bottom"><b>Bottom line.</b> The data cut both ways: small molecules genuinely keep earning new indications inside
  the window the clock truncates, yet equalizing the clock with biologics would pull tens of billions of high-spend drugs out of
  negotiation. The same dataset supports both readings.</p>

  <div class="fs-src"><b>Sources &amp; methodology.</b> Cohort = the {s['n_negotiated']} IRA-negotiated drugs (Cycles 1–3).
  "New indications" = FDA efficacy supplements (a documented proxy). Spend = gross Medicare spending (Part&nbsp;D + Part&nbsp;B,
  {s['spend_year']}) computed from CMS Spending-by-Drug data, not CMS per-cycle totals. Cycle&nbsp;3 MFPs not yet published.
  <ul>{src_items}</ul></div>
</div>
"""


# --------------------------------------------------------------- Methodology tab
def _fix_md_links(html: str) -> str:
    """Point relative doc links at the GitHub repo so they work on the hosted site."""
    def repl(m):
        href = m.group(1)
        if href.startswith(("http", "#", "mailto:")):
            return m.group(0)
        if href.startswith("../"):
            target = REPO_URL + "/blob/main/" + href[3:]
        else:
            target = REPO_URL + "/blob/main/docs/" + href
        return f'href="{target}" target="_blank" rel="noopener"'
    return re.sub(r'href="([^"]+)"', repl, html)


def _methodology_section() -> str:
    import markdown
    md = METHODOLOGY_MD.read_text()
    body = markdown.markdown(md, extensions=["extra", "tables", "sane_lists"])
    body = _fix_md_links(body)
    return f"""
<div class="article">
  <div class="eyebrow">Methodology</div>
  <p class="fs-dek">Every data-source decision, cleaning rule, and limitation behind the numbers. The full data dictionary
  and findings log live in the <a href="{REPO_URL}/tree/main/docs" target="_blank" rel="noopener">repository</a>.</p>
  <div class="md">{body}</div>
</div>
"""


# ----------------------------------------------------------------------- assembly
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>The Innovation Clock — Medicare drug timing</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  :root{--sm:#1b6ca8;--bio:#d4761f;--ink:#222;--muted:#666;--clock:#444;--after:#e8b4b8;
        --bg:#fbfaf7;--card:#fff;--line:#e6e3dc;--accent:#1b6ca8;}
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
       color:var(--ink);background:var(--bg);line-height:1.5}
  a{color:var(--accent)}
  /* top app bar */
  .appbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:6px;flex-wrap:wrap;
          background:var(--card);border-bottom:1px solid var(--line);padding:10px 26px;box-shadow:0 1px 2px rgba(0,0,0,.03)}
  .brand{font-weight:700;font-size:15px;letter-spacing:-.2px;margin-right:14px}
  .brand span{color:var(--accent)}
  .tab{font:inherit;font-size:13.5px;padding:7px 13px;border:none;background:none;color:var(--muted);
       cursor:pointer;border-radius:7px}
  .tab:hover{background:#f1efe9;color:var(--ink)}
  .tab.active{background:var(--ink);color:#fff}
  .appbar .right{margin-left:auto;display:flex;gap:8px;align-items:center}
  .ghlink{font-size:12.5px;color:var(--muted);text-decoration:none;border:1px solid var(--line);padding:6px 11px;border-radius:7px}
  .ghlink:hover{color:var(--ink);border-color:#ccc}
  .pdfmini{font-size:12.5px;background:var(--accent);color:#fff;text-decoration:none;padding:6px 11px;border-radius:7px}
  /* tab panels */
  .tabpanel{display:none}
  .tabpanel.active{display:block}
  /* dashboard */
  header.dash{padding:20px 30px 12px;border-bottom:1px solid var(--line);background:var(--card)}
  header.dash h1{margin:0;font-size:20px;letter-spacing:-0.2px}
  .sub{color:var(--muted);font-size:13px;margin-top:4px;max-width:840px}
  .controls{display:flex;gap:14px;align-items:center;flex-wrap:wrap;padding:16px 30px 0}
  select,button.ctl{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:7px;background:#fff;color:var(--ink);cursor:pointer}
  button.ctl.active{background:var(--ink);color:#fff;border-color:var(--ink)}
  .wrap{display:flex;gap:22px;padding:22px 30px;flex-wrap:wrap}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px}
  .main{flex:1 1 620px;min-width:520px}
  .side{flex:0 0 290px}
  .stat{margin-bottom:14px}
  .stat .k{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}
  .stat .v{font-size:18px;font-weight:600}
  .pill{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;font-weight:600}
  .pill.sm{background:#e3eef6;color:var(--sm)} .pill.bio{background:#f8ebdd;color:var(--bio)}
  .legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:6px}
  .legend i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px;vertical-align:-1px}
  .axis path,.axis line{stroke:#ccc}.axis text{fill:var(--muted);font-size:11px}
  .tip{position:absolute;pointer-events:none;background:#222;color:#fff;padding:6px 9px;border-radius:6px;font-size:12px;opacity:0;transition:opacity .12s;max-width:260px}
  .note{font-size:11.5px;color:var(--muted);margin-top:10px}
  .row-label{font-size:10px;fill:var(--ink)}
  footer{padding:14px 30px 30px;color:var(--muted);font-size:11.5px;max-width:900px}
  /* article (fact sheet + methodology) */
  .article{max-width:880px;margin:0 auto;padding:26px 30px 60px}
  .eyebrow{text-transform:uppercase;letter-spacing:2px;font-size:11px;color:var(--accent);font-weight:700}
  .fs-title{font-size:30px;margin:6px 0 4px;letter-spacing:-.5px}
  .fs-dek{font-size:15px;color:#444;margin:0 0 14px;max-width:90%}
  .btn-pdf{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;font-weight:600;
           padding:9px 16px;border-radius:8px;font-size:13.5px;margin-bottom:16px}
  .btn-pdf:hover{background:#155a8a}
  .fs-hero{display:flex;gap:18px;align-items:center;background:#f4f7fa;border:1px solid #e0e8ef;border-radius:10px;padding:16px 18px;margin:6px 0 18px}
  .fs-stat-big{font-size:42px;font-weight:800;color:var(--accent);line-height:.95;white-space:nowrap}
  .fs-stat-cap{font-size:13.5px;color:#333}
  .fs-fig{width:100%;border:1px solid #ececec;border-radius:6px;margin:6px 0 4px}
  .fs-cap{font-size:11.5px;color:var(--muted);margin:0 0 16px}
  .fs-twofig{display:flex;gap:16px;flex-wrap:wrap}.fs-twofig figure{flex:1 1 320px;margin:0}
  .fs-table{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0 4px}
  .fs-table th,.fs-table td{text-align:left;padding:7px 9px;border-bottom:1px solid #ececec}
  .fs-table th{background:#f4f7fa;color:var(--accent);text-transform:uppercase;letter-spacing:.4px;font-size:11px}
  .fs-h2{font-size:18px;margin:22px 0 8px;border-bottom:1px solid var(--line);padding-bottom:5px}
  .fs-callout{background:#fdf3ec;border-left:4px solid var(--bio);border-radius:0 8px 8px 0;padding:13px 16px;margin:16px 0}
  .fs-callout h3{margin:0 0 5px;color:var(--bio);font-size:15px}.fs-callout p{margin:0;font-size:13.5px}
  .fs-two{display:flex;gap:16px;flex-wrap:wrap}
  .fs-box{flex:1 1 320px;border:1px solid #ececec;border-radius:8px;padding:13px 16px}
  .fs-box.shows{border-top:3px solid var(--sm)}.fs-box.contested{border-top:3px solid var(--bio)}
  .fs-box h3{margin:0 0 7px;font-size:15px}.fs-box ul{margin:0;padding-left:17px}.fs-box li{margin-bottom:7px;font-size:13px}
  .fs-bottom{margin-top:14px;font-size:13.5px}
  small{color:var(--accent)}
  .fs-src{font-size:11.5px;color:#555;margin-top:18px;border-top:1px solid var(--line);padding-top:10px}
  .fs-src ul{list-style:none;padding:0;margin:6px 0}.fs-src li{margin-bottom:3px;word-break:break-word}
  .fs-src span{color:#222;font-weight:600}
  /* methodology markdown */
  .md{font-size:14px;color:#2a2a2a}
  .md h1{font-size:24px;margin:18px 0 6px}.md h2{font-size:19px;margin:22px 0 6px;border-bottom:1px solid var(--line);padding-bottom:4px}
  .md h3{font-size:16px;margin:16px 0 4px}
  .md code{background:#f1efe9;padding:1px 5px;border-radius:4px;font-size:12.5px}
  .md pre{background:#f6f5f1;padding:12px;border-radius:8px;overflow:auto}
  .md table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}
  .md th,.md td{border:1px solid #e3e0d8;padding:6px 9px;text-align:left}.md th{background:#f4f7fa}
  .md ul,.md ol{padding-left:22px}.md li{margin-bottom:5px}
  .md blockquote{border-left:3px solid var(--line);margin:0;padding-left:14px;color:var(--muted)}
  @media(max-width:640px){.appbar{padding:9px 16px}.article{padding:20px 16px 50px}.wrap{padding:16px}.main{min-width:0}}
</style>
</head>
<body>
<div class="appbar">
  <div class="brand">The <span>Innovation Clock</span></div>
  <button class="tab" data-tab="dashboard">Dashboard</button>
  <button class="tab" data-tab="factsheet">Fact Sheet</button>
  <button class="tab" data-tab="methodology">Methodology</button>
  <div class="right">
    <a class="pdfmini" href="__PDF_HREF__" target="_blank" rel="noopener">⬇ PDF</a>
    <a class="ghlink" href="__REPO_URL__" target="_blank" rel="noopener">View on GitHub ↗</a>
  </div>
</div>

<!-- ================= DASHBOARD TAB ================= -->
<section id="tab-dashboard" class="tabpanel">
  <header class="dash">
    <h1>The Innovation Clock</h1>
    <div class="sub">When do America's most expensive Medicare drugs earn new clinical value — and how does that line up
    with the Inflation Reduction Act's price-negotiation deadline (year&nbsp;9 for small molecules, year&nbsp;13 for biologics)?
    Each dot is a new FDA-approved indication. The diamond marks the negotiation clock; the shaded band is the price-controlled period.</div>
  </header>
  <div class="controls">
    <button id="btn-single" class="ctl active">Single drug</button>
    <button id="btn-compare" class="ctl">Compare all (negotiated)</button>
    <select id="drug"></select>
    <select id="sortby">
      <option value="modality">Sort: modality, then approval</option>
      <option value="last">Sort: latest indication</option>
      <option value="spend">Sort: Medicare spend</option>
    </select>
  </div>
  <div class="wrap">
    <div class="main panel">
      <div id="chart"></div>
      <div class="legend">
        <span><i style="background:var(--sm)"></i>Small-molecule indication</span>
        <span><i style="background:var(--bio)"></i>Biologic indication</span>
        <span><i style="background:var(--clock);border-radius:0;transform:rotate(45deg)"></i>Negotiation clock</span>
        <span><i style="background:var(--after)"></i>Price-controlled region</span>
      </div>
      <div class="note" id="chart-note"></div>
    </div>
    <div class="side panel" id="side"></div>
  </div>
  <footer>
    Sources: FDA Drugs@FDA / openFDA (approvals &amp; efficacy supplements), CMS Medicare Part&nbsp;D/B Spending by Drug
    (latest year), CMS Drug Price Negotiation fact sheets (MFPs), FDA Orphan Drug Designations. New indications are a
    proxy based on FDA <em>efficacy supplements</em>. Cycle&nbsp;3 MFPs are not yet published.
  </footer>
</section>

<!-- ================= FACT SHEET TAB ================= -->
<section id="tab-factsheet" class="tabpanel">__FACTSHEET_SECTION__</section>

<!-- ================= METHODOLOGY TAB ================= -->
<section id="tab-methodology" class="tabpanel">__METHODOLOGY_SECTION__</section>

<div class="tip" id="tip"></div>

<script>
const DATA = __DATA__;
const STATS = __STATS__;
const C = {sm:"#1b6ca8", bio:"#d4761f", clock:"#444", after:"#e8b4b8"};
const color = d => d.modality === "biologic" ? C.bio : C.sm;
const fmt$ = v => v==null ? "n/a" : (v>=1e9 ? "$"+(v/1e9).toFixed(2)+"B" : v>=1e6 ? "$"+(v/1e6).toFixed(1)+"M" : "$"+d3.format(",")(Math.round(v)));
const resolved = DATA.drugs.filter(d => d.modality && d.original_approval_date);
const tip = d3.select("#tip");

const sel = d3.select("#drug");
resolved.slice().sort((a,b)=> (a.in_negotiated===b.in_negotiated? d3.ascending(a.brand,b.brand) : (a.in_negotiated?-1:1)))
  .forEach(d => sel.append("option").attr("value", d.brand).text(d.brand + (d.in_negotiated? "  •" : "")));

let mode = "single";
function showTip(html, ev){tip.html(html).style("left",(ev.pageX+12)+"px").style("top",(ev.pageY+12)+"px").style("opacity",1);}
function hideTip(){tip.style("opacity",0);}
function indYears(d){return d.indications.map(i=>i.years_after_launch).filter(v=>v!=null);}
function lastYear(d){const y=indYears(d); return y.length?Math.max(...y):0;}

function single(brand){
  const d = resolved.find(x=>x.brand===brand) || resolved[0];
  drawTimeline([d], {height: 150, single:true});
  d3.select("#chart-note").html(`Showing <b>${d.brand}</b> (${d.generic}). Dots = new FDA indications; diamond = year-${d.clock_year} negotiation clock.`);
  drawSide(d);
}
function compare(){
  let ds = resolved.filter(d=>d.in_negotiated);
  const sortby = d3.select("#sortby").property("value");
  if(sortby==="last") ds.sort((a,b)=> d3.descending(lastYear(a), lastYear(b)));
  else if(sortby==="spend") ds.sort((a,b)=> d3.descending(a.total_spend||0, b.total_spend||0));
  else ds.sort((a,b)=> d3.ascending(a.modality==="small molecule"?0:1, b.modality==="small molecule"?0:1) || d3.ascending(a.original_approval_date,b.original_approval_date));
  drawTimeline(ds, {height: Math.max(360, ds.length*17+60)});
  d3.select("#chart-note").html(`All <b>${ds.length}</b> IRA-negotiated drugs (Cycles 1–3). Each lane is a drug from approval (left) to its most recent new indication.`);
  d3.select("#side").html(sideSummary());
}
function drawTimeline(ds, opts){
  const W = Math.min(880, (document.querySelector('.main').clientWidth||820)-36);
  const m = {top:24,right:18,bottom:34,left:118};
  const rowH = opts.single? 60 : 17;
  const H = opts.single? 150 : ds.length*rowH + m.top + m.bottom;
  const xMax = Math.min(28, Math.max(14, d3.max(ds, d=>Math.max(lastYear(d), d.clock_year))+1));
  d3.select("#chart").html("");
  const svg = d3.select("#chart").append("svg").attr("width",W).attr("height",H);
  const x = d3.scaleLinear().domain([0,xMax]).range([m.left, W-m.right]);
  const y = d3.scaleBand().domain(ds.map(d=>d.brand)).range([m.top, H-m.bottom]).padding(0.35);
  svg.append("rect").attr("x",x(9)).attr("y",m.top-6).attr("width",x(xMax)-x(9)).attr("height",H-m.bottom-m.top+6).attr("fill",C.after).attr("opacity",0.10);
  [[9,C.sm,"yr 9"],[13,C.bio,"yr 13"]].forEach(([v,c,t])=>{
    svg.append("line").attr("x1",x(v)).attr("x2",x(v)).attr("y1",m.top-6).attr("y2",H-m.bottom).attr("stroke",c).attr("stroke-dasharray","2,2").attr("opacity",0.6);
    svg.append("text").attr("x",x(v)).attr("y",m.top-10).attr("text-anchor","middle").attr("font-size",10).attr("fill",c).text(t);
  });
  ds.forEach(d=>{
    const yy = y(d.brand)+y.bandwidth()/2;
    svg.append("line").attr("x1",x(0)).attr("x2",x(Math.max(lastYear(d),d.clock_year))).attr("y1",yy).attr("y2",yy).attr("stroke","#ddd").attr("stroke-width",1);
    svg.append("line").attr("x1",x(0)).attr("x2",x(0)).attr("y1",yy-5).attr("y2",yy+5).attr("stroke",color(d)).attr("stroke-width",2);
    svg.selectAll(null).data(d.indications.filter(i=>i.years_after_launch!=null)).enter().append("circle")
      .attr("cx",i=>x(i.years_after_launch)).attr("cy",yy).attr("r",opts.single?6:3.6).attr("fill",color(d))
      .attr("stroke", i=> i.years_after_launch>=d.clock_year ? C.clock : "none").attr("stroke-width",1)
      .attr("opacity", i=> i.years_after_launch>=d.clock_year ? 0.95 : 0.65)
      .on("mousemove",(ev,i)=>showTip(`${d.brand}: new indication at <b>${i.years_after_launch.toFixed(1)} yrs</b> (${i.date})${i.years_after_launch>=d.clock_year?" — after clock":""}`,ev)).on("mouseleave",hideTip);
    svg.append("path").attr("transform",`translate(${x(d.clock_year)},${yy})`).attr("d",d3.symbol(d3.symbolDiamond, opts.single?90:42)()).attr("fill",C.clock)
      .on("mousemove",ev=>showTip(`${d.brand}: negotiation clock at year ${d.clock_year} (${d.modality})`,ev)).on("mouseleave",hideTip);
    svg.append("text").attr("x",m.left-8).attr("y",yy).attr("dy","0.32em").attr("text-anchor","end").attr("class","row-label").attr("font-size",opts.single?12:10).text(d.brand);
  });
  svg.append("g").attr("class","axis").attr("transform",`translate(0,${H-m.bottom})`).call(d3.axisBottom(x).ticks(8).tickFormat(d=>d+"y"));
  svg.append("text").attr("x",(m.left+W-m.right)/2).attr("y",H-2).attr("text-anchor","middle").attr("font-size",11).attr("fill","#666").text("Years after first FDA approval");
}
function drawSide(d){
  const cyc = d.ira_cycle ? `Cycle ${d.ira_cycle}` : "not negotiated";
  const mfp = d.mfp_usd!=null ? fmt$(d.mfp_usd)+" / mo" : (d.ira_cycle===3? "pending (2026)" : "n/a");
  const inWindow = indYears(d).some(v=> v>=d.clock_year-2 && v<=d.clock_year);
  const afterN = indYears(d).filter(v=>v>=d.clock_year).length;
  d3.select("#side").html(`
    <div class="stat"><div class="k">Modality</div><div class="v"><span class="pill ${d.modality==='biologic'?'bio':'sm'}">${d.modality}</span> · clock yr ${d.clock_year}</div></div>
    <div class="stat"><div class="k">First approval</div><div class="v">${d.original_approval_date||'—'} <span style="font-size:12px;color:#666">(${d.application_number||''})</span></div></div>
    <div class="stat"><div class="k">New indications</div><div class="v">${d.indications.length} total · ${afterN} after clock</div></div>
    <div class="stat"><div class="k">In yr ${d.clock_year-2}–${d.clock_year} window</div><div class="v">${inWindow?'Yes — gained value as the clock closed':'No'}</div></div>
    <div class="stat"><div class="k">IRA negotiation</div><div class="v">${cyc}</div></div>
    <div class="stat"><div class="k">Maximum Fair Price</div><div class="v">${mfp}</div></div>
    <div class="stat"><div class="k">Medicare spend (${DATA.spend_year})</div><div class="v">${fmt$(d.total_spend)}</div>
      <div style="font-size:12px;color:#666">Part D ${fmt$(d.part_d_spend)} · Part B ${fmt$(d.part_b_spend)}</div></div>
    <div class="stat"><div class="k">Orphan status</div><div class="v" style="font-size:15px">${d.orphan_status.replace(/_/g,' ')}${d.serial_orphan_candidate?' · serial-orphan':''}</div></div>
  `);
}
function sideSummary(){
  if(!STATS||!STATS.distribution) return "<div class='stat'><div class='k'>Cohort</div><div class='v'>"+resolved.length+" drugs resolved</div></div>";
  const s=STATS, sm=s.distribution["small molecule"]||{}, bio=s.distribution["biologic"]||{};
  return `
    <div class="stat"><div class="k">Negotiated cohort spend (${s.spend_year})</div><div class="v">${fmt$(s.negotiated_total_spend)}</div></div>
    <div class="stat"><div class="k">Small molecules gaining an indication in yr 7–9</div><div class="v">${s.sm_in_window_count} of ${s.sm_negotiated}</div></div>
    <div class="stat"><div class="k">% indications after clock</div><div class="v">SM ${sm.pct_after_clock||0}% · Bio ${bio.pct_after_clock||0}%</div></div>
    <div class="stat"><div class="k">Serial-orphan (negotiated, strict)</div><div class="v">${s.serial_orphan_strict_count} <span style="font-size:12px;color:#666">(${s.negotiated_multi_orphan} multi-orphan)</span></div></div>
    <div class="stat"><div class="k">Blocked under an EPIC 11-yr rule (small molecules)</div><div class="v">${s.epic_blocked_count} of ${s.epic_sm_total} · ${fmt$(s.epic_blocked_spend)}</div></div>
    <div class="note">"•" in the drug list marks IRA-negotiated drugs.</div>`;
}
function redrawDashboard(){ mode==="single" ? single(sel.property("value")) : compare(); }

d3.select("#btn-single").on("click",()=>{mode="single";setBtns();single(sel.property("value"));});
d3.select("#btn-compare").on("click",()=>{mode="compare";setBtns();compare();});
sel.on("change",()=>{ if(mode==="single") single(sel.property("value")); });
d3.select("#sortby").on("change",()=>{ if(mode==="compare") compare(); });
function setBtns(){d3.select("#btn-single").classed("active",mode==="single");d3.select("#btn-compare").classed("active",mode==="compare");}
window.addEventListener("resize",()=>{ if(document.getElementById("tab-dashboard").classList.contains("active")) redrawDashboard(); });

// ---- tab routing ----
const TABS = ["dashboard","factsheet","methodology"];
function showTab(name){
  if(!TABS.includes(name)) name="dashboard";
  TABS.forEach(t=>{
    document.getElementById("tab-"+t).classList.toggle("active", t===name);
  });
  document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("active", b.dataset.tab===name));
  if(history.replaceState) history.replaceState(null,"","#"+name);
  if(name==="dashboard") redrawDashboard();
  window.scrollTo(0,0);
}
document.querySelectorAll(".tab").forEach(b=> b.addEventListener("click",()=>showTab(b.dataset.tab)));
showTab((location.hash||"#dashboard").slice(1));
</script>
</body>
</html>
"""


def run() -> str:
    payload = json.loads(JSON_IN.read_text())
    stats = json.loads(STATS_IN.read_text()) if STATS_IN.exists() else {}
    policy = json.loads(POLICY_IN.read_text())
    fs = _factsheet_section(stats, policy) if stats else "<div class='article'>Fact sheet unavailable.</div>"
    meth = _methodology_section()
    html = (HTML
            .replace("__DATA__", json.dumps(payload))
            .replace("__STATS__", json.dumps(stats, default=str))
            .replace("__FACTSHEET_SECTION__", fs)
            .replace("__METHODOLOGY_SECTION__", meth)
            .replace("__REPO_URL__", REPO_URL)
            .replace("__PDF_HREF__", PDF_HREF))
    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(html)//1024} KB) — tabs: Dashboard, Fact Sheet, Methodology")
    return str(OUT)


if __name__ == "__main__":
    run()
