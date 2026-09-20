# Implementation evidence

The local Python pipeline, bounded evaluation harness, Android-installable PWA and gated automation are implemented. The production dashboard contains no forecasts because no lawful PSX history or validated production model is available. No market accuracy or deployment success is claimed.

**Review update, 2026-09-19:** the evaluation configuration and rolling company reports were corrected after the original verification below. The current Python suite has **41 passing tests**, and both horizons completed four synthetic development folds under protocol v2. Lint and format checks passed. See [the review](REVIEW_2026-09-19.md); earlier frontend/browser results were not rerun for this backend change. Automated PSX fetching remains unimplemented pending a verified permitted source.

## Acceptance mapping

| Plan requirement | Local evidence |
| --- | --- |
| 1-2 Publication cutoff and immutable revisions | tests/test_timing_and_data.py: future-release/revision and availability-evidence tests |
| 3 Grouped chronological split and overlap purge | tests/test_evaluation.py: all-stage date grouping and reserved-final tests |
| 4 Holiday/five-session maturity | tests/test_timing_and_data.py: explicit calendar and maturity tests |
| 5 Corporate-action treatment | Split/bonus/rights parameterized tests and unresolved-action feature suppression |
| 6 Missing/no trade/zero distinction | Data tests plus company missing-exposure indicator regression |
| 7 HTTP 200 error page | tests/test_operations.py: parser failure and bounded retry tests |
| 8 Failed/stale source | Source gate tests and issuance regression with missing reference close |
| 9 Idempotent issuance | Original issuance preserved on retry; missed boundary rejected |
| 10 Disjoint fit/blend/calibration/selection/evaluation | Grouped stage tests, fit preprocessing test and recorded fixture stage dates |
| 11 Probability/model/target contracts | Pydantic contract tests, target/model issuance gates and browser cross-field validation |
| 12 Partial/corrupt publication | Atomic-pointer regression, hash validation, rollback and browser last-good-cache test |
| 13 Expired offline forecast | Browser expired-cache test: corrupt update, service worker reload, network offline, visibly historical |
| 14 Public artifact hygiene | Production build scanner checks current and retained bundle histories, raw Parquet, maps and credential patterns; permission tests |
| 15 Mobile/accessibility/offline | Chromium Pixel 7 emulation at 320/360/393 CSS px, axe checks, manifest/icons, offline tests; physical Android installation remains pending |
| 16 Reproducible setup | Fresh uv environment, locked pnpm reinstall, fixture generation/validation, backup/restore and successful production build |

See ../reports/pytest.xml (35 tests), ../reports/browser-results.json (5 tests), ../reports/local-verification.json and ../reports/qa/. Six frontend unit/component tests also passed. Formatting, lint, schema drift and all four static workflow checks passed.

## Research boundaries

Synthetic development runs contain four chronological folds per horizon; separate reserved-test runs contain 252 dates per horizon. These verify software execution only. The original reports are preserved; they predate the addition of date-balanced coverage and selected-correctness fields. They are not silently rewritten to suggest a new final-test opening.

Pooled-company training uses company price history and dated bank-sector/exporter context with a distinct missing-exposure flag. Forward company scorecards are withheld publicly below 200 outcomes and 100 dates. At 63 matured dates, forward deterioration can suppress subsequent probabilities; immutable earlier forecasts remain unchanged.

Optional driver groups are disabled without audited vintages. Their as-of features and ablation runner are implemented, but no driver benefit is established. A winning driver model still requires a matching production inference version; mismatched features fail closed. The neural challenger is deferred under the plan's prerequisite of lawful timestamped news and measured cheaper-feature benefit.

## Remaining external dependencies

1. Lawfully retained PSX history and explicit rights for training and public derived forecasts; dated exchange calendar, corporate actions, historical membership/liquidity and release-time evidence. Registry switches alone are not permission evidence.
2. Optional driver source credentials and permitted release vintages only after source review. No optional key is needed to run the current empty dashboard.
3. Chosen GitHub account, public code repository, private state repository and the narrowly scoped settings in RUNBOOK.md. Hosted CI, manual release and deployment smoke checks have not run. Schedules remain disabled.
4. Physical Android Chrome installation/offline verification after an HTTPS release. Mobile emulation is not physical-device evidence.
5. Future prospective observations, which cannot be manufactured or accelerated by local tests.

Git is initialized locally; no remote publication or commit identity was invented. The exact account variables, secret names, release order and recovery steps are documented in RUNBOOK.md. Source access and deployment evidence remain explicitly pending in the machine-readable reports.
