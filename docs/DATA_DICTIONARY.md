# Data Dictionary

Two processed datasets are produced by `python -m src.build_dataset`. Spend figures are Medicare **gross** spending for the latest available year (**2023**). Monetary fields are USD. Nullable fields are blank/empty in the CSV.

---

## `data/processed/innovation_clock_master.csv` — LONG

One row per **(drug × indication event)**. A drug with zero efficacy supplements still gets a single row with null event fields, so no drug is dropped. **424 rows** in the current build.

| Column | Type | Description |
|---|---|---|
| `drug_brand` | string | Brand name as carried in the cohort (e.g. `Eliquis`). |
| `drug_generic` | string | Active ingredient / generic (e.g. `apixaban`; combinations use `/`). |
| `active_ingredient` | string | Normalized ingredient token(s), `; `-joined (used for matching). |
| `fda_application_number` | string | Anchor application — earliest original approval (e.g. `NDA202155`). Null if unresolved. |
| `modality` | string | `small molecule` (anchor = NDA) or `biologic` (anchor = BLA). Null if unresolved. |
| `original_approval_date` | date (ISO) | Year 0: earliest `ORIG`+`AP` submission across the molecule's apps. |
| `clock_year` | int | IRA price-effective year: 9 (small molecule) or 13 (biologic). |
| `indication_event_date` | date (ISO) | Date of this new-indication event (FDA efficacy supplement). Null if the drug has none. |
| `years_after_launch` | float | `(indication_event_date − original_approval_date) / 365.25`. |
| `indication_text` | string | Best-effort `indications_and_usage` label text (drug-level; may be null). |
| `is_after_clock` | bool | `years_after_launch ≥ clock_year` (the indication arrived in the price-controlled period). Null if no event. |
| `event_app_number` | string | Which application carried this efficacy supplement. |
| `orphan_status` | string | `orphan_approved` / `designated_not_approved` / `none` / `unknown`. |
| `ira_cycle` | int | IRA negotiation cycle (1, 2, 3) or blank if non-negotiated. |
| `mfp_usd` | float | Maximum Fair Price (30-day-supply equivalent). Blank for Cycle 3 (not yet published) and non-negotiated drugs. |
| `part_d_spend_latest_usd` | float | Medicare Part D gross spend, latest year. |
| `part_b_spend_latest_usd` | float | Medicare Part B gross spend, latest year. |
| `spend_year` | int | Year the spend figures refer to (2023). |
| `source_urls` | string | `; `-joined provenance URLs (CMS fact sheet + openFDA). |

---

## `data/processed/innovation_clock_summary.csv` — WIDE

One row per **drug**. **64 rows** in the current build.

| Column | Type | Description |
|---|---|---|
| `drug_brand` | string | Brand name. |
| `drug_generic` | string | Generic / active ingredient. |
| `active_ingredient` | string | Normalized ingredient token(s), `; `-joined. |
| `fda_application_number` | string | Anchor (earliest-original-approval) application. |
| `all_app_numbers` | string | All matched originator applications, `; `-joined. |
| `modality` | string | `small molecule` / `biologic` / blank if unresolved. |
| `clock_year` | int | 9 or 13. |
| `original_approval_date` | date (ISO) | Year-0 approval. |
| `ira_cycle` | int | 1 / 2 / 3 or blank. |
| `ira_effective_year` | int | Year the negotiated MFP takes effect (2026 / 2027 / 2028). |
| `mfp_usd` | float | Maximum Fair Price (30-day equiv). Blank where not published / not negotiated. |
| `in_negotiated` | bool | Drug is in IRA Cycles 1–3. |
| `in_top_spend` | bool | Drug is in the top-50 Part D by spend. |
| `cohort_source` | string | Why it's in the cohort (`IRA Cycle N` or `Top-50 Part D spend`). |
| `part` | string | Primary Medicare part (`Part D` / `Part B`); see Xolair caveat in METHODOLOGY. |
| `orphan_status` | string | See above. |
| `serial_orphan_candidate` | bool | ≥2 distinct *approved* orphan indications (coarse; see METHODOLOGY §5). |
| `n_orphan_indications_approved` | int | Count of distinct approved orphan indications. |
| `part_d_spend_latest_usd` | float | Part D gross spend, latest year. |
| `part_b_spend_latest_usd` | float | Part B gross spend, latest year. |
| `total_medicare_spend_latest_usd` | float | Part D + Part B. |
| `spend_year` | int | 2023. |
| `n_indications_total` | int | Number of new-indication (efficacy supplement) events. |
| `n_indications_after_clock` | int | Events with `years_after_launch ≥ clock_year`. |
| `n_indications_in_window` | int | Events in `[clock_year−2, clock_year]` (yr 7–9 small molecule / 11–13 biologic). |
| `window_lo_yr`, `window_hi_yr` | int | The window bounds for this drug's modality. |
| `last_indication_year` | int | Calendar year of the most recent new indication. |
| `source_urls` | string | Provenance URLs. |

---

## Supporting files

- **`data/processed/dashboard_data.json`** — drug-level records (incl. per-indication `years_after_launch`) embedded into `dashboard/index.html`.
- **`data/processed/headline_stats.json`** — the computed headline numbers (consumed by the dashboard summary panel and the fact sheet).
- **`data/raw/policy_facts.json`** — cited policy facts (statement + source URL/org/date) used in the fact sheet.
- **`data/raw/{fda,cms,orphan}/`** — cached raw API responses; presence makes reruns offline and deterministic.
