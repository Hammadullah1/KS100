# KSE-100 Research Desk

A local Python research pipeline and Android-installable React PWA implementing [CODEX_BUILD_PLAN.md](CODEX_BUILD_PLAN.md).

**Current status:** phase-one daily experimental KSE-100 index forecasts connect the [dashboard](https://ks-100.vercel.app/) to a dedicated GitHub data branch. The scheduled job fetches closing data, trains the research model and publishes one/five-session probabilities with stale-data warnings and a forward outcome record. See [live-feed operation](docs/LIVE_RESEARCH.md). Historical model comparisons have not established a reliable forecasting advantage; probabilities are not validated accuracy. Individual-stock forecasts remain outside this phase. See [model research](docs/MODEL_RESEARCH_2026-09-20.md).

See [progress and evidence](PROGRESS.md), [source audit](docs/SOURCE_AUDIT.md), [evaluation protocol](docs/EVALUATION.md), [model card](docs/MODEL_CARD.md) and [operations runbook](docs/RUNBOOK.md).

## Clean local setup

Tested with Python 3.10.11, uv 0.11.8, Node 24.16.0 and pnpm 10.34.5 on Windows. Python and JavaScript packages are pinned in `uv.lock` and `web/pnpm-lock.yaml`. Python is constrained to 3.10 for this tested environment; review an interpreter upgrade before its support period ends.

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
uv sync --locked
uv run psx source-audit
uv run psx --state state/fixture fixture
uv run psx --state state/fixture validate
uv run psx bundle --empty
uv run python scripts/export_schema.py
corepack pnpm@10.34.5 --dir web install --frozen-lockfile
corepack pnpm@10.34.5 --dir web contracts
corepack pnpm@10.34.5 --dir web test
corepack pnpm@10.34.5 --dir web build
corepack pnpm@10.34.5 --dir web dev
```

If Corepack is unavailable, install the **exact** free pnpm version with `npm.cmd install --global pnpm@10.34.5`, then use `pnpm --dir web ...`. The local npm client timed out on registry metadata during implementation; the verified pnpm 10 client succeeded. No project-specific paid service is needed for these local commands.

The dev server prints its local URL (usually http://127.0.0.1:5173). The production preview uses `pnpm --dir web preview -- --port 4173`. Service-worker/offline checks require a production build served over localhost or HTTPS.

## Verification

```powershell
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
uv run pytest --junitxml=reports/pytest.xml
pnpm --dir web exec playwright install chromium
pnpm --dir web e2e
```

Fixture evaluation, explicitly separated from market evidence:

```powershell
uv run psx --state state/fixture baseline --horizon 1 --cutoff 2026-09-18T13:17:00Z --output reports/local/h1
uv run psx --state state/fixture baseline --horizon 5 --cutoff 2026-09-18T13:17:00Z --output reports/local/h5
uv run psx --state state/fixture evaluate --horizon 1 --cutoff 2026-09-18T13:17:00Z --output reports/local/h1 --final
```

The fixture generator has a fixed seed and TEST identifiers. It invents a calendar and observations solely for testing. Never interpret its results as PSX history or forecasting ability. Production commands refuse fixture datasets and fixture models.

The current evaluation configuration is **protocol v2**. It separates exploratory threshold fitting from the larger independent evidence needed for a validated signal and uses complete dates for rolling company reports. Existing protocol-v1 reports remain unchanged. Use a fresh output directory (for example, `reports/experiments/protocol-v2/h1`) after changing a frozen protocol. See [the review](docs/REVIEW_2026-09-19.md) and [evaluation details](docs/EVALUATION.md).

## Command interface

Local retrospective CSV research (input files and reports stay outside public files):

```powershell
uv run psx snapshot-research --csv state/research/kse100_daily.csv --output reports/local/new-experiment
uv run psx snapshot-research --csv state/research/kse100_daily.csv --brent-csv state/research/brent_fred_raw.csv --output reports/local/new-brent-experiment
```

Use a new output directory for every experiment. Settings are frozen in `config/snapshot_research.yaml`; saved protocols record their values and hashes. These commands explicitly label the current history as already observed and cannot promote their artifacts to production. Raw data are not included in the repository.

Run `uv run psx --help` and `uv run psx COMMAND --help`. Global `--state PATH` goes **before** the command.

| Command | Result |
| --- | --- |
| source-audit | Dated permissions and blockers, no network collection |
| snapshot-research | Rolling CSV research with optional delayed Brent features; retrospective evidence only |
| fixture | Explicit synthetic Parquet snapshot and quality report |
| backfill | Permission-gated normalized JSON import; EIA live route remains disabled until audited live |
| validate | Schema, session, price and basis checks |
| features | Origin/cutoff-specific, backward-looking features |
| baseline / train | Same bounded chronological candidate research implementation |
| evaluate --final | Open the reserved final period once under the frozen protocol |
| promote | Check supplied artifact checksum and evidence; never promotes fixtures |
| daily / forecast | Active-model inference; real issue time; missed boundary rejected |
| outcomes | Append matured outcomes and corrections |
| bundle / verify-bundle | Validate and atomically package public-safe JSON |
| backup / restore | Archive permitted state and verify restored snapshot hashes |
| rollback-model / rollback-bundle | Restore an already verified preceding release |
| budget | Idempotently reserve a bounded monthly job allowance |

Exit codes: 0 completed operation (including creating a truthful blocked-status bundle), 2 invalid input/contract, 3 missing dependency or blocked production run. No command changes from real data to fixtures after failure.

## Data and publication

The default instrument is `PSX:KSE100:TR`; optional `PSX:KSE100PR:PR` remains separate. Company price labels exclude cash dividends and adjust documented splits, bonus shares and rights. No trading strategy or executable-profit estimate is claimed.

A lawfully supplied dataset can be imported only after recording source-specific rights and availability evidence. Import instruments and the explicit calendar before bars. Schema files are in `src/psx_pipeline/schemas/`. See [the data dictionary](docs/DATA_DICTIONARY.md).

The public app receives a small allowlisted bundle. Private state, raw files, API keys and model coefficients do not belong in `web/public`. Public code is MIT-licensed; that license does not grant any rights to third-party data or pretrained models. The supplied build plan retains its author's rights.

Schedules and deployment are gated off. See [account settings and recovery](docs/RUNBOOK.md) before enabling them.
