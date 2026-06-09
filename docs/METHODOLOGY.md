# Methodology

This document records every data-source decision, cleaning rule, and known limitation in the Innovation Clock pipeline. The goal is full reproducibility: `python -m src.run_all` rebuilds every artifact from cached raw responses in `data/raw/`.

## 1. The analytical frame (policy facts)

The IRA lets Medicare set a "Maximum Fair Price" (MFP) on high-spend, single-source drugs. Eligibility timing depends on **modality**, taken from the FDA application type:

- **Small molecule (FDA NDA)** — selected at **year 7** after approval; MFP effective at **year 9**.
- **Biologic (FDA BLA)** — selected at **year 11**; MFP effective at **year 13**.

The 4-year gap is the contested **"pill penalty."** The **EPIC Act (H.R. 1492, 119th Congress)** would push small-molecule selection to year 11; as of 2026 it is **pending, not enacted**. The **One Big Beautiful Bill Act** (signed July 4, 2025) broadened the orphan exclusion to "serial orphan" drugs (multiple rare-disease indications, no non-orphan approval) and resets their clock to first non-orphan approval. All policy numbers cited in outputs carry a source URL — see [`data/raw/policy_facts.json`](../data/raw/policy_facts.json), compiled from primary sources and cross-checked against the underlying documents (CMS, KFF, Congress.gov, CRS, Public Citizen, PhRMA, Sidley/Jones Day).

## 2. Cohort construction (`src/cohort.py`)

The cohort is the **union** of:

- **(A) IRA negotiation Cycles 1–3** — 10 + 15 + 15 = 40 unique molecules (Tradjenta appears in Cycle 2 *and* as the Cycle 3 renegotiation; counted once under Cycle 2). These lists and their MFPs are **curated, cited constants** verified against primary CMS fact sheets and cross-checked vs KFF on 2026-06-07. They are *baked in*, not scraped at runtime, because CMS HTML/PDF layouts change and are not reliably machine-parseable — baking them in keeps reruns deterministic and offline. The MFP values are the CMS-published **30-day-supply-equivalent** negotiated prices.
- **(B) Top-50 Medicare Part D drugs** by latest-year (2023) gross spend, fetched live from CMS and cached.

Deduplication uses the **ingredient set** (normalized active ingredients) with a **brand-name fallback** — CMS abbreviates combination-drug ingredients (e.g. "Bictegrav/Emtricit/Tenofov Ala"), so brand matching is needed to merge e.g. Biktarvy/Trelegy/Ofev that appear in both (A) and (B). The cohort is capped near 64–70 molecules.

**"Negotiation-eligible" approximation.** For the top-50 set we use high-spend single brand-name Part D drugs (brand ≠ generic; supplies like needles/lancets excluded). True IRA eligibility also requires 7+ years on market with no generic/biosimilar competitor — not determinable from spend data alone — so the top-50 set is an *approximation* that broadens the analysis beyond the negotiated 40.

**Canonical analysis cohort = the 40 negotiated drugs.** The two CSVs and the dashboard carry the full 64-drug union, but every headline statistic, the modality table, and Figures 1–3 are computed on the 40 IRA-negotiated drugs only. The top-50 union is never mixed into the headline stats (it would otherwise pull in non-negotiated drugs like Humira and Lantus). See `analyze.py` and the reconciliation in `docs/FINDINGS.md` §6.

## 3. FDA resolution — the crux (`src/fetch_fda.py`)

Mapping a brand/generic to the right FDA application(s) is the hardest step. Findings that shaped the logic:

- **`products.active_ingredients.name` is the reliable search key.** The openFDA `openfda` block (brand/generic/substance names) is **empty on many originator NDAs/BLAs**, so brand/generic/substance searches *miss the original application*. Example: `openfda.brand_name:"ELIQUIS"` returns HTTP 404 (no match) and `openfda.generic_name:"apixaban"` returns only ANDA generics — but `products.active_ingredients.name:"APIXABAN"` returns the original NDA202155 (2012) plus the NDA220073 reformulation. We search by each active-ingredient token (plus brand/generic as cheap fallbacks), union the results, and **keep only `NDA`/`BLA` originator applications** (ANDA generics dropped).
- **Ingredient-set filter.** A candidate application is accepted if the cohort drug's expected ingredient set is contained in the application's ingredients (handles combinations — both members must be present, which excludes e.g. valsartan-only products when resolving Entresto) **or** the brand name matches.
- **Anchor = earliest original approval.** Year 0 is the **minimum `submission_status_date` among `submission_type == "ORIG"` and `submission_status == "AP"`** across *all* matched applications. This fixes the reformulation trap: a brand search for Imbruvica surfaces a 2022 reformulation (NDA217003), but anchoring to the earliest ORIG-AP correctly yields NDA205552 (2013-11-13).
- **New indications = efficacy supplements.** Submissions with `submission_type == "SUPPL"`, `submission_status == "AP"`, and class **`EFFICACY`** (detected via `submission_class_code == "EFFICACY"` — more robust than the sometimes-absent `submission_class_code_description`). Events are **deduplicated by date** across all of a molecule's applications (e.g. Eliquis supplements #39 and #40 on 2025-04-17 collapse to one event). `years_after_launch = (event_date − anchor_date) / 365.25`.
- **Modality** is read from the **anchor application's prefix**: `NDA` → small molecule (clock 9), `BLA` → biologic (clock 13).
- **Indication text** is best-effort from the openFDA `label` endpoint (`indications_and_usage`); missing for some drugs.

**HTTP etiquette & caching.** Descriptive User-Agent; ~0.3s between live calls; exponential backoff on 429/5xx; a malformed single query (HTTP 400, e.g. a combination generic with punctuation) is skipped (logged) rather than fatal, and the other search angles still resolve the drug. Every raw JSON response is cached to `data/raw/fda/`.

**Documented FDA limits.** openFDA caps results at 1,000 per query (not hit at our cohort size). Efficacy supplements are a **proxy** for "new indications": they capture most new-disease approvals but also some population/line-of-therapy expansions and can miss a handful of original-label indications. This biases indication counts slightly upward and is consistent across modalities, so cross-modality comparisons remain meaningful.

## 4. CMS spend (`src/fetch_cms.py`)

- **UUID discovery, not hardcoding.** Dataset UUIDs change yearly, so we fetch the CMS open-data catalog (`https://data.cms.gov/data.json`) and match the exact titles "Medicare Part D Spending by Drug" and "Medicare Part B Spending by Drug" (the annual, not Quarterly, datasets), reading the dataset UUID from the distribution's `accessURL`. The data-api is then paginated (`size=5000`) and every page cached to `data/raw/cms/`.
- **Latest year = 2023** (series 2019–2023).
- **Part D** carries per-manufacturer rows plus an `Mftr_Name == "Overall"` aggregate — we keep the Overall row to avoid double-counting (3,598 drugs).
- **Part B has no manufacturer column** (it is HCPCS-based); a drug can span multiple HCPCS rows, so Part B spend for a drug is the **sum** of its matched rows, whereas Part D (already one Overall row per drug) takes the single value.
- **Join FDA↔CMS** has no shared key: we normalize names (uppercase, strip salts/forms/punctuation) and match exact-then-fuzzy (`rapidfuzz`, token-sort ratio ≥ 88). Spend is looked up in **both** Part D and Part B for every drug (so Part B physician-administered biologics like Orencia/Entyvio get their dominant Part B spend), and `total_medicare_spend = Part D + Part B`. Salt/form stripping covers e.g. "Dapagliflozin Propanediol" → dapagliflozin, "Nintedanib Esylate" → nintedanib.

## 5. Orphan enrichment (`src/fetch_orphan.py`)

The FDA OOPD "Search Orphan Drug Designations and Approvals" database has **no JSON API** and sits behind Akamai bot management. The pipeline: (1) GET the search page to obtain Akamai session cookies (`_abck`, `bm_sz`); (2) **POST** the ColdFusion form (`OOPD_Results.cfm`, `Output_Format=Detailed`) per drug's primary ingredient — GET is blocked with 503; (3) parse the labeled text output (`Generic Name`, `Orphan Designation`, `Orphan Designation Status`, `Marketing Approval Date`) into structured records; (4) cache the raw HTML per drug to `data/raw/orphan/`. If the site is unreachable, `orphan_status` falls back to `"unknown"` and the pipeline proceeds (orphan is enrichment, non-blocking).

`orphan_status ∈ {orphan_approved, designated_not_approved, none, unknown}`. `serial_orphan_candidate` = ≥2 distinct *approved* orphan indications. Validation: Imbruvica (13 distinct), Revlimid (9), Calquence (3) flag true; Eliquis flags `none` — all correct.

**Serial-orphan precision.** The OBBBA exemption requires multiple orphan indications **and no approved non-orphan indication**. `serial_orphan_candidate` (≥2 orphan indications) alone is over-inclusive (e.g. Enbrel, Stelara, Otezla carry orphan designations *plus* large non-orphan markets like RA/psoriasis). `analyze.py` therefore computes a **strict** flag: a multi-orphan drug whose FDA label indications text contains no clearly-common disease keyword. The keyword list covers common autoimmune/metabolic/CNS diseases **and common (non-orphan) solid tumors** (renal cell, endometrial, non-small-cell lung, colorectal, melanoma, breast, prostate, hepatocellular, ovarian, gastric, bladder, head-and-neck). This is a documented heuristic; it yields **4** plausible OBBBA serial-orphan drugs: **Calquence, Imbruvica, Ofev, Pomalyst** (all-rare leukemias/lymphomas, myeloma/Kaposi, pulmonary fibrosis). **Lenvima is correctly excluded** — its label includes renal cell and endometrial carcinoma, both non-orphan. `headline_stats.json` records the exclusion reason for every multi-orphan drug. Each candidate's orphan/non-orphan basis is printed in `docs/FINDINGS.md` §4.

## 6. Analysis (`src/analyze.py`)

**Canonical cohort = the 40 IRA-negotiated drugs.** Every headline number, the modality table, and Figures 1–3 are computed on these 40 only (30 small molecule + 10 biologic). The broader 64-drug union (incl. top-50 Part D spenders) is reported only as context and is never mixed into the stats. `docs/FINDINGS.md` prints an explicit old→new reconciliation for every number that changed when the cohort was locked.

- **Unit of analysis matters.** Item 1 ("20 of 30") counts **drugs** that gained ≥1 indication in the window; item 2 ("% after clock") counts **indications**. Different denominators.
- **Yr 7–9 window** (small molecules) / **yr 11–13** (biologics) = `[clock_year − 2, clock_year]`. A drug is "in window" if ≥1 indication's `years_after_launch` falls in it.
- **After clock**: `years_after_launch ≥ clock_year`. **Back half of window**: `years_after_launch > clock_year / 2`. Both computed on the 289 efficacy-supplement events of the 40 negotiated drugs.
- **EPIC balance check — small molecules only.** EPIC moves *only* the small-molecule selection clock (yr 7 → 11); biologics already sit at yr 11 and are **unaffected**, so they cannot be removed by EPIC. We therefore count only the **30 negotiated small molecules** that were < 11 years past first approval at their cycle's selected-drug announcement (Cycle 1: 2023-08-29; Cycle 2: 2025-01-17; Cycle 3: 2026-01-27): **19 of 30** ($65.7B). Per cycle: 5/7, 8/15, 6/8. (Public Citizen's published "5 of the first 10, 8 of the next 15" counts *all* selected drugs incl. biologics; the 5 and 8 blocked are the small molecules — consistent with our count.)

## 7. Validation / sanity checks

- Every indication event date is verified to fall on/after the anchor approval date (0 violations in the current run).
- Modality is derived solely from the application prefix.
- Drugs with 0 resolved originator applications are flagged in the run summary (currently: Arexvy, Shingrix).
- 62 of 64 cohort drugs resolved (97%); 64/64 have spend; 40/40 negotiated have spend.

## 8. Known limitations (do not hide)

1. **Efficacy supplements are a proxy** for new indications (see §3).
2. **Cycle 3 (IPAY 2028) MFPs are not published** until ~Nov 30, 2026; `mfp_usd` is `null` for those drugs — never imputed.
3. **Two vaccines unresolved** (Arexvy, Shingrix): CMS lists their generic as an antigen description ("Rsvpref3 Antigen/As01e/PF") that does not map to FDA active-ingredient names; they are non-negotiated top-spend entries and are left with null FDA fields.
4. **Insulin aspart (NovoLog/Fiasp)** resolves as a **biologic** (BLA, clock 13) because FDA transitioned insulins to BLAs in March 2020; the original approval date (2000) is preserved. Mechanically correct under the application-prefix rule and clinically defensible (insulin is a biologic), but worth flagging as a modality edge case.
5. **Xolair Part B classification is contested.** CMS's Cycle 3 press release headlines four Part B drugs (Botox, Cimzia, Orencia, Entyvio); some analyses add Xolair under a "majority of gross spending" definition. We label Xolair Part B with a note; spend is looked up in both parts regardless, so totals are unaffected.
6. **Top-50 "eligibility" is approximate** (§2).
7. **Fuzzy name matching** can mis-join in principle; exact normalized matching is tried first and the threshold is conservative (≥88). No mismatches observed in the current cohort.
