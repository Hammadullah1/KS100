# Model card - no active production model

- Target: KSE-100 official total-return close direction over one or five actual exchange sessions. Optional price-return and company models have distinct identifiers.
- Labels: Up means return > 0. Down or unchanged includes zero.
- Intended use: personal probability research and evidence inspection.
- Current data: synthetic TEST fixtures only. No permitted historical PSX dataset has been verified.
- Current production model: none. Candidate artifacts in fixture reports are unpromotable.
- Measured market accuracy, calibration, coverage and economic return: unavailable.
- Measured software behavior: see the test and fixture reports in PROGRESS.md.
- Training: chronological fit - out-of-time model/blend choice - calibration - selection - evaluation, plus reserved final test.
- Limitations: data rights, historical publication vintages, exchange calendar coverage, corporate actions and historical universe are external dependencies. Market shocks and regime changes remain unpredictable.
- Promotion: requires a reviewed artifact checksum, immutable snapshot, real untouched evidence, improvement over historical frequency, calibration checks and runtime checks. Weekly training alone never promotes.
- Deployment: not verified. No live-data access, uptime or future-performance claim.
- Future observation: an append-only ledger exists in software; real prospective observations have not begun.

"No demonstrated forecasting advantage yet" is the current research conclusion. A test fixture's correctness percentage is never evidence for a market claim.

Forward monitoring compares each instrument/horizon/model scorecard with its frozen evaluation. After 63 matured dates, Brier deterioration above 0.05 or ECE above 0.15 suppresses new probabilities pending review. Prior issuance remains immutable. Company forward scorecards require at least 200 outcomes and 100 distinct dates before public display; these are support gates, not proof of skill. Pooled research reports include opportunity-weighted and date-balanced accuracy, Brier, coverage and selected correctness. Dated bank-sector and exporter exposure (with a separate missing flag) provide initial company context.

Driver ablations are research-only until an accepted driver group has an equally versioned production inference path; the feature-version gate prevents an experimental driver model from silently receiving price-only inputs. The neural challenger remains conditional on lawful timestamped news and measured cheaper-feature benefit.
