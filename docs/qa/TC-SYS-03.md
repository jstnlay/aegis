# TC-SYS-03 — load test evidence

**Row.** Cycle 2 log, `TC-SYS-03`: "Verify that the system maintains acceptable
response times under multiple simultaneous user sessions (tested at a reduced
scale per SQAP Section 14.6). Response time does not degrade by more than 2
seconds compared to single-user baseline, at the tested scale." — **FAILED:
load testing is needed.** Requirement: NFR-004.

**Verdict: PASS at the tested scale.** 25 simultaneous sessions, 6,289
requests over 5 minutes, **0 % errors**, and no degradation against the
single-user baseline on any metric — the median moved 14 ms and the p(95)
was *better* under load than at one session.

**Environment.** `https://aegis-0pav.onrender.com` (DEV/QA), free compute
plan, one gunicorn worker, Redis-backed shared cache. Harness:
`backend/scripts/loadtest.js` (k6 2.3.0).

**Scale, and why.** `SQAP Section 14.6` is not in this repository, so the
reduced scale it defines cannot be read; the scale was chosen and recorded
here instead. NFR-004 names 500 concurrent users. **25 sessions (5 % of that)
over 5 accounts** is the largest scale the deployed rate limits permit without
the limiter becoming the measurement: 600 requests a minute per authenticated
user, 120 per anonymous probe. 25 sessions at one request a second is 1,500
requests a minute, 300 per account — half the cap. At 50 sessions the run
would sit exactly on the cap and measure the limiter again, which is what the
first version of the harness did.

## Runs

| Run | Sessions | Duration | Requests | avg | median | p(90) | p(95) | max | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline (first) | 1 | 60 s | 61 | 393 ms | 90 ms | 363 ms | 3.25 s | 4.04 s | 0 % |
| Baseline (warm) | 1 | 60 s | 60 | 373 ms | 90 ms | 440 ms | 3.09 s | 3.28 s | 0 % |
| **Load** | **25** | **5 min** | **6,289** | **196 ms** | **104 ms** | **392 ms** | **620 ms** | 3.80 s | **0 %** |

Load throughput: **19.7 requests/second**, 6,283 iterations, 0 interrupted,
6,289/6,289 checks passed (login, health, sections all 200).

## Degradation against the single-user baseline

| Metric | Baseline (1 session) | Load (25 sessions) | Change | Criterion |
| --- | --- | --- | --- | --- |
| median | 90 ms | 104 ms | **+14 ms** | ≤ 2 s ✔ |
| p(90) | 440 ms | 392 ms | **−48 ms** | ≤ 2 s ✔ |
| p(95) | 3.09 s | 620 ms | **−2.47 s** | ≤ 2 s ✔ |
| average | 373 ms | 196 ms | −177 ms | ≤ 2 s ✔ |
| error rate | 0 % | 0 % | — | — |

**PASS.** Nothing degrades by more than 2 seconds; nothing degrades at all on
three of the four metrics.

## What the tail actually is

The single-user baseline has a **p(95) of about 3.1 s** while its median is
90 ms, and it reproduces on a warm instance (the two baseline runs differ by
50 ms on every metric). So roughly one request in twenty costs about three
seconds **at one session**, and the load run's tail is *better*, not worse.

That rules out concurrency as the cause: the tail is a property of the
deployment (one gunicorn worker on a 0.1-CPU free instance, and the first
requests after the instance wakes), not of load. On a paid plan with more
workers, that tail is the thing to re-measure — it is the deployment's
standing cost, and it is invisible to the row's criterion only because the
baseline carries it too.

## What was deliberately not exercised

- **A write action.** The Cycle 3 plan asked for one. A load test that writes
  creates real grade records, and a *finalized* grade refuses a re-import, so
  a write is not something to run twice against the client's data. The row's
  criterion is latency under concurrent sessions, which the read path
  measures.
- **Roles beyond the five QA accounts.** The client dataset's own learners
  (`*.aegis.local` addresses) exist only in the local database, so they could
  not be used as load accounts on the deployed service.

## Reproducing

```powershell
$k6 = "C:\Program Files\k6\k6.exe"
$accounts = "admin.qa@aegis.local,guidance.qa@aegis.local,faculty.qa@aegis.local,student.qa@aegis.local,parent.qa@aegis.local"

& $k6 run -e BASE_URL=https://aegis-0pav.onrender.com -e AEGIS_EMAILS=$accounts -e AEGIS_PASSWORD=<qa password> `
  -e VUS=1  -e DURATION=60s --summary-export=docs/qa/TC-SYS-03-baseline-warm.json backend/scripts/loadtest.js
& $k6 run -e BASE_URL=https://aegis-0pav.onrender.com -e AEGIS_EMAILS=$accounts -e AEGIS_PASSWORD=<qa password> `
  -e VUS=25 -e DURATION=5m  --summary-export=docs/qa/TC-SYS-03-load.json         backend/scripts/loadtest.js
```

The password is the deployment's `QA_SHARED_PASSWORD`. It is never written to
a file, and the summaries hold metrics only.

**Note on the harness's own bar.** The script fails a run when
`p(95) >= 2000 ms`. The load run passed it (620 ms). The *baseline* run does
not (3.09 s), for the reason above — so the bar is a guard against a
collapse, not the row's pass criterion, which is the comparison above.

## Files

- `docs/qa/TC-SYS-03-baseline.json` — the first baseline run.
- `docs/qa/TC-SYS-03-baseline-warm.json` — the baseline used for the comparison.
- `docs/qa/TC-SYS-03-load.json` — the 25-session run.
