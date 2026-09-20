# Data contracts and timing

Version 1 contracts live in `src/psx_pipeline/contracts.py`; exported JSON Schemas live in `schemas/`. `scripts/export_schema.py` plus `pnpm contracts` generates matching TypeScript types. Unknown fields, nonfinite numbers and naive datetimes fail validation. UTC timestamps are stored; the UI formats Asia/Karachi.

| Table | Keys and important fields | Policy |
| --- | --- | --- |
| instruments | id, symbol, name, kind, return_basis, currency, source, sector | TR, PR and company targets are distinct |
| sessions | date, is_open, opens_at, closes_at, update_due_at, published_at, evidence | Explicit contiguous civil-date coverage including closures; actual sessions can differ on Fridays |
| bars | instrument, session, vintage, basis, units, status, OHLC, volume | No forward-fill; final closes must arrive after the session closes |
| actions | instrument, ex_session, kind, ratio, subscription_price, previous_close, resolved | Terms and ex-date separate from availability |
| membership | instrument, index, effective_from/to, liquidity_rank, weight, sector, exporter_exposure | Select only information available at each origin; removals remain in history |
| macro | series, reference_period, value, units, vintage | Release date is not reference period; age and missingness retained |
| flows | macro fields, participant, sector | Units and net/gross definitions must be audited |
| events | event_id, category, scope, entity, language/confidence, URL, content_hash, sentiment/encoder | Minimal metadata; story revisions become available only when received |
| features | instrument, session, cutoff, version, snapshot, values, input hashes, eligibility/reason | Price returns 1/5/20 sessions, trailing 20-session volatility |
| forecasts | instrument, horizon, target, cutoff, issue time, target session, deadlines, probabilities, signal, model, snapshot, policy | Immutable key = instrument/reference session/horizon/policy |
| outcomes | forecast key, target close, realized return, label, direction, vintage, correction_of | Append only after validated maturity; preserve original forecasts |
| models | version, scope, target, horizon, snapshot, hashes, evidence | Safe JSON/logistic coefficients and LightGBM text; no pickle |
| runs | start/end, status, persisted stage timestamps, reason | A failed fetch is not successful empty data |

Every source observation carries source, available_at, ingested_at, published_at where known, availability_evidence, vintage, payload_hash and fixture flag. Availability earlier than first receipt requires explicit evidence. A recently downloaded series with unknown historical release times is excluded from headline historical research.

## Adjustment policy v1

For a price before an action and an origin on/after its ex-session, multiply by the applicable factor, using only terms available at that origin:

- Split: 1 / new-shares-per-old-share ratio.
- Bonus: 1 / (1 + bonus-shares-per-old-share).
- Rights: (previous close + rights-per-old-share * subscription price) / ((1 + rights-per-old-share) * previous close). Missing terms fail.
- Cash dividends: factor 1; excluded from company price-direction labels.

Raw observations remain immutable. Adjustments are computed per origin and vintage; future ex-dates cannot change earlier features. Unresolved windows are excluded. Unexplained absolute session returns above the predeclared 25% review threshold are excluded pending investigation. This threshold is a data-review safeguard, not a volatility forecast.

The binary target is adjusted target/reference - 1 > 0; equality belongs to "Down or unchanged." Index series use their official supplied basis. The research label convention freezes the first validated target close by its update deadline and the original origin reference close; later revisions are separate correction records. This deliberately conservative first-final convention is recorded in the protocol.

## Manual imports and retained state

Normalized JSON arrays are the manual adapter format. Import in order: instruments, sessions, actions/membership, bars, optional macro/events. Example command after rights approval:

`uv run psx --state state/private backfill --source psx --table bars --file PATH_TO_PERMITTED_NORMALIZED_JSON`

The import does not confer data rights. Calendar evidence must identify the exchange notice and schedule coverage; do not generate a weekday calendar for production. If source publication evidence is unavailable, use first receipt and exclude those rows from historical evaluation.

Snapshots use small year-partitioned Zstandard Parquet files, manifest checksums and a last-written pointer. Ledgers are immutable JSON records. Caches and expiring Actions artifacts are accelerators; the private state repository is the durable remote copy when approved. Exceeding size caps requires deliberate retention work; never silently delete forecasts or corrections.
