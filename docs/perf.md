# Performance (P5.5)

Targets (plan Part B P5.5): cold start ≤ 10 s to `/api/health` OK; offline answer p95 ≤ 300 ms;
LLM answer p95 ≤ 5 s or the offline fallback.

| Measure | Result | Target | How |
|---|---|---|---|
| Cold start (`start.bat` launched → first `/api/health` `status: ok`) | **8.0–8.7 s** (3 runs: 8.7, 8.0, 8.0) | ≤ 10 s | `& $VPY scripts\serve_check.py` with `DADA_PYTHON=$VPY` (prints `cold start to health`) |
| Server ready (uvicorn alone, under the network tripwire) | 5.6–7.6 s | — | `scripts\no_network.py scripts\smoke_api.py --serve --offline` (prints `server ready in`) |
| Agent build in-process (KB, encoder, retriever, features) | 1.9–2.0 s | — | `build_default_agent()` |
| Offline answer, in-process, first pass over DEV (154 questions) | **p50 10.7 ms, p95 13.6 ms**, max 72 ms | p95 ≤ 300 ms | `Agent.turn(ChatRequest(message=q))` per DEV `question_ar`, after one warm-up turn |
| Offline answer, in-process, 3 passes (462 turns; repeats hit the query cache) | p50 2.0 ms, p95 12.7 ms | — | same loop ×3 |
| Offline answer through the HTTP app (TestClient, 154 DEV questions) | p50 12.8 ms, p95 17.7–24.6 ms, max 77 ms | — | `POST /api/chat` |
| LLM answer (OpenRouter, pinned model) | p50 {{LLM_P50_MS}} ms, p95 {{LLM_P95_MS}} ms | p95 ≤ 5 s or offline | measured by the integrator in `main` with the key |

The offline path is about 20× under its target, so the 5 s LLM deadline (`LLM_DEADLINE_S`) is the only
latency that a judge can feel. When the LLM misses its deadline the turn falls back to the offline answer
inside the same request (`tests/test_hardening.py::test_llm_failure_is_offline_200_with_reason[timeout]`).

Cold start breakdown: `start.bat` first checks that onnxruntime loads and whether port 8000 is free (two
short Python runs, about 2 s), then uvicorn imports the app, validates the official sha256s and the encoder,
builds the agent and probes the LLM (no call offline). Most of the remaining time is Python + onnxruntime
import and the first encoder session.

## Machine

Windows 11 Home (10.0.26300), Intel Core (Family 6 Model 142, 4 cores / 8 threads), Python 3.13.1,
onnxruntime 1.31.0 on CPU, laptop on mains power, other apps open (editor, browser). Offline mode
(`OFFLINE=1`, `STORE=local`). Numbers measured on 11 Nov 2026 from the `w4/harden` branch.

## Reproduce

```
$env:DADA_PYTHON = $VPY; & $VPY scripts\serve_check.py          # cold start (last line)
& $VPY scripts\no_network.py scripts\smoke_api.py --serve --offline --session 60
```

The in-process latency loop is a dozen lines: build the agent with `build_default_agent()`, read
`data/ours/eval_dev.csv`, time `agent.turn(ChatRequest(message=row["question_ar"]))` per row, report the
50th and 95th percentiles.
