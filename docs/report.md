# Dada Academy onboarding assistant: technical report

## 1. Problem and approach

New employees need answers they can trust. Every answer cites knowledge-base rows verbatim;
unsupported questions get a fixed refusal or "not confirmed"; generated text may not add contacts, links or numbers;
scenario feedback is never a score; the plan is "suggested".

Design rule: **the server decides, the model words.** Guards, a hybrid retriever and validated tools
decide; an optional language model chooses tools and phrases answers; a server verifier accepts or
drops every reply. Without a key the app runs fully offline.

## 2. Architecture

```
Browser (React, RTL, hash routes) -- JSON API --> FastAPI on 127.0.0.1
                                                 |
 Agent.turn: 1 guards (employment, contact; injection flagged)
             2 tool choice: LLM agent_v1 -> validate_args
               (invalid or disallowed -> rule router; offline: router)
             3 server runs the tool
                answer_from_rows: e5 + BM25 -> RRF -> margin band
                  offline: row verbatim | "not confirmed" + row | refusal
                  AI: answer_v1 over live rows -> verifier
                      pass: show | fail: offline result
                start/give feedback/end scenario, propose progress,
                show plan, start quiz, greet, refuse
             4 reply + sources + trace ("How I answered")
 Store: Supabase (KB + history, demo profiles, progress, attempts,
        turn logs without text) | local SQLite fallback
```

## 3. Tools and AI components

- **Retrieval:** `intfloat/multilingual-e5-small` (int8 ONNX, local) plus hand-written BM25 over
  normalised Arabic, fused by reciprocal-rank fusion. The five-values list is built by the server.
- **Offline confidence:** margin = best row similarity minus best similarity to 42 out-of-scope
  examples. Row similarity also uses four anchor questions per row, written from the row text only.
  Two thresholds, chosen on DEV only, give three bands: answer, not confirmed, refuse.
- **Guards:** whole-word patterns on normalised text for employment decisions (pay, firing, probation
  outcome) and contact requests. They run first, are final, and a guarded message never reaches the model.
- **Agent tools:** answer from rows, start scenario, give feedback, end scenario, propose progress,
  show plan, start quiz, greet, refuse. Progress changes only after the user confirms.
- **LLM (optional):** `deepseek/deepseek-v4.1-flash` via OpenRouter, pinned, temperature 0, seed 42,
  `data_collection: deny`, reasoning off, 5 s turn budget, USD 3 cap in code.
- **Verifier:** cited ids must be rows sent; each id needs a verbatim quote of six or more characters;
  every number must appear in the cited rows or the question; no contacts or links; at most 700
  characters. Failure falls back to the offline result. Only verified replies are cached.
- **Scenario feedback:** the model marks checklist items met or missing; the server writes the
  feedback from fixed sentences and the scenario's value. Offline, the user picks one of three replies
  or sees the suggested response.
- **Live knowledge editing:** edits re-index immediately and carry a «معدّل مباشرة» badge.
- **Hardening:** cross-origin writes refused; keys never logged or sent to the browser.

Stack: FastAPI, Pydantic, httpx, NumPy, ONNX Runtime, tokenizers; React, Vite, Tailwind CSS, IBM
Plex Sans Arabic. No training or fine-tuning.

## 4. Evaluation

DEV (154 questions: official FAQ, paraphrases, unanswerable, guard, multi-row, scenario and
progress cases) drove every threshold and prompt. A held-out set (50 questions) was
written blind by a separate author, sealed, and run once after freezing (commit `c6ea919`). The jury
test file was never used for tuning.

| Set · mode | Correct | Answerable refused | Unanswerable refused (or not confirmed) | Invented contacts |
|---|---|---|---|---|
| DEV · offline | 106/154 | 0/80 | 13/43 (40/43) | 0 |
| DEV · AI | 142/154 | 0/80 | 43/43 | 0 |
| Held-out · offline | 25/50 | 2/26 | 5/14 (14/14) | 0 |
| Held-out · AI | 43/50 | 0/26 | 14/14 | 0 |

On unseen wording offline mode is clearly weaker (25/50, 2 answerable refused) than AI mode (43/50,
none refused). DEV offline top-1 retrieval: 72/80. Latency p95: offline ≈ 14 ms, AI 3118 ms
(uncached). Verifier rejections about 1%; spend 0.054 USD. Jury block (reported only): 9/9 in both
modes. Red team: 19/20.

## 5. Limitations

- Offline mode refuses few unseen unanswerable questions outright (held-out 5/14); the rest get "not
  confirmed" with the closest row.
- Offline answers cannot combine rows or answer part of a question (DEV multi-row 0/3).
- Rows added live are matched less confidently offline.
- The verifier checks grounding, not quality of wording.
- Knowledge-base editing has no authentication (demo staff mode).
- 18 rows only; no HR procedures or employment decisions.

## 6. AI use, knowledge sources and privacy

- **Knowledge:** only the official `knowledge_base.csv`, hashed and unchanged; our own files are marked
  `source=ours`. Scenarios, the plan and the quiz are fictional competition examples, not SOPs. Some
  facts are paraphrased from Dada materials and need Dada's approval before external release.
- **What leaves the laptop:** without a key, nothing goes to an AI service (a socket tripwire proves
  this). With a key: the question (plus the previous one for short follow-ups), the live rows and
  practice replies, to OpenRouter with data collection denied. Never the role, alias or progress.
- **Stored:** Supabase (region to be confirmed) holds the KB with history, demo aliases, progress,
  attempt ids and turn metadata, **no chat text**; a local SQLite file takes over, without sync, when it
  is unreachable. The browser keeps progress and the thread locally.
- **No real employee or customer data.** The app makes no employment decisions.

Details: `docs/privacy_ai_note.md`.
