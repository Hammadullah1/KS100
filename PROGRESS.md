# Implementation progress and evidence

The build plan remains authoritative. A completed local component is not a verified live phase.

## Real-data model continuation — 2026-09-20

Added `psx snapshot-research`, using the existing logistic/LightGBM implementations with 21-session refresh, full-fit LightGBM refitting, separate probability calibration, fixed shrinkage, trend/volatility features and daily refreshed baselines. A FRED/EIA Brent snapshot was fetched successfully and compared using an explicitly assumed seven-calendar-day availability delay. Local datasets and trained artifacts remain in ignored directories.

Both horizons were trained and evaluated on the real 1,240-row index snapshot. This history had already been inspected; all new results are exploratory. **No reliable accuracy advantage has been established.** Detailed results and limitations: [model research](docs/MODEL_RESEARCH_2026-09-20.md). The current models predict the index; individual-stock probabilities require constituent-level history and corporate-action data.

The expanded Python suite has **54 passing tests**, including causal feature construction, immature-label exclusion, purged rolling stages, Brent delay/staleness, model reproduction and rejection of snapshot artifacts by production promotion. GitHub research now supports a manual private-snapshot mode; hosted execution, repository/account setup, daily source ingestion and deployment remain unverified. The historical implementation notes below describe the earlier state of the project.

## Review continuation — 2026-09-19

An independent review found and repaired two evaluation defects: an impossible 100-date requirement inside a 63-date threshold-fitting block, and rolling pooled-company reports grouped by rows rather than complete dates. Protocol v2 separates exploratory fitting support from the unchanged final accuracy-claim criteria. See [the review and remaining work](docs/REVIEW_2026-09-19.md).

The original 35-test suite passed before changes; the expanded suite now has **41 passing Python tests** ([review report](reports/review-v2-pytest.xml)). New synthetic development runs use `reports/review-v2/`; original reports and reserved tests are preserved. The earlier frontend/browser verification below is historical evidence and was not rerun for these backend-only changes. Real data access, market accuracy and deployment remain unverified.

## Original implementation evidence

| Phase | Local checklist | Exit evidence / remaining dependency |
| --- | --- | --- |
| 0 Feasibility | [x] Source audit, explicit TR/PR targets, registry, cost assumptions | [Source audit](docs/SOURCE_AUDIT.md), [machine-readable audit](reports/source-audit.json). Permitted free PSX history and public forecast rights are unresolved. |
| 1 Skeleton | [x] Python CLI, locked dependencies, generated contracts, fixture pipeline and empty PWA | Local fixture snapshot and production build executed. [Setup](README.md). Hosted CI still pending account/repository. |
| 2 Data | [x] Gated/manual adapters, explicit calendar, adjustments, vintage snapshots, quality checks | [35 passing Python tests](reports/pytest.xml). Real dated history/calendar/actions/membership remain unavailable. |
| 3 Baseline research | [x] Baselines, logistic/LightGBM, grouped/purged stages, calibration, selection, uncertainty | [1-session fixture development](reports/fixture/h1/historical.json), [5-session](reports/fixture/h5/historical.json), [1-session reserved test](reports/fixture/h1/final-test.json), [5-session reserved test](reports/fixture/h5/final-test.json). Synthetic software evidence only; real market evaluation blocked. |
| 4 Indirect drivers | [x] Availability/age features, deduped event features, same-date ablation runner | [Unavailable-group report](reports/fixture/drivers/ablations.json). No group has demonstrated a market benefit. Permitted release vintages needed. |
| 5 Challenger | [x] Bounded blend/calibration/selection; [x] documented decision to defer neural work | No permitted timestamped news corpus or measured cheap-feature improvement. No neural accuracy or runtime claim. |
| 6 Product | [x] Overview/watchlist/evidence/drivers/health, manifest/icons, verified bundles, client-clock staleness | Production build and 6 frontend tests passed; 320/360/393 px and accessibility checks passed. Offline reload, expired-cache/corrupt-publication check and visual review passed. Real forecasts and physical Android check pending. |
| 7 Automation/release | [x] Pinned CI/daily/recovery/research/Pages workflows, budget gate, state backup/restore, runbook | [Static workflow check](reports/workflow-static-check.json), [pins](reports/action-pins.json). Schedules disabled; [hosted release evidence pending](reports/release-evidence.json). |
| 8 Forward observation | [x] Immutable issuance, matured outcomes/corrections, forward scoring and deterioration-based issuance suppression | [Research status](reports/research-status.json). No real prospective forecasts exist; future performance cannot yet be observed. |

## Verified local results so far

- Python acceptance suite: **35 passed**; no failures in the latest recorded run.
- Frontend unit/component suite: **6 passed**.
- Production build: successful; public bundle integrity and forbidden-artifact checks passed.
- Synthetic historical evaluation: **4 development folds per horizon**.
- Synthetic reserved evaluation: **252 dates per horizon** under the frozen protocol.
- Backups/restoration, source gates, unchanged outcomes, delayed releases, revisions, corporate-action factors, stale prices, duplicate issuance and interrupted publication have dedicated tests.
- Browser tests caught a font import failure, then an offline cache mismatch. Both were repaired and the final five browser tests passed. Failed runs are not counted as passed.

## Completion boundaries

**Software built:** all unconditional local phases implemented and checked; conditional live-data and challenger work remains gated.
**Data access verified:** documentation and permission findings only; no live PSX feed.
**Model evaluated:** synthetic test datasets only; no measured market accuracy.
**Deployment verified:** no.
**Future performance:** not yet observable.

Local checks are complete. the remaining external inputs are a lawful historical dataset and rights evidence, the chosen GitHub repositories/account settings, and an authorized release plus physical Android check.

## Final local verification

- [Machine-readable verification](reports/local-verification.json): fresh locked Python environment, recreated locked frontend dependencies, fixture validation and verified backup/restore.
- [Browser results](reports/browser-results.json): **5 passed**, including actual offline reload of an expired cached forecast after a corrupt publication.
- [Mobile screenshot](reports/qa/dashboard-393.png), [offline screenshot](reports/qa/offline.png), [expired cached forecast](reports/qa/expired-cache.png).
- [Acceptance mapping and remaining dependencies](docs/IMPLEMENTATION_REPORT.md).
- Latest Python suite: **35 passed**. Frontend suite: **6 passed**. Production build, schema drift check, formatting/lint and static workflow checks passed.
