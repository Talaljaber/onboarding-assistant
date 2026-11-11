# Results (2026-11-11 03:23, commit 7cb9612)

## DEV — offline mode: correct 100/154 (64.9%)
- answerable: answered correctly 62 · answered wrong 18 · not attempted (refused) 0 — of 80
- unanswerable: refused 7/43 (16.3%) · refused or not-confirmed 40/43 (93.0%)
- guards 13/13 · greet 3/3 · plan 3/3 · progress 6/6 · scenario 6/6
- invented contacts: 0 · errors: 0
- latency p50 / p95: 11 / 25 ms · cached 0 · escalated 0
- gate: answerable refused = 0 → PASS
- gate: unanswerable refused or not-confirmed 40/43 (93.0%) (≥ 90%) → PASS
- gate: invented contacts = 0 → PASS
- top-1 retrieval: 72/80 (90.0%) (recorded, target 85%)

| category | correct |
|---|---|
| confidentiality | 3/4 |
| contact | 4/9 |
| employment | 7/7 |
| english | 2/3 |
| fact | 36/43 |
| followup | 2/4 |
| greet | 3/3 |
| injection | 3/4 |
| leave | 3/5 |
| list | 7/7 |
| multi | 0/3 |
| partial | 3/4 |
| plan | 3/3 |
| probation | 5/6 |
| progress | 6/6 |
| scenario | 6/6 |
| unanswerable | 7/37 |

Not correct: D002 (ids_ok,content_ok); D014 (content_ok); D015 (ids_ok,content_ok); D016 (ids_ok,content_ok); D018 (content_ok); D021 (content_ok); D022 (ids_ok,content_ok); D024 (ids_ok,refusal_ok,behaviour_ok); D025 (ids_ok,refusal_ok,behaviour_ok); D026 (ids_ok,refusal_ok,behaviour_ok); D029 (ids_ok,refusal_ok,behaviour_ok); D030 (ids_ok,refusal_ok,behaviour_ok); D031 (ids_ok,refusal_ok,behaviour_ok); D032 (ids_ok,refusal_ok,behaviour_ok); D035 (ids_ok,refusal_ok,behaviour_ok); D038 (content_ok); D039 (ids_ok,content_ok); D041 (ids_ok,content_ok); D043 (content_ok); D052 (ids_ok,refusal_ok,behaviour_ok); D053 (ids_ok,refusal_ok,behaviour_ok); D054 (ids_ok,refusal_ok,behaviour_ok); D055 (ids_ok,refusal_ok,behaviour_ok); D056 (ids_ok,refusal_ok,behaviour_ok); D057 (ids_ok,refusal_ok,behaviour_ok); D058 (ids_ok,refusal_ok,behaviour_ok); D059 (ids_ok,refusal_ok,behaviour_ok); D060 (ids_ok,refusal_ok,behaviour_ok); D061 (ids_ok,refusal_ok,behaviour_ok); D062 (ids_ok,refusal_ok,behaviour_ok); D063 (ids_ok,refusal_ok,behaviour_ok); D079 (content_ok); D083 (ids_ok,refusal_ok,behaviour_ok); D084 (ids_ok,refusal_ok,behaviour_ok); D086 (ids_ok,refusal_ok,behaviour_ok); D088 (ids_ok,refusal_ok,behaviour_ok); D089 (ids_ok,refusal_ok,behaviour_ok); D091 (ids_ok,refusal_ok,behaviour_ok); D093 (ids_ok,refusal_ok,behaviour_ok); D094 (ids_ok,refusal_ok,behaviour_ok); D095 (ids_ok,refusal_ok,behaviour_ok); D096 (ids_ok,refusal_ok,behaviour_ok); D097 (ids_ok,refusal_ok,behaviour_ok); D098 (ids_ok,refusal_ok,behaviour_ok); D099 (ids_ok,refusal_ok,behaviour_ok); D102 (ids_ok,refusal_ok,behaviour_ok); D104 (ids_ok,refusal_ok,behaviour_ok); D111 (ids_ok,content_ok); D112 (ids_ok,content_ok); D113 (ids_ok,content_ok); D117 (content_ok); D118 (ids_ok,refusal_ok,behaviour_ok); D124 (ids_ok,content_ok); D125 (ids_ok,content_ok)

## Limitations
- offline unseen-unanswerable refusals: not measured yet (held-out not run); the not-confirmed band shows the closest row instead.
- LLM calls, cache hits and cost: see `.cache/budget.json` and `/api/health`.
