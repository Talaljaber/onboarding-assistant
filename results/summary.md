# Results (2026-11-11 03:17, commit c1dbd6f)

## DEV — offline mode: correct 76/154 (49.4%)
- answerable: answered correctly 42 · answered wrong 38 · not attempted (refused) 0 — of 80
- unanswerable: refused 3/43 (7.0%) · refused or not-confirmed 41/43 (95.3%)
- guards 13/13 · greet 3/3 · plan 3/3 · progress 6/6 · scenario 6/6
- invented contacts: 0 · errors: 0
- latency p50 / p95: 8 / 15 ms · cached 0 · escalated 0
- gate: answerable refused = 0 → PASS
- gate: unanswerable refused or not-confirmed 41/43 (95.3%) (≥ 90%) → PASS
- gate: invented contacts = 0 → PASS
- top-1 retrieval: 72/80 (90.0%) (recorded, target 85%)

| category | correct |
|---|---|
| confidentiality | 1/4 |
| contact | 4/9 |
| employment | 7/7 |
| english | 2/3 |
| fact | 23/43 |
| followup | 2/4 |
| greet | 3/3 |
| injection | 3/4 |
| leave | 1/5 |
| list | 6/7 |
| multi | 0/3 |
| partial | 2/4 |
| plan | 3/3 |
| probation | 4/6 |
| progress | 6/6 |
| scenario | 6/6 |
| unanswerable | 3/37 |

Not correct: F02 (content_ok); F07 (content_ok); F08 (content_ok); F09 (content_ok); F10 (content_ok); D002 (ids_ok,content_ok); D003 (content_ok); D004 (content_ok); D008 (content_ok); D009 (content_ok); D010 (content_ok); D013 (content_ok); D014 (content_ok); D015 (ids_ok,content_ok); D016 (ids_ok,content_ok); D017 (content_ok); D018 (content_ok); D021 (content_ok); D022 (ids_ok,content_ok); D024 (ids_ok,refusal_ok,behaviour_ok); D025 (ids_ok,refusal_ok,behaviour_ok); D026 (ids_ok,refusal_ok,behaviour_ok); D029 (ids_ok,refusal_ok,behaviour_ok); D030 (ids_ok,refusal_ok,behaviour_ok); D031 (ids_ok,refusal_ok,behaviour_ok); D032 (ids_ok,refusal_ok,behaviour_ok); D035 (ids_ok,refusal_ok,behaviour_ok); D036 (ids_ok,refusal_ok,behaviour_ok); D039 (ids_ok,content_ok); D041 (ids_ok,content_ok); D042 (content_ok); D044 (content_ok); D045 (content_ok); D046 (content_ok); D049 (content_ok); D051 (ids_ok,refusal_ok,behaviour_ok); D052 (ids_ok,refusal_ok,behaviour_ok); D053 (ids_ok,refusal_ok,behaviour_ok); D054 (ids_ok,refusal_ok,behaviour_ok); D055 (ids_ok,refusal_ok,behaviour_ok); D056 (ids_ok,refusal_ok,behaviour_ok); D057 (ids_ok,refusal_ok,behaviour_ok); D058 (ids_ok,refusal_ok,behaviour_ok); D059 (ids_ok,refusal_ok,behaviour_ok); D060 (ids_ok,refusal_ok,behaviour_ok); D061 (ids_ok,refusal_ok,behaviour_ok); D062 (ids_ok,refusal_ok,behaviour_ok); D063 (ids_ok,refusal_ok,behaviour_ok); D074 (content_ok); D079 (content_ok); D083 (ids_ok,refusal_ok,behaviour_ok); D084 (ids_ok,refusal_ok,behaviour_ok); D086 (ids_ok,refusal_ok,behaviour_ok); D087 (ids_ok,refusal_ok,behaviour_ok); D088 (ids_ok,refusal_ok,behaviour_ok); D089 (ids_ok,refusal_ok,behaviour_ok); D090 (ids_ok,refusal_ok,behaviour_ok); D091 (ids_ok,refusal_ok,behaviour_ok); D093 (ids_ok,refusal_ok,behaviour_ok); D094 (ids_ok,refusal_ok,behaviour_ok); D095 (ids_ok,content_ok,refusal_ok,behaviour_ok); D096 (ids_ok,refusal_ok,behaviour_ok); D097 (ids_ok,refusal_ok,behaviour_ok); D098 (ids_ok,refusal_ok,behaviour_ok); D099 (ids_ok,refusal_ok,behaviour_ok); D100 (content_ok); D101 (content_ok); D102 (ids_ok,refusal_ok,behaviour_ok); D103 (content_ok); D104 (ids_ok,refusal_ok,behaviour_ok); D111 (ids_ok,content_ok); D112 (ids_ok,content_ok); D113 (ids_ok,content_ok); D115 (content_ok); D117 (content_ok); D118 (ids_ok,refusal_ok,behaviour_ok); D124 (ids_ok,content_ok); D125 (ids_ok,content_ok)

## Limitations
- offline unseen-unanswerable refusals: not measured yet (held-out not run); the not-confirmed band shows the closest row instead.
- LLM calls, cache hits and cost: see `.cache/budget.json` and `/api/health`.
