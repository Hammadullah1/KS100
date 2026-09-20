# Operations and release runbook

No remote repository, successful hosted workflow or deployed URL is recorded yet. Local checks do not establish deployment.

## Required accounts and settings - after local review

1. Choose a GitHub account and public code repository. Review current [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) and [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) against the actual account. Use standard Ubuntu runners; disable paid usage where the account permits. No paid domain is required.
2. Set Pages source to **GitHub Actions** and configure the `github-pages` environment. Set `ACCOUNT_REVIEWED=true` and `PUBLISH_ENABLED=true` only after the concrete site/repository is approved. All flags default absent/disabled.
3. For permitted private retained data, create a separate private state repository. Set code-repository variable `STATE_REPOSITORY=owner/repo`. Secret `STATE_TOKEN` is a fine-grained token limited to that state repository's contents read/write. Do not put the token in an environment file or browser variable.
4. Complete source-specific permission and timing decisions in `config/sources.yaml`. A true flag is not evidence. Import an explicit exchange calendar and normalized history. EIA's optional server-side secret name is `EIA_API_KEY`; FRED's reserved name is `FRED_API_KEY`. Neither is required for the empty app or fixture checks. Do not enable sources with unresolved rights.
5. Run the manual CI workflow, inspect its logs and browser checks, then dispatch the **empty research dashboard** release workflow if publishing that reviewed empty site is desired. It deliberately contains no fixture forecasts.
6. Record workflow URL, deployment URL, bundle ID and date in `reports/release-evidence.json` only after observing success. Smoke-test the real HTTPS URL and install/open it in Chrome on a physical Android device. Screenshots from mobile emulation are not physical-device evidence.
7. Enable `SCHEDULES_ENABLED=true` only once permitted data, calendar coverage and a reviewed active model are available. A no-model run reports blocked; it does not invent a 50/50 forecast.

## Scheduled operation

Wakeups are 18:17 and 19:17 Asia/Karachi weekdays (13:17/14:17 UTC), plus Saturday 10:17 Asia/Karachi research (05:17 UTC). The dated exchange calendar decides if a session occurred. Source publication times may require an explicit schedule change; current wakeups are provisional until live timings are observed.

The daily workflow validates the latest approved snapshot, issues forecasts before the next session opens, and appends matured outcomes. There is currently no approved automated PSX collector; the manual-import route is usable after permission evidence is supplied. An enabled EIA adapter alone is insufficient for PSX forecasting.

A shared concurrency group serializes daily/recovery/research/release work. Forecast keys preserve issued probabilities during retries. Recovery skips already-completed sessions. A missed next-open boundary is never backdated. Weekly research writes candidates only; final-test opening and promotion are deliberate separate commands.

Standard [GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) may be late or dropped and public-repository schedules may be disabled after inactivity. Check workflow activity monthly and after a missed deadline. Dispatch manually after correcting the failure. The client checks expiry and update deadlines even if no job ever woke up.

## Candidate review and promotion

### Manual retrospective CSV research

After configuring the account and private state repository, the weekly research workflow can also be dispatched manually with `mode=snapshot`; this does not require enabling schedules. Put the reviewed local CSV at `research-inputs/kse100_daily.csv` within that state repository, and optionally the FRED-format Brent snapshot at `research-inputs/brent_fred.csv`. This mode writes only private exploratory reports under a run-specific path. It neither promotes models nor updates the public dashboard. It does not fetch or refresh these input snapshots automatically. Normal scheduled research still uses the approved normalized dataset.

Snapshot artifacts are deliberately rejected by production promotion. They contain retrospective assumptions and previously inspected evaluation periods. Review the [real-data research findings](MODEL_RESEARCH_2026-09-20.md) before interpreting scores.

### Approved dataset promotion

Inspect the source audit, snapshot checksums, protocol, exclusions, baseline comparisons, calibration, support, runtime and the unchanged final-test design. Compute the canonical candidate hash with `psx_pipeline.storage.digest`, then:

`uv run psx --state state/private promote --candidate REVIEWED_JSON --expected-sha256 REVIEWED_HASH`

Fixture promotion is prohibited. Calibration changes create a new model version. Models live in immutable release files; the previous active model is retained. `rollback-model --horizon 1 --instrument PSX:KSE100:TR` restores the preceding registered model. Pooled-company rollback uses `--scope company`.

For a damaged publication, leave the current valid pointer intact. Restore a verified preceding bundle with `rollback-bundle --output BUNDLE_ROOT --bundle-id HASH`, rebuild the same static app and deploy explicitly. Never rely on a default-token commit triggering another workflow; the publishing workflow deploys directly.

## State, backups and restoration

Only permitted normalized data, immutable forecasts/outcomes, models, protocol reports, job statuses and budgets belong in private state. Actions caches and one-day deployment artifacts are not the durable copy. Keep the private state repository below the configured 100 MB working-tree cap; snapshots are content-addressed and year-partitioned. Review growth monthly. Archive by an explicit audited retention policy, preserving forecast/outcome history.

```powershell
uv run psx --state state/private backup --output state/backups/reviewed.zip
uv run psx --state state/restored restore --archive state/backups/reviewed.zip
uv run psx --state state/restored validate
```

Restore requires an empty target, checks archive paths/size and verifies the current dataset and publication hashes. A fixture backup/restore acceptance test is included. Record the backup checksum separately.

A `.writer.lock` prevents concurrent mutation. After interruption, confirm its PID no longer runs and back up state before removing that one stale lock. Never delete a lock merely because another job is slow. No recovery procedure rewrites an issued probability.

## Security and failure handling

Untrusted PRs receive no production secrets. Production workflows run trusted default-branch code only. Dependencies and workflow commits are pinned; update them through reviewed PRs and rerun checks. `reports/action-pins.json` records official release URLs and verified commits.

Error pages with HTTP 200, schema changes, throttling, download caps, ambiguous vintages, invalid units and corrupted bundles fail closed. Network retries are bounded. Structured validation errors omit source values. News is untrusted metadata; React escapes displayed text and source links require HTTPS.

The public build excludes raw Parquet, source maps and fixture forecasts and scans credential patterns. That scan is defense in depth, not permission to place secrets under `web/public`. Source permissions remain the controlling gate. If public forecast rights are unavailable, use the local app; an obscure public URL is not protected access.
