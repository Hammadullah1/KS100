# Real-data research and GitHub handoff — 20 September 2026

## What now works

The project can train and compare its logistic-regression and LightGBM models directly from a local daily index CSV. No paid API, GPU or extra library was required. The 1,240-row KSE-100 snapshot spans 20 September 2021 through 18 September 2026. The additional real Brent snapshot was fetched from [FRED's EIA Brent series](https://fred.stlouisfed.org/series/DCOILBRENTEU).

The command `psx snapshot-research` refreshes model fits every 21 recorded sessions, uses only matured labels, separates calibration from training, purges labels across boundaries, compares simple baselines, and saves per-date predictions and trained artifacts. It selects a primary from earlier development probability loss before evaluating the later slice. Zero future labels are invented. An interrupted or completed output directory cannot be overwritten.

The latest period was already seen in earlier experiments. It remains **exploratory**, regardless of whether this new code selected a model before evaluating that slice.

## Tested changes

- Full-fit refitting after LightGBM chooses its stopping iteration inside the training block.
- Price/volume features, then additional 60-session trend, drawdown, downside volatility, relative volatility and RSI features.
- Raw probabilities compared with calibrated probabilities mixed 50:50 with a daily refreshed frequency baseline. This fixed mixture reduces overconfidence without tuning against the evaluation outcomes.
- Delayed Brent returns and volatility, with age and missing/stale indicators. The seven-calendar-day availability delay is a research assumption; historical release dates and revisions are not verified. This is not point-in-time macro evidence.

## Results so far

Both in-project experiments evaluated 252 common forecast origins from 9 September 2025 to 11 September 2026. Development labels crossing that boundary were excluded. Five-session outcomes overlap and are not independent trials.

| Comparison | Next session accuracy | Next five sessions accuracy |
|---|---:|---:|
| Daily refreshed frequency baseline | 49.6% | 58.7% |
| Logistic price/volume, calibrated and mixed with baseline | 52.8% | 59.1% |
| Logistic with Brent, calibrated and mixed | 51.2% | 57.9% |
| LightGBM with Brent, calibrated and mixed | 51.2% | 57.9% |

These selected comparisons are not a newly validated winning model. Complete tables contain all attempted variants, including poor results. The price-only experiment selected raw regime LightGBM for the next-session horizon from development; it scored 50.0% later. Adding Brent changed that development choice to raw Brent logistic, which scored 48.4% later and had worse probability loss. The five-session primary remained the simple frequency baseline. The 59.1% descriptive ML result has worse probability loss than the baseline and was not the development-selected primary.

**Conclusion: high accuracy has not been achieved.** More features did not establish a stable advantage. Preserve failed attempts. Further improvements require better dated features and genuinely new forward evidence, not repeatedly choosing whichever model happens to score highest on this year.

Local detailed outputs (ignored by Git):

- `reports/local/snapshot-v1/RESULTS.md`: price/volume and regime comparisons, 22.3 seconds on this machine.
- `reports/local/snapshot-brent-v1/RESULTS.md`: additional Brent comparisons, 31.8 seconds.
- Each directory contains frozen protocols, development selections, boundary evidence, all predictions and last trained artifacts.
- `reports/local/pytest-model-improvements.xml`: 54 passing Python tests.
- Both experiment directories now contain passing `verification.json` audits: labels and scores were independently recomputed, chronological boundaries checked, and saved models reproduced their final-batch predictions. Formatting/lint and all four GitHub workflow static checks passed. These checks establish local correctness, not forecasting skill or a successful hosted run.

## Daily app architecture

1. After final closing data becomes available, GitHub Actions fetches/validates approved index and constituent data.
2. The active reviewed models calculate next-session and five-session probabilities. Research retraining produces candidates separately.
3. Immutable forecast records retain issue time and model version; subsequent outcomes measure actual forward performance.
4. The existing allowlisted JSON bundle carries probabilities, abstentions, forecast horizons, freshness and evaluation evidence.
5. The Android-installable frontend loads that bundle from GitHub Pages. A permanent API server is unnecessary for daily forecasts.

The existing daily workflow already validates, issues, scores and packages an approved dataset; there is still no approved automated PSX collector or active production model. A scheduled wakeup is not proof that the closing data is available. Late/failed updates must display stale or unavailable status.

The current snapshot is **the index**, not prices for all 100 companies. Extending to the constituents requires dated membership, company OHLCV, adjusted prices/corporate actions, and per-stock/pooled-model evaluation. A 60% estimated probability is not a guarantee or measured accuracy for that stock.

## GitHub setup prepared

The research workflow now has an explicit manual `snapshot` mode. It reads `research-inputs/kse100_daily.csv` and optional `research-inputs/brent_fred.csv` in the separate private state repository. It writes results to a run-specific private directory and never publishes them or promotes the model. Scheduled approved-data research retains its existing behavior. Failed research is reported as failure after diagnostics are preserved.

Repository URL/account access are still needed. No remote or GitHub CLI is configured on this machine. The requested repository has not been created or pushed, and no hosted run is claimed.

Standard GitHub-hosted runners in public repositories are free under the currently documented [Actions billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions). Use standard Ubuntu runners, bounded runtimes and storage, and review actual account settings before enabling schedules. Keep private source data outside the public code repository. See [the runbook](RUNBOOK.md) for account, state, publication and recovery settings.

## Next evidence to collect

Freeze a candidate and log forecasts before their outcomes on future sessions. Compare accuracy, both directional recalls, probability loss and coverage with the refreshed baseline. Acquire dated USD/PKR and verified Brent publication vintages before using them for a production performance claim. Audit longer index history before merging it. A more complex model or larger search alone is not evidence of higher accuracy.
