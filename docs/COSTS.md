# Cost assumptions and operating caps

Reviewed 2026-09-18. No subscription, purchase, GPU, API spend, domain purchase or paid upgrade was made.

[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) currently makes standard public-repository runners free; larger runners are charged. Storage and private usage have account-specific allowances. The actual account has not been inspected, so production schedules remain disabled.

A conservative 22-weekday, four-Saturday monthly estimate:

| Component | Assumption | Reserved minutes |
| --- | --- | ---: |
| Daily + recovery preparation | 44 jobs x 20-minute hard timeout | 880 |
| Direct Pages deployment | 44 jobs x 10-minute hard timeout | 440 |
| Weekly research | 4 x 45-minute hard timeout | 180 |
| CI, setup and manual release allowance | Planning allowance; actual use must be tracked | 300 |
| Total | Worst-case reservations, not observed consumption | 1800 |

The scheduled-job ledger reserves daily preparation plus deployment together, and weekly research separately. The configured scheduled cap leaves the planning allowance for checks. Extra workdays, retries or manual releases can exhaust this budget; optional research must be skipped first. This is an engineering cap, not a guarantee about charges shared with other repositories.

Target daily inference time is under 300 seconds with cached dependencies. Synthetic evaluation timings are in fixture reports; they do not measure a production daily feed. No production inference runtime has yet been measured.

State cap: 100 MB permitted normalized working tree. Public results cap: 2 MB per complete bundle. Raw HTTP response cap: 5 MB. Deployment-artifact retention: one day. State snapshots and ledgers are durable in the approved private repository, not an expiring artifact.

Before enabling workflows: confirm the code repository is public, the state/account usage fits free allowances, Pages use is eligible and paid usage is disabled where possible. Keep account spending controls independent of application configuration.
