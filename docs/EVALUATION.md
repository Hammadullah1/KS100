# Evaluation protocol v2

No market evaluation has been completed. Reports under `reports/fixture/` contain synthetic software checks only. All actual package/model executions and timing are recorded separately from any financial claim.

The target and return basis are frozen, with separate one- and five-session reports. An index is evaluated independently; pooled company research requires dated liquidity/membership and company/sector context. Today's constituents are not substituted for a historical universe.

The default fit window is 504 dates. Later blocks of 63 dates are reserved, in order, for out-of-time model/blend choice, sigmoid calibration, threshold selection and evaluation. Training expands between development folds. The last 252 eligible dates remain untouched until `evaluate --final`. Dates group all companies together; every boundary purges labels ending in the next block or unavailable by its first cutoff. The final report cannot be opened again into the same research directory. New experiments require new identifiers and disclosure that an earlier holdout was already inspected.

Baselines: training up-frequency, majority-class direction, and a fixed lagged-return directional rule. Candidates: regularized logistic regression with fit-window scaling and a modest LightGBM model (7 leaves, depth 3, at most 200 trees, early stopping inside the fit block). One configuration per horizon is planned; the cap is 20. Optional logistic/LightGBM blends use the prespecified weights 0.25, 0.5 and 0.75 on genuinely later predictions. Calibration uses a separate block. A single model may win.

The lagged-return baseline's 0.6/0.4 mapping is a predeclared heuristic for comparison, not a production model probability. The majority classifier's hard probabilities are likewise baseline diagnostics. Production candidates receive later calibration.

Signal thresholds are selected separately by direction from a fixed grid. Protocol v2 distinguishes exploratory threshold fitting from independent evidence for an accuracy claim. The purged 63-date selection block requires at least 20 selected observations across 20 distinct dates per candidate direction, at least 10% coverage, and the declared 80% bootstrap lower-bound target. Passing this tuning step only proposes a policy; it does not establish validated accuracy or enable a production directional signal.

The untouched-test 80% historical-support criterion is unchanged: a one-sided 95% date-block lower bound of at least 80%, 200 selected matured forecasts, 100 distinct selected dates, at least 10% coverage, probability improvement and acceptable calibration, including support for each claimed direction. Insufficient final support leaves the app in research/no-strong-signal mode. A zero-signal policy has zero coverage and null selected correctness. The tuning counts are engineering defaults for fitting a threshold, not a statistical guarantee.

Protocol v1 applied the 100-date claim requirement to a selection block containing at most 63 dates. That made every threshold unreachable regardless of prediction quality. Old frozen v1 configurations keep their original behaviour; existing reports are preserved. New experiments use a new output directory and record protocol v2. No historical market holdout was opened or reopened during this repair.

Reports contain Brier/log loss, accuracy/balanced accuracy, directional precision/recall, unchanged frequencies, support, selected correctness, coverage, abstentions, calibration bin counts, rolling and fit-defined volatility regimes. Rolling windows contain 63 complete forecast dates, preserving every company on each date; they are not groups of 63 rows. Pooled correctness and Brier are reported both by opportunity and balanced by date. Moving-block bootstrap samples complete dates and all companies together; block lengths 5, 10 and 20, 500 replicates, seed 731 are declared before results.

There is no index profit simulation, short-selling assumption, price range or expected return inferred from a direction probability. These require separately validated executable prices, instruments and costs.

Driver experiments compare the same origin rows and targets. Disabled/unavailable groups are recorded, not imputed into invented observations. Cheap timestamped event counts, deduplication and language metadata are implemented. No licensed news history or evidence of cheap-feature benefit exists; neural/FinBERT training is therefore deferred. The external WCN-LSTM paper's reported performance is never used as this project's result.

Read [scikit-learn calibration guidance](https://scikit-learn.org/stable/modules/calibration.html) and [LightGBM Python API](https://lightgbm.readthedocs.io/en/stable/Python-API.html) for library mechanics. The project adds its own date grouping, interval purging and stage isolation.
