# Build plan for Codex: KSE-100 probability dashboard

Prepared: 18 September 2026. This document is a complete implementation brief. It consolidates and supersedes the earlier project blueprint and model research where implementation choices differ. It does not report a trained model, measured prediction accuracy, a verified production data feed, or a deployed app.

## 1. The instruction to Codex

Build a personal PSX forecasting project with an Android-installable web app, public source code on GitHub, scheduled data updates, and honest probability estimates. Start with the KSE-100 index, then add a small, liquid constituent-stock watchlist. Include indirect market drivers when their data is permitted, historically available, and measurably useful.

The priorities, in order, are:

1. Trustworthy evaluation and useful probabilities.
2. Correct, timely data and visible failures.
3. A working, understandable Android dashboard.
4. Zero required subscription or hosting expenditure.
5. Efficient operation and maintainable code.

Implement the phases in this document. Make routine engineering decisions independently and record them. Complete everything that can be built and tested locally before requesting any missing account access or consequential publication decision. Never substitute fabricated prices, probabilities, or accuracy for an unavailable dependency. If a source is blocked, finish the source adapter interface, clearly labelled fixtures, tests, and empty-state UI while recording the live-data blocker.

Do not make model complexity a success criterion. A simple model that survives realistic evaluation is an acceptable winner. An app reporting “No demonstrated forecasting advantage yet” is also an honest research result. A polished dashboard with invented confidence is not completion.

## 2. Correct the assumptions before building

### KSE-100 is an index, not a single stock

The index and its constituent companies need separate forecasts. A market-level probability cannot be copied onto every company. Start the app on an index overview; show company forecasts only when those models and data are ready.

PSX distinguishes the headline KSE-100 total-return series from KSE100PR, its price-return counterpart. Use explicit instrument identifiers and return-basis labels. Do not splice their histories or describe one as the other. See the [PSX index descriptions](https://www.psx.com.pk/psx/product-and-services/indices) and [official index brochure](https://www.psx.com.pk/psx/themes/psx/uploads/KSE-100-and-KSE100-PR-Brochure-Jun-2025-Updated.pdf).

### A smoother chart still contains noise

Combining companies can reduce some company-specific fluctuations. It does not remove common market shocks, unexpected announcements, changing investor behaviour, or uncertainty about tomorrow. Index membership alone also does not make an individual constituent free of noise.

Treat “the KSE-100 might be easier to predict” as a hypothesis to test. Measure predictability on untouched future periods. Do not smooth the target using future prices or discard difficult dates to make the model look accurate.

### Three numbers must remain separate

- **Forecast probability:** the model's estimate for one defined future event.
- **Historical correctness:** the proportion of predictions that proved correct in a specified evaluation period.
- **Coverage:** the proportion of eligible opportunities on which the system issued a directional signal.

An 80% forecast is not proof of 80% measured accuracy. High correctness on a tiny, retrospectively chosen subset is not evidence that the app will be highly accurate every day. No accuracy percentage is promised by this plan.

## 3. Product scope and defaults

| Decision | Default |
| --- | --- |
| Primary instrument | Official KSE-100 headline index, clearly labelled total return |
| Optional second index | KSE100PR, independently identified and evaluated if sufficient history exists |
| Company coverage | Initially 10–20 liquid constituents selected using information available at each selection date |
| Horizons | Next 1 trading session and next 5 trading sessions; separate models and scorecards |
| Forecast frequency | Once after each completed PSX session and successful data validation |
| Device | Responsive PWA that can be added to an Android home screen |
| Hosting | GitHub Pages where current terms and data rights permit; Vercel Hobby is an alternative for eligible personal use |
| Compute | Scheduled CPU jobs; no continuously running prediction server |
| Accounts | No broker connection, trading execution, payments, or public user registration in version 1 |
| Access | Personal research dashboard; public publication only for content permitted for public display |
| Spending | No paid APIs, GPU rental, paid AI calls, paid domains, or automatic paid upgrades |

Use an exchange-session calendar, not a generic Monday–Friday counter. Handle holidays, special closures, Friday sessions, and announced schedule changes. Store times in UTC and show them in Asia/Karachi.

## 4. Exactly what the model predicts

### 4.1 Primary direction target

For instrument i, reference session t, and horizon h:

    return(i,t,h) = reference_series(i,t+h) / reference_series(i,t) - 1
    up_label(i,t,h) = 1 if return(i,t,h) > 0, otherwise 0
    p_up = P(up_label = 1 | information available at forecast cutoff)
    p_not_up = 1 - p_up

The interface labels are **“Up”** and **“Down or unchanged.”** Preserve that second label: its probability includes an exactly unchanged close. Show the actual frequencies of up, down, and unchanged outcomes in evaluation. Do not silently remove unchanged observations.

For company price forecasts, reference_series is the close adjusted for splits, bonus shares, and rights according to a documented adjustment policy. Cash dividends are excluded from this price-direction target. A separate total-investment-return target may include them later. For the headline index, use the official total-return index series as supplied and identified.

This binary definition is the version-1 choice. It replaces the earlier proposal for an unspecified “near-flat” band. An optional later three-class product can predict rise/near-flat/fall, but it must predeclare its bands, receive a new target identifier, and have a separate scorecard. Never change the definition to improve a reported result.

### 4.2 Forecast timestamps and maturation

Every forecast records reference session, reference close, cutoff time, issue time, target session, horizon, model version, feature version, and data snapshot identifier.

- The cutoff is the actual time at which the pipeline freezes its information set.
- Only information available by that cutoff may enter the forecast.
- A forecast for the next session is published before that session opens. If a delayed run misses that boundary, mark that issuance as missed; do not backdate it.
- Five-session outcomes mature only after the fifth exchange session's validated close is available.
- Retraining and evaluation use only matured labels available at that job's cutoff.
- Changes to a completed session's official close create an auditable correction; they do not silently rewrite the original forecast record.

### 4.3 Signal selection is separate from prediction

Store probabilities for valid forecasts. Issue a directional signal only if the prevalidated selection policy allows it. Otherwise show “No strong signal” with an explanation such as insufficient evidence, weak probability, stale input, or unusual conditions.

The app is allowed to abstain. It must disclose the resulting coverage. “No strong signal” is not an unchanged-price forecast.

### 4.4 Prediction does not imply executable profit

The reference close is already in the past when an evening forecast is produced. Any trading simulation enters at a realistically available subsequent price, initially the next session's open, with explicit execution assumptions and costs. It cannot buy at the same close that generated the prediction.

The index itself is a benchmark, not an automatically tradable instrument. Do not report investable index profits without defining a permitted tradable proxy and its tracking, liquidity, and costs. Do not assume short selling is available for every company. A directional research score and a long-only trading simulation are separate outputs.

## 5. Indirect drivers: what to investigate and why

The following relationships are hypotheses. Their signs can change by company, sector, economic regime, and whether an announcement was expected. The model must test them; the app must not describe feature importance as proof of causation.

### Priority A: establish the first useful baseline

| Driver group | Candidate inputs | Why it may matter | Timing and source requirement |
| --- | --- | --- | --- |
| Own market history | Lagged returns, trailing volatility, volume/value traded, gaps, range, liquidity | Momentum, reversals, stress, and trading conditions | Final permitted PSX observations; no unverified intraday value treated as a final close |
| Market and sector context | Index returns, sector returns, breadth, constituent concentration, lagged relative performance | Companies share exposure to broad market conditions | Historical membership and weights; avoid using today's constituents throughout history |
| Brent oil | Lagged spot-price changes, multi-session trend, volatility | Import costs, inflation and currency pressure; different effects on producers and users | [EIA](https://www.eia.gov/opendata/documentation.php) or [FRED Brent](https://fred.stlouisfed.org/series/DCOILBRENTEU), using actual publication availability |
| USD/PKR | Lagged changes, volatility, interaction with commodity prices | Import bills, export receipts, foreign debt and investor returns | [SBP economic data](https://www.sbp.org.pk/economic-data); distinguish exchange-rate definitions |
| Domestic rates | Policy rate, KIBOR and available government yield measures; changes and curve slope | Financing costs, bank income, valuations and alternatives to equities | SBP series and announcement timestamps; effective date is not necessarily announcement date |
| Investor flows | Foreign and local net buying, sector flows, trailing cumulative flows | Demand, selling pressure and changing participation | [NCCPL market information](https://www.nccpl.com.pk/market-information); verify FIPI/LIPI history, units, rights and release times |

First implement a price-only baseline, then add the available A groups one at a time. A delayed macro source is usable as delayed information; it must never be disguised as current information.

### Priority B: economic releases and identifiable events

| Driver group | Candidate inputs | Treatment |
| --- | --- | --- |
| Inflation | CPI change, latest inflation level, trend; selected weekly inflation information | Use [PBS releases](https://www.pbs.gov.pk/press-release/) at their publication times, not at the start of their reference month |
| External position | FX reserves, current account, trade balance, remittances | Use available SBP vintages and release calendar; include age of the latest observation |
| IMF developments | Staff agreement, board approval, review, disbursement | Separate event types and dates from [IMF Pakistan](https://www.imf.org/en/countries/pak); do not merge them into one invented event |
| Fiscal policy | Budget, tax or levy changes, subsidies, official borrowing announcements | Use [Ministry of Finance](https://www.finance.gov.pk/) and authoritative notices; record announcement and effective dates separately |
| Corporate events | Results, dividends, rights, buybacks, material notices, scheduled meetings | Source company/PSX disclosures; use publication times, not financial-period end dates |
| Global conditions | Licensed broad equity/risk measures, US rates, selected regional-market moves | A same-date US closing value is not available at an earlier Pakistan cutoff; apply actual time-zone alignment |
| Policy and disruption events | Verified energy-policy changes, shutdowns, severe weather disruptions and major official policy announcements | Explicit event taxonomy, source links, relevance and timestamps; do not turn rumours into factual features |

An economic “surprise” means actual release minus a contemporaneous expected value. Compute it only when a permitted historical expectation series exists. Otherwise use changes from previous published values and call them changes.

### Priority C: company and sector exposure

Add these only after the core pipeline works and adequate dated histories exist:

- Oil and gas: production, realised prices, exchange exposure, receivables and circular-debt-related announcements.
- Banks: rate changes, deposit/loan mix, credit growth, funding costs, asset quality, and government-security exposure.
- Cement: coal and energy costs, dispatches, capacity utilisation, construction conditions, and pricing.
- Textiles: cotton, energy costs, export demand, exchange exposure, and margins.
- Fertiliser: gas supply/pricing, policy changes, seasonal demand, and company disclosures.
- Autos and other import-dependent businesses: currency, financing rates, imports and production restrictions.
- Across companies: leverage, margins, cash flow, valuation measures and earnings changes, as published at the time.

Candidate sources include official company filings, SBP/PBS statistics and relevant industry publications. Verify each source independently. The planner does not assert that these histories are freely downloadable or licensed for redistribution.

### Exposure interactions to test

Test a small, predeclared group such as Brent change × oil-producer sector; Brent change × USD/PKR change; rate change × bank sector; FX change × disclosed exporter exposure. Use historical exposure classifications where possible. Do not infer every company's exposure solely from its present sector name.

For the index, sector weights and major-company exposures help represent changing composition. Do not derive index probability by taking a weighted mean of constituent up probabilities: that does not model return magnitudes or their dependence.

### The rule for keeping a driver

Each group must pass a chronological comparison with and without that group, using the same dates and targets. Retain it only if the gain is sufficiently stable to justify its maintenance, latency and missing-data cost. Keep unsuccessful experiments in the research log. Avoid searching hundreds of variations and reporting only the winner.

## 6. Data feasibility and permissions come first

Create a source registry and a source-audit report before implementing unattended collection. Publicly viewable data is not automatically licensed for bulk collection, model training or public redistribution. The [PSX portal terms](https://dps.psx.com.pk/) and [data services information](https://www.psx.com.pk/psx/product-and-services/data-services-vending) make this a real project dependency.

For every source, record:

- Official identity, documentation URL, verified endpoint or download mechanism.
- Allowed collection, retention, training, display and derived-output uses, with evidence and review date.
- Authentication requirements, free limits, rate limits and attribution requirements.
- Fields, units, adjustment basis, timezone, history depth and publication schedule.
- Revision behaviour and whether historical publication timestamps or vintages exist.
- Operational owner, parser version, timeout, retry rules and fallback policy.

Keep separate flags for public raw-data redistribution, private storage, training, and public derived forecasts. A library that scrapes a restricted source does not solve its permissions. Private storage also does not confer missing rights.

Implement adapter interfaces for PSX price/index history, corporate actions, SBP, EIA/FRED, NCCPL and disclosures. Enable each live adapter only after the audit passes. Do not invent endpoint paths or assume unofficial APIs are stable. Retain a documented manual-import route for lawfully supplied files.

If free permitted PSX history or public forecast rights cannot be verified, report that exact dependency. Continue building the rest with labelled fixtures. Do not claim the zero-cost production data problem has been solved. Do not purchase data, contact providers, or accept new contracts automatically.

## 7. Data storage and information timing

### 7.1 Required data tables

Implement schema-validated tables for instruments, trading sessions, bars/index observations, corporate actions, membership/weights, macro observations, investor flows, events/news metadata, features, forecasts, outcome records, model registry and pipeline runs.

An observation needs source identifier, instrument/series identifier, observation time or reference period, published-at time where known, available-at time, ingestion time, revision/vintage, units, value, adjustment basis and provenance. Preserve original payload hashes where retention is permitted.

Do not equate the following:

- The month a CPI value describes and the day it became public.
- A company's quarter end and the results announcement date.
- An oil observation date and the time the source published it.
- A recently downloaded revised series and the version investors saw historically.

For live operation, available-at is no earlier than first successful receipt unless reliable publication evidence establishes an earlier time. Historical backfills need documented publication evidence or a conservative, explicitly justified lag. If neither exists, exclude the series from the headline backtest. A later download alone does not establish historical availability.

Use backward as-of joins: every feature must have available-at no later than that forecast's cutoff. Forward-fill a released macro value only within a configured age limit and include its age/missingness. Never backfill from the next release. Do not silently replace unavailable values with zero.

### 7.2 Price integrity

- Check unique keys, ordering, session membership, valid OHLC relationships, nonnegative volume and consistent units.
- Distinguish no trade, suspended trading, a missing observation and a genuine unchanged close.
- Investigate extreme returns against corporate actions and official corrections before treating them as market moves.
- Preserve raw and adjusted series separately, with a tested adjustment policy and vintage.
- Do not forward-fill missing prices to manufacture tradable sessions or outcome labels.
- Exclude unresolved action windows from eligible forecasts with an explicit reason; report exclusions and their frequency.
- Avoid future corporate actions influencing features constructed for earlier forecast origins.

### 7.3 Historical universe

For constituent research, reconstruct membership and liquidity eligibility using information available on each date. Include later removals when they belonged to the historical universe. Do not backtest today's best-known companies as if they were the only available choices years ago.

If historical membership is unavailable, use an honestly labelled fixed-universe experiment with that limitation and withhold claims about the historical KSE-100 constituent universe.

### 7.4 Durable state

Use small partitioned Parquet files and JSON metadata, queried with DuckDB where helpful. GitHub Actions caches and expiring workflow artifacts are accelerators, not the only source of truth.

Default layout: a public code repository and, when necessary and permitted, a separate private state repository holding compact permitted research data, immutable forecast records and small model releases. Keep large raw documents out of Git history. Document retention, growth limits, backup and restore. Never put credentials into either repository.

Use a narrowly scoped credential only if cross-repository writes are needed; explain that setup once the local system is reviewable. A private state repository may still expose restricted content if a workflow copies it into a public artifact: audit every publication path.

If derived forecasts require authenticated access, public static JSON is unsuitable. Document and implement an appropriately protected personal-access option, or leave publication blocked while providing a working local app. An obscure URL is not access control.

## 8. Model development: a measured ladder

### Stage 0 — baselines that must be beaten

Implement historical up-frequency probability, majority-class direction, a simple lagged-return rule, and regularised logistic regression. Calculate the historical frequency using only past training observations. Compare on identical dates, instruments and horizons.

This prevents a model from claiming success merely because the market rose most days in its test period.

### Stage 1 — primary production candidate

Use LightGBM binary classifiers for one- and five-session targets. Start with modest tree depth/leaf count, regularisation and early stopping. Use lagged returns and trailing statistics instead of relying on raw price levels. Fit preprocessing on training data only.

Maintain a separate index model and a pooled company model with company/sector context. Avoid training a large independent neural network for every company. Limit the first feature set to interpretable groups and a bounded number of tuning trials.

Recommended initial research budget: at most 20 LightGBM configurations per horizon, with the same predetermined chronological folds. Record every attempt. This is a compute cap, not a promise that 20 trials are necessary.

### Stage 2 — compact news and sequence challenger

Once data timing and baseline evaluation are sound, implement a small WCN-LSTM-inspired challenger with a price/history branch and separately categorised market, sector and company news features. First test whether inexpensive news counts/event categories/sentiment features help LightGBM; the neural branch must justify its extra cost.

The [PSX WCN-LSTM study](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0282234) motivates this experiment, but does not establish this project's future accuracy. Its comparisons concern a particular historical sample and setup. Do not reuse study results as app performance.

News requirements:

- Use only permitted sources; retain links and minimal metadata when full-text retention is not allowed.
- Deduplicate repeated and syndicated stories; prevent updates to a story from appearing before their publication.
- Map companies, sectors and macro topics, handling ambiguous names and Urdu/English text explicitly.
- Keep language and sentiment confidence as features. Do not silently run an English-only classifier over Urdu and treat the scores as validated.
- Start with cheap features. A frozen [FinBERT](https://arxiv.org/abs/1908.10063) encoder is optional if its licence, download size, domain fit and CPU runtime are acceptable. Cache permitted outputs by content hash and model version.
- FinBERT classifies financial text; it is not a stock-price forecasting model.
- Audit the pretrained encoder's training-period provenance before making historical claims. If future training-corpus contamination cannot be ruled out, disclose it and use a qualifying historical encoder or prospective-only evaluation for that branch.

Cap this initial neural experiment to a small architecture and at most three prespecified variants. Disable it in production if it exceeds the budget or fails evaluation. TCN, xLSTM and transformer-based cross-stock models are later research options, not required dependencies.

### Stage 3 — blend only when validated

Generate genuine out-of-time predictions from candidate models. Test a constrained nonnegative blend whose weights sum to one, or a simple logistic combiner trained on those predictions. A valid outcome is using the best single model.

Do not train a combiner on in-sample predictions. Do not assume agreement between models means independence: models using the same market data often fail together.

Calibrate the final chosen predictor on a later, disjoint chronological block. Start with sigmoid calibration; compare isotonic only when enough calibration observations exist. Check [calibration guidance](https://scikit-learn.org/stable/modules/calibration.html). Recalibration changes the model version.

If class weighting or resampling is explored, evaluate and calibrate against the natural prevalence; do not present altered training prevalence as a real-world probability.

### Stage 4 — selective signals

Learn thresholds and quality gates on a further validation block. Candidate gates include probability strength, calibrated reliability, eligible liquidity, input freshness and out-of-distribution status. Model agreement can be tested as one additional feature, not treated as a guarantee.

Keep thresholds separate by horizon and, where support permits, by signal direction. Pooling across companies must not create unsupported company-specific accuracy claims. Keep complexity low when sample sizes are small.

## 9. Evaluation that the developer must implement

### 9.1 Chronological protocol

Use expanding or rolling walk-forward evaluation. Group all companies from the same forecast date together. Random row splits are prohibited. A generic time-series splitter on a symbol-sorted table is also insufficient.

Aim for at least five years of usable daily history. As a starting design, use at least 504 sessions for initial fitting, development blocks of roughly 63 sessions, and a final untouched period of approximately 252 sessions when history allows. These are planning defaults; adjust for available data before examining final results and record the reason. Shorter history means weaker evidence, not permission to imply greater certainty.

For each development fold, preserve the order:

    Earlier fit data
      -> later out-of-time predictions for blend fitting, if used
      -> later calibration block
      -> later threshold-selection block
      -> later evaluation block

Across every boundary, purge training examples whose label ends overlap the later block. Use actual exchange-session label intervals, including five-session overlap. A five-row gap on a multi-company table does not solve this problem.

Freeze the target, features, models, search budget, refresh schedule, thresholds and reporting before opening the final test period. A simulated weekly refresh in that period is allowed only as part of the frozen procedure, using then-matured historical labels. Do not manually revise the method after inspecting that test and continue calling it untouched.

Fit scalers, imputers, feature selectors, denoisers and regime models inside the historical training window. Prohibit centred rolling windows and whole-series wavelet/filter transformations that use later observations. Validate against the actual defined return, not a future-smoothed target.

### 9.2 Required metrics

| Metric | Purpose |
| --- | --- |
| Brier score and log loss | Whether probability estimates improve over baseline probabilities |
| Calibration plot and bin counts | Whether estimated probabilities match observed frequencies, with sample support visible |
| Accuracy and balanced accuracy | Overall correctness plus protection against one-class dominance |
| Precision/recall by direction | Whether success is limited to one direction |
| Selected-signal correctness | Correctness when the system actually issues a signal |
| Coverage and abstention rate | How often that selectivity permits a signal |
| Support | Forecast count, unique dates, companies and matured outcomes |
| Date-block uncertainty intervals | Uncertainty allowing for correlated stocks and overlapping horizons |
| Rolling and regime breakdowns | Whether gains survive different market conditions |
| Data exclusions and missed issuances | Whether the pipeline avoids difficult cases or fails operationally |

Publish both opportunity-weighted and date-balanced summaries for pooled company models. Report the index separately. A hundred companies forecast on the same date are not a hundred independent market experiments.

Use a moving-block bootstrap over dates, preserving all companies on each sampled date and allowing for horizon overlap. Predeclare block-length choices and include sensitivity checks. Keep conventional independent-binomial intervals only as clearly labelled supplementary illustrations.

Separate research backtests, final-test results and genuinely forward-issued forecasts. An append-only forecast ledger must make forward results reproducible.

### 9.3 How to investigate the desired high percentage

Treat 80% selected-signal correctness as a research aspiration, not an expected outcome or deployment guarantee. Investigate whether a conservative gate can achieve that while issuing enough signals to be useful.

Before the final test, define a threshold policy and minimum evidence. Suggested starting criteria for an “80% supported historically” label are:

- A preselected signal policy and an untouched evaluation period.
- A one-sided 95% lower confidence bound for selected-signal correctness of at least 80%, calculated with the date-dependence method above.
- At least 200 matured selected forecasts across at least 100 distinct forecast dates, and separately reported support for each claimed direction and horizon.
- At least 10% coverage of eligible opportunities, with operational data coverage also disclosed.
- Improvement over relevant baselines and no severe probability-calibration failure.

These are deliberately demanding evidence requirements, not a claim that the project can meet them. The index may need years of prospective evidence at low coverage. Company observations cannot be substituted to make an index-specific claim. Do not relax these criteria after seeing the final results merely to unlock a badge.

If the target is not met, report the actual measured result, confidence interval and coverage. The app can remain useful as a research dashboard without the high-correctness label. A gate that produces zero signals is a failed usefulness target, not a successful 100% system.

### 9.4 Economic usefulness, if simulated

Only add an economic-performance report when actual costs and executable data are available. Include spread, fees, slippage, liquidity limits, cash periods and a clearly specified long-only strategy. Treat overnight gaps, price limits, suspension and missing opens realistically. Compare with a defined passive alternative over the same dates.

Probability of a rise alone does not estimate the size of gains versus losses. Add a separately validated return-magnitude or quantile model only if needed; otherwise leave expected profit and price-range fields absent. Never derive a narrow price interval from a direction probability.

## 10. Refresh, deterioration and model promotion

Keep an active model and a candidate model. A daily run performs inference with the active model. A weekly research run evaluates a candidate; it does not automatically replace the active model merely because retraining completed.

Promotion requires a predetermined recent chronological validation procedure, baseline comparisons, probability quality, data-quality checks and runtime checks. All selection stages use matured labels only. Keep the preceding active version for rollback.

Monitor input missingness, observation age, feature-distribution changes, calibration, Brier score, selected precision, coverage and directional balance. Define warning/pause thresholds using development data and store them in configuration. Do not use a single bad prediction as a reason to retune.

When a required source is stale or the input distribution is outside the validated operating range, suppress the signal and show the reason. A warning alone cannot make an unsupported probability reliable. A separately validated reduced-feature model may serve as a fallback; do not silently drop features and call the resulting model equivalent.

Weekly reviews can measure recent performance; repeated testing does not create new independent confirmation of an old accuracy claim. Record every promotion and the evidence supporting it.

## 11. System architecture

    Permitted source adapters
        -> timestamped observations and durable state
        -> quality checks and availability-aware feature builder
        -> versioned active model and calibrator
        -> immutable forecast ledger
        -> validated public-safe results bundle
        -> static mobile web app

    Matured outcomes -> evaluation reports and monitoring
    Historical snapshots -> bounded research -> candidate promotion gate

### Technology choices

- Python: pandas, PyArrow, DuckDB, scikit-learn and LightGBM.
- Optional news/sequence branch: small PyTorch model and optional frozen text encoder.
- Contracts: versioned JSON Schema or equivalent, with matching generated TypeScript types.
- Frontend: React, TypeScript and Vite, responsive CSS, manifest and service worker.
- Automation: GitHub Actions on standard Linux CPU runners.
- Hosting: static artifact deployment to GitHub Pages; keep the same build portable to Vercel.
- Tests: pytest for pipeline correctness; frontend contract/component tests and focused browser tests.

Check current compatibility and pin dependency versions and lockfiles during implementation. Do not hardcode package-version guesses from this document. Avoid a database server, Kubernetes, a paid AI service or a permanent Python web server for this daily-update use case.

### Repository structure

    .github/workflows/
      ci.yml
      daily.yml
      research.yml
    config/
      sources.yaml
      instruments.yaml
      calendars.yaml
      features.yaml
      evaluation.yaml
      budgets.yaml
    src/psx_pipeline/
      adapters/
      schemas/
      calendar/
      validation/
      features/
      models/
      evaluation/
      monitoring/
      publishing/
      cli.py
    tests/
      fixtures/
      unit/
      integration/
    web/
      src/
      public/
      tests/
    docs/
      SOURCE_AUDIT.md
      DATA_DICTIONARY.md
      MODEL_CARD.md
      EVALUATION.md
      RUNBOOK.md
      COSTS.md
      DECISIONS.md
    reports/
    pyproject.toml
    README.md
    .env.example
    .gitignore

Do not check real secrets, unapproved source data, unlicensed news text or large generated datasets into the public repository. Select a source-code licence intentionally and distinguish it from third-party data/model licences.

### Command interface to implement

Provide documented commands for source audit, permitted backfill, data validation, feature building, baseline comparison, candidate training, candidate evaluation, promotion, daily forecast, matured-outcome evaluation and public-bundle creation. Use one reusable pipeline implementation from both local execution and Actions.

All commands need clear exit codes, bounded runtime, structured logs and idempotent reruns. Allow explicit cutoff/session arguments for reproducible historical runs. A command must not silently switch from real data to fixtures after an error.

## 12. Results contract and publishing

Create a bundle manifest containing schema version, bundle identifier, generation time, expected update deadline, source-session coverage, model/version identifiers, file hashes, pipeline status and attribution.

Each forecast contains instrument, target definition, horizon, reference session/value, cutoff and issue times, target session, probabilities, signal decision, suppression reason, validation status and relevant scorecard reference. Values are null when unavailable. Do not substitute 50/50 as a placeholder for “no model.”

Keep research estimates distinguishable from validated signals. “Estimated probability; validation pending” is a possible research state, but it must not appear with a strong-signal or high-accuracy badge.

Publish a complete versioned bundle atomically. Forecasts, metrics and model metadata must refer to the same version. Validate hashes and schema before replacing the latest pointer. Maintain the last valid deployment and a documented rollback procedure.

Forecast keys must prevent duplicate issuance for the same instrument, reference session, horizon and policy. Retries may complete an interrupted publication, but cannot overwrite an issued probability after learning the outcome. Outcome and correction records are appended separately.

Limit public bundles to authorised information. Strip private source payloads and credentials from frontend assets, source maps, logs and downloadable reports. A browser-visible environment variable is public.

## 13. Android dashboard requirements

### Home

- KSE-100 overview and 1-session / 5-session selector.
- Up and down-or-unchanged probabilities, target date and clearly named return basis.
- Signal status: upward, downward-or-unchanged, no strong signal, or unavailable.
- Reference session, last successful update and next expected update in Pakistan time.
- A short explanation of forecast probability versus historical correctness.

### Watchlist

- Company name, symbol, horizon, forecast and input freshness.
- Sector and research-validation status.
- Filters and sorting without implying that an extreme unvalidated probability is the best investment.
- No borrowing of the index's accuracy for individual companies.

### Evidence

- Historical, final-test and forward results in distinct views.
- Correctness, coverage, support, uncertainty interval and evaluation dates together.
- Calibration chart and a simple baseline comparison.
- Breakdown by horizon and direction; per-company metrics only with adequate support.
- Full signal history, including failures, abstentions and subsequently corrected data.

### Drivers

- Dated observed changes in oil, currency, rates and other available factors.
- A few model contributions when a valid explanation method is available.
- Source links and timestamps.
- Plain wording: “contributed to this model estimate,” not “caused tomorrow's move.”

### Health

- Last completed data fetch, validation, prediction and publication.
- Active model version, source availability and any delayed observations.
- Honest “waiting for update,” “data delayed,” “offline” and “no trained model” states.
- Manual refresh that checks published results; opening the page does not retrain the model.

The browser may poll a small results/status file while visible. If the backend exposes only completed-run status, show that. Do not animate invented live fetching stages. Display live progress only when actual persisted job-stage events are available through an authorised endpoint.

### Mobile and offline behaviour

Support narrow Android screens, readable charts, touch targets, accessible contrast and text alternatives for colours. Include a manifest, icons and installation guidance. Cache the app shell; use a network-first approach for forecasts with visible last-update information.

The client must detect staleness using the clock and the exchange calendar even when the scheduler never ran. Store separate forecast target/expiry and data-update deadlines. Cached expired forecasts remain viewable as history but cannot look like current signals. Unknown calendar coverage also prevents a “fresh” claim.

No placeholder numbers may appear in production mode. Fixture/demo mode must be unmistakably labelled and disabled in the production deployment configuration.

## 14. Free automation and hosting

### Schedule

Initial proposed schedule, to be checked against actual source publication times:

| Job | Pakistan time | UTC cron |
| --- | --- | --- |
| Daily update | 18:17 Monday–Friday | 17 13 * * 1-5 |
| Recovery check | 19:17 Monday–Friday | 17 14 * * 1-5 |
| Candidate research | 10:17 Saturday | 17 5 * * 6 |

The calendar decides whether a session occurred and whether its data is final. Weekday scheduling is only a wakeup mechanism. A recovery run exits early if the session already completed successfully. If an essential source publishes later, deliberately move the schedule or use its last available permitted value as a dated feature; never silently claim the newer value was available.

Provide manual workflow dispatch and concurrency control so recovery, training and publication cannot corrupt shared state. Use bounded exponential backoff and respect source limits. An unavailable source must produce a meaningful status rather than an empty “successful” forecast file.

GitHub scheduled workflows can be delayed or dropped, run from the default branch, and public-repository schedules can be disabled after prolonged repository inactivity. Document manual recovery and inactivity checks; do not promise an unattended uptime guarantee. See [GitHub scheduling behaviour](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

### Runtime and cost budget

Design targets, to be measured rather than claimed as achieved:

- Normal daily inference pipeline: under 5 minutes once dependencies/data are cached.
- Hard daily job timeout: 20 minutes.
- Weekly candidate research timeout: 45 minutes.
- Skip optional experiments before exceeding the configured monthly budget.
- Incremental fetches, compressed small bundles, bounded history downloads and cached news features.
- No GPU requirement and no continuously running backend.

Standard public-repository Actions runners are currently free under GitHub's published rules; private work and storage have allowances. Check the actual account and [current Actions billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions) before enabling schedules. Do not assume the entire allowance is available to this one project.

Maintain a monthly estimate including daily jobs, recovery checks, dependency setup, tests, training, deployments and artifact storage. Set explicit caps and keep paid usage disabled where the platform allows. CPU targets may require dropping the neural branch.

### Deployment

Default to a GitHub Pages custom Actions deployment if the content and current hosting terms permit it. Build and deploy the validated results and static app together. Scope deployment permissions narrowly and use the documented Pages environment flow. See [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

Do not assume that a commit made with the workflow's default token will trigger another deployment workflow. Use a supported explicit dependency or deploy directly in the successful publishing workflow.

Vercel is an alternative for an eligible personal, noncommercial project; verify [Hobby plan restrictions](https://vercel.com/docs/plans/hobby). Use one production hosting target initially. A free hosted URL is sufficient; a custom domain is optional.

The website can remain accessible between jobs while predictions update daily. That is the intended meaning of availability here; it does not require the model to run continuously or fetch market data whenever the app opens.

## 15. Security and operational reliability

- Keep provider keys and repository/deployment credentials in protected secrets, never browser code.
- Do not run untrusted pull-request code with production data credentials.
- Pin third-party workflow actions to reviewed versions/commits and maintain a deliberate update process.
- Treat news text and downloaded documents as untrusted input; escape displayed text and restrict outbound source URLs appropriately.
- Do not load untrusted serialised model files; verify registry provenance and checksums.
- Log counts, timestamps and errors while avoiding secret values and restricted payload contents.
- Stop cleanly on schema changes, unexpected HTML responses, throttling and corrupted downloads.
- Maintain rollback, state-backup and restoration instructions; test restoration with a small permitted fixture.
- Publish health degradation when possible, and rely on client freshness detection when publication itself fails.

## 16. Required tests and acceptance evidence

Test the financial-data and operational failure modes that would otherwise produce believable but wrong results:

1. A value published after the cutoff cannot enter a feature row.
2. A revised macro observation cannot overwrite an earlier vintage used in evaluation.
3. All companies for a date stay in one chronological split; overlapping labels are purged at boundaries.
4. Labels do not mature early, including holiday and five-session cases.
5. Split/bonus/rights fixtures produce the documented adjusted returns; unresolved actions suppress issuance.
6. Missing observations, no trading and zero values remain distinct.
7. A parser receiving an error page with HTTP 200 fails validation.
8. A failed or stale required source cannot generate a fresh signal.
9. Rerunning a job does not duplicate or rewrite an issued forecast.
10. Calibration, blend fitting, threshold selection and evaluation use the intended disjoint data.
11. Probabilities are finite, within bounds and associated with the correct model, horizon and target definition.
12. Partial/corrupt bundles cannot replace the last good publication.
13. An expired offline forecast is visibly historical, including when the scheduler never woke up.
14. Production builds contain no fixture forecasts, credentials or disallowed source data.
15. The PWA works at common narrow phone widths and preserves accessible labels and install/offline behaviour.
16. A documented clean setup can reproduce a fixture pipeline and the public app build.

Include a recorded end-to-end manual workflow run, deployment smoke check and Android-browser check before claiming the app is live. If account access prevents these, report them as pending; passing local tests alone is not a deployed system.

## 17. Implementation phases and exit criteria

| Phase | Work | Exit evidence |
| --- | --- | --- |
| 0. Feasibility | Audit permitted free sources, index definitions, usable history and hosting/account limits | Source audit, explicit blockers, selected target definitions and cost assumptions |
| 1. Working skeleton | Repository, contracts, CLI, fixture pipeline and mobile empty states | Reproducible local run; no fake production forecasts; CI checks pass |
| 2. Data foundation | Approved adapters, calendar, corporate actions, vintage storage and quality checks | Reproducible dated dataset; availability and adjustment tests; data-quality report |
| 3. Baseline research | Historical baselines, logistic regression, price-only LightGBM and chronological evaluation | Full comparison report, scorecards, uncertainty and exclusions |
| 4. Indirect drivers | Priority A/B groups, relevant sector interactions and ablation comparisons | Evidence showing which groups help, fail or remain unavailable |
| 5. Advanced challenger | Cheap news features, bounded sequence/news challenger, blend/calibration/selection | Measured benefit and runtime, or documented decision to keep the simpler model |
| 6. Product integration | Real forecast bundles, evidence/history/health pages and Android PWA | Consistent model/data metadata; mobile and stale/offline checks |
| 7. Automation and release | Durable state, schedules, direct deployment, recovery and cost caps | Successful authorised workflow and deployed URL, with runbook and rollback |
| 8. Forward observation | Append forecasts before outcomes, score matured outcomes and monitor deterioration | Growing prospective ledger; claims limited to actual available evidence |

Do not jump to phase 5 while phase 2 has unresolved timing or adjustment errors. Do not block the basic app on a neural model that fails to improve results. If statistical evidence is insufficient, release only the honestly labelled research capabilities that are ready.

## 18. Completion checklist for Codex

Deliver:

- Working source repository and reproducible local instructions.
- Data dictionary, source audit and source-specific permitted-use decisions.
- Versioned dataset/feature/model contracts and provenance.
- Backtest report with baselines, calibration, support, uncertainty, coverage and exclusions.
- A model card that states the target, limitations and what has actually been measured.
- Android-ready PWA with truthful current, empty, failed and stale states.
- Scheduled workflows with manual rerun, budget limits and recovery instructions.
- Durable forecast history, matured outcomes and model promotion/rollback records.
- Cost assumptions, required account settings and secrets names without secret values.
- Verified deployed URL and workflow evidence if deployment access is available.
- A concise outstanding-dependencies list if live data or deployment remains blocked.

The final implementation report must distinguish **software built**, **data access verified**, **model evaluated**, **deployment verified**, and **future performance still being observed**. Report actual results even when they fall short of the user's hoped-for percentage.

## 19. Additional reference points

- [SBP release calendar](https://www.sbp.org.pk/data-calendar): use actual release timing for economic observations.
- [EIA open data](https://www.eia.gov/opendata/): inspect current data access, API and attribution requirements.
- [PBS FAQs](https://www.pbs.gov.pk/faqs/): publication-frequency context; actual releases determine availability.
- [Scikit-learn time-series splitting](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): useful building block; date grouping and label purging still require project-specific logic.
- [Selective classification research](https://arxiv.org/abs/1705.08500): background for abstention; not a financial accuracy guarantee.
- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits): check current limits and permitted usage before release.

## 20. Final design decision

Build the trustworthy data pipeline and evaluation system first. Use LightGBM as the initial strong candidate, test a small news/sequence challenger, calibrate the best validated predictor, and issue selective signals with visible coverage. Give the user a fast Android dashboard that serves the last valid results and clearly detects stale data.

The path to a higher defensible correctness percentage is better information timing, useful independent information, careful validation and selective issuance. Adding more complex models or more indicators alone does not establish a higher percentage.
