# Daily experimental index feed

The Vercel frontend reads `https://raw.githubusercontent.com/Hammadullah1/KS100/forecast-data/latest.json` directly. It needs no browser token, paid API server or daily frontend rebuild. The `forecast-data` branch contains only derived probabilities and the issued-forecast record; source prices and model parameters are not published there.

`live-research.yml` runs at 18:47 and 19:47 Pakistan time on weekdays and can be dispatched manually. It downloads PSX's EOD index history, rejects invalid/stale data, fits the existing logistic model on matured labels, calibrates separately, and mixes its probability equally with recent up-frequency. This fixed research candidate has **no demonstrated forecasting advantage**. The job runs under the standard Ubuntu runner with a ten-minute cap. GitHub schedules may run late; the frontend checks deadlines independently.

The first run generates real estimates for the latest recorded index close. It does not invent all-100-stock coverage. Forecasts target the next one/five recorded closing observations; the exchange calendar and return-basis reconciliation are not complete. The update deadline uses a weekday assumption and is labelled as such. An estimate is never called a validated signal. Original production source/promotion gates remain unchanged; this separately labelled experimental feed is not an approved production bundle or a source-rights certification.

Retries preserve issued probabilities and model versions. Later closes append outcomes only for predictions issued before their outcome date; revised reference prices are not silently scored. The latest 1,000 issued estimates are retained. Forward correctness is descriptive, and the app flags small samples and overlapping five-session outcomes. Failed source updates leave the previous file intact; overdue estimates remain labelled overdue in the browser. No synthetic fallback is allowed.

Local generation:

```powershell
.venv/Scripts/python.exe -m psx_pipeline.live_research --output state/live-preview/latest.json
```

For recovery, supply `--previous` with the latest previously published file. Production schedules requiring a verified calendar and approved model remain separate from this research preview. Disable the **Daily experimental index forecasts** workflow in GitHub to pause updates; the app will show the last estimate with its original deadline.

Vercel: deploy the `main` branch with root `web`, Vite, build `pnpm build`, output `dist`. Do not deploy `forecast-data` as the website. No new Vercel environment variable is required for this repository. This feature covers the KSE-100 index only; company forecasts need separate company histories and corporate-action handling.
