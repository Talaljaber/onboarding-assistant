# Results (2026-11-11 04:16, commit 83c1e07)

## DEV — llm mode: correct 142/154 (92.2%)
- answerable: answered correctly 68 · answered wrong 12 · not attempted (refused) 0 — of 80
- unanswerable: refused 43/43 (100.0%) · refused or not-confirmed 43/43 (100.0%)
- guards 13/13 · greet 3/3 · plan 3/3 · progress 6/6 · scenario 6/6
- invented contacts: 0 · errors: 0
- latency p50 / p95: 7 / 12 ms · cached 137 · escalated 0
- LLM-vs-router disagreement: 4 rows (D032, D042, D113, D118)
- gate: correct 142/154 (92.2%) (≥ 90%) → PASS
- gate: answerable refused = 0 → PASS

| category | correct |
|---|---|
| confidentiality | 4/4 |
| contact | 9/9 |
| employment | 7/7 |
| english | 3/3 |
| fact | 32/43 |
| followup | 4/4 |
| greet | 3/3 |
| injection | 4/4 |
| leave | 5/5 |
| list | 7/7 |
| multi | 3/3 |
| partial | 4/4 |
| plan | 3/3 |
| probation | 5/6 |
| progress | 6/6 |
| scenario | 6/6 |
| unanswerable | 37/37 |

Not correct: D004 (ids_ok); D007 (ids_ok); D009 (ids_ok); D013 (ids_ok); D022 (ids_ok); D039 (ids_ok); D041 (ids_ok); D043 (content_ok); D044 (ids_ok); D050 (ids_ok); D071 (ids_ok); D076 (ids_ok)

## DEV — offline mode: correct 106/154 (68.8%)
- answerable: answered correctly 62 · answered wrong 18 · not attempted (refused) 0 — of 80
- unanswerable: refused 13/43 (30.2%) · refused or not-confirmed 40/43 (93.0%)
- guards 13/13 · greet 3/3 · plan 3/3 · progress 6/6 · scenario 6/6
- invented contacts: 0 · errors: 0
- latency p50 / p95: 10 / 25 ms · cached 0 · escalated 0
- gate: answerable refused = 0 → PASS
- gate: unanswerable refused or not-confirmed 40/43 (93.0%) (≥ 90%) → PASS
- gate: invented contacts = 0 → PASS
- top-1 retrieval: 72/80 (90.0%) (recorded, target 85%)

| category | correct |
|---|---|
| confidentiality | 3/4 |
| contact | 6/9 |
| employment | 7/7 |
| english | 2/3 |
| fact | 36/43 |
| followup | 2/4 |
| greet | 3/3 |
| injection | 4/4 |
| leave | 3/5 |
| list | 7/7 |
| multi | 0/3 |
| partial | 3/4 |
| plan | 3/3 |
| probation | 5/6 |
| progress | 6/6 |
| scenario | 6/6 |
| unanswerable | 10/37 |

Not correct: D002 (ids_ok,content_ok); D014 (content_ok); D015 (ids_ok,content_ok); D016 (ids_ok,content_ok); D018 (content_ok); D021 (content_ok); D022 (ids_ok,content_ok); D024 (ids_ok,refusal_ok,behaviour_ok); D026 (ids_ok,refusal_ok,behaviour_ok); D029 (ids_ok,refusal_ok,behaviour_ok); D030 (ids_ok,refusal_ok,behaviour_ok); D031 (ids_ok,refusal_ok,behaviour_ok); D032 (ids_ok,refusal_ok,behaviour_ok); D035 (ids_ok,refusal_ok,behaviour_ok); D038 (content_ok); D039 (ids_ok,content_ok); D041 (ids_ok,content_ok); D043 (content_ok); D053 (ids_ok,refusal_ok,behaviour_ok); D054 (ids_ok,refusal_ok,behaviour_ok); D055 (ids_ok,refusal_ok,behaviour_ok); D056 (ids_ok,refusal_ok,behaviour_ok); D057 (ids_ok,refusal_ok,behaviour_ok); D058 (ids_ok,refusal_ok,behaviour_ok); D059 (ids_ok,refusal_ok,behaviour_ok); D060 (ids_ok,refusal_ok,behaviour_ok); D061 (ids_ok,refusal_ok,behaviour_ok); D062 (ids_ok,refusal_ok,behaviour_ok); D063 (ids_ok,refusal_ok,behaviour_ok); D079 (content_ok); D083 (ids_ok,refusal_ok,behaviour_ok); D084 (ids_ok,refusal_ok,behaviour_ok); D086 (ids_ok,refusal_ok,behaviour_ok); D088 (ids_ok,refusal_ok,behaviour_ok); D089 (ids_ok,refusal_ok,behaviour_ok); D091 (ids_ok,refusal_ok,behaviour_ok); D093 (ids_ok,refusal_ok,behaviour_ok); D094 (ids_ok,refusal_ok,behaviour_ok); D095 (ids_ok,refusal_ok,behaviour_ok); D099 (ids_ok,refusal_ok,behaviour_ok); D102 (ids_ok,refusal_ok,behaviour_ok); D104 (ids_ok,refusal_ok,behaviour_ok); D111 (ids_ok,content_ok); D112 (ids_ok,content_ok); D113 (ids_ok,content_ok); D117 (content_ok); D124 (ids_ok,content_ok); D125 (ids_ok,content_ok)

## Jury block (reported only, never tuned on) — llm mode: correct 9/9 (100.0%)
- answerable: answered correctly 5 · answered wrong 0 · not attempted (refused) 0 — of 5
- unanswerable: refused 1/1 (100.0%) · refused or not-confirmed 1/1 (100.0%)
- guards 0/0 · progress 1/1 · scenario 2/2
- invented contacts: 0 · errors: 0
- latency p50 / p95: 14 / 79 ms · cached 8 · escalated 0
- LLM-vs-router disagreement: 0 rows ()

| category | correct |
|---|---|
| confidentiality | 1/1 |
| fact | 1/1 |
| leave | 1/1 |
| list | 1/1 |
| probation | 1/1 |
| progress | 1/1 |
| scenario | 2/2 |
| unanswerable | 1/1 |

## Jury block (reported only, never tuned on) — offline mode: correct 9/9 (100.0%)
- answerable: answered correctly 5 · answered wrong 0 · not attempted (refused) 0 — of 5
- unanswerable: refused 1/1 (100.0%) · refused or not-confirmed 1/1 (100.0%)
- guards 0/0 · progress 1/1 · scenario 2/2
- invented contacts: 0 · errors: 0
- latency p50 / p95: 9 / 39 ms · cached 0 · escalated 0

| category | correct |
|---|---|
| confidentiality | 1/1 |
| fact | 1/1 |
| leave | 1/1 |
| list | 1/1 |
| probation | 1/1 |
| progress | 1/1 |
| scenario | 2/2 |
| unanswerable | 1/1 |

## Held-out (final run) — llm mode: correct 43/50 (86.0%)
- answerable: answered correctly 21 · answered wrong 5 · not attempted (refused) 0 — of 26
- unanswerable: refused 14/14 (100.0%) · refused or not-confirmed 14/14 (100.0%)
- guards 5/7 · progress 1/1 · scenario 2/2
- invented contacts: 0 · errors: 0
- latency p50 / p95: 1586 / 4102 ms · cached 0 · escalated 0
- LLM-vs-router disagreement: 5 rows

## Held-out (final run) — offline mode: correct 25/50 (50.0%)
- answerable: answered correctly 13 · answered wrong 11 · not attempted (refused) 2 — of 26
- unanswerable: refused 5/14 (35.7%) · refused or not-confirmed 14/14 (100.0%)
- guards 5/7 · progress 1/1 · scenario 1/2
- invented contacts: 0 · errors: 0
- latency p50 / p95: 8 / 10 ms · cached 0 · escalated 0

## Limitations
- offline unseen-unanswerable refusals: 5/14; the not-confirmed band shows the closest row instead.
- LLM calls, cache hits and cost: see `.cache/budget.json` and `/api/health`.
