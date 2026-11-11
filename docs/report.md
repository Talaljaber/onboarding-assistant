# Dada Academy onboarding assistant: technical report

## 1. Problem and approach

New employees need answers they can trust. Every answer cites knowledge-base rows
and shows them verbatim; unsupported questions get a fixed refusal; generated text may not contain a
name, phone, email, link or number absent from the cited rows; scenario feedback is never a score; the
plan is "suggested"; the user's role never reaches the answer prompt.

Design rule: **the server decides, the model words.** Guards, a hybrid retriever and validated tools
decide; an optional language model chooses tools and phrases answers; a server verifier accepts or
drops every reply. Without a key the app runs fully offline.

## 2. Architecture

```
Browser (React, RTL, hash routes) -- JSON --> FastAPI on 127.0.0.1
                                                 |
 Agent.turn: 1 guards (employment, contact; injection flagged)
             2 tool choice: rule router (offline) or LLM agent_v1
               -> validate_args against fixed enums
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
- **Offline confidence:** margin = best row similarity minus best similarity to 40 out-of-scope
  examples. Row similarity also uses four anchor questions per row, written from the row text only.
  Two thresholds, chosen on DEV only, give three bands: answer, not confirmed, refuse.
- **Guards:** whole-word patterns on normalised text for employment decisions (pay, firing, probation
  outcome) and contact requests. They run first and are final.
- **Agent tools:** answer from rows, start scenario, give feedback, end scenario, propose progress,
  show plan, start quiz, greet, refuse. Progress changes only after the user confirms.
- **LLM (optional):** `deepseek/deepseek-v4.1-flash` via OpenRouter, pinned, temperature 0, seed 42,
  `data_collection: deny`, 5 s deadline, USD 3 cap in code. {{VERIFY}}
- **Verifier:** cited ids must be rows sent; each id needs a verbatim quote of six or more characters;
  every number must appear in the cited rows or the question; no contacts or links; at most 700
  characters. Failure falls back to the offline result. Only verified replies are cached.
- **Scenario feedback:** the model marks checklist items met or missing; the server writes the
  feedback from fixed sentences and the scenario's value. Offline, the user picks one of three replies
  or sees the suggested response.
- **Live knowledge editing:** edits re-index immediately and carry a «معدّل مباشرة» badge.
  {{VERIFY}}

Stack: FastAPI, Pydantic, httpx, NumPy, ONNX Runtime, tokenizers; React, Vite, Tailwind CSS, IBM
Plex Sans Arabic. No training or fine-tuning.

## 4. Evaluation

DEV (154 questions: the official FAQ plus our own paraphrases, unanswerable, guard, multi-row,
scenario and progress cases) drove every threshold and prompt. A held-out set was written
blind by a separate author, sealed, and run once after freezing (commit {{FREEZE_SHA}}). The jury
test file was never used for tuning.

| Set · mode | Correct | Answerable refused | Unanswerable refused (or not confirmed) | Invented contacts |
|---|---|---|---|---|
| DEV · offline | 100/154 | 0/80 | 7/43 (40/43) | 0 |
| DEV · AI | {{DEV_LLM_CORRECT}} | {{DEV_LLM_ANSWERABLE_REFUSED}} | {{DEV_LLM_UNANS_REFUSED}} | {{DEV_LLM_CONTACTS}} |
| Held-out · offline | {{HELDOUT_OFFLINE_CORRECT}} | {{HELDOUT_OFFLINE_ANSWERABLE_REFUSED}} | {{HELDOUT_OFFLINE_UNANS_REFUSED}} ({{HELDOUT_OFFLINE_UNANS_REFUSED_OR_NC}}) | {{HELDOUT_OFFLINE_CONTACTS}} |
| Held-out · AI | {{HELDOUT_LLM_CORRECT}} | {{HELDOUT_LLM_ANSWERABLE_REFUSED}} | {{HELDOUT_LLM_UNANS_REFUSED}} | {{HELDOUT_LLM_CONTACTS}} |

DEV offline: top-1 retrieval 72/80; guards 13/13; scenario, progress and plan rows all correct;
latency p50 11 ms, p95 25 ms. AI mode: p50 {{LLM_P50_MS}} ms, p95 {{LLM_P95_MS}} ms; verifier
rejections {{DEV_LLM_VERIFIER_REJECT_RATE}}; total spend {{LLM_SPEND_USD}} USD. Rows:
`results/results.csv`.

## 5. Limitations

- Offline mode refuses few unseen unanswerable questions outright (DEV 7/43); most get "not
  confirmed" with the closest row, and 3/43 got a wrong confident row.
- Offline answers cannot combine rows or answer part of a question (DEV multi-row 0/3).
- Edited or added rows are matched less confidently offline.
- The verifier checks grounding, not quality of wording.
- 18 rows only; no HR procedures or employment decisions.
- If Supabase fails mid-session, writes go to the local file; there is no sync back.

## 6. AI use, knowledge sources and privacy

- **Knowledge:** only the official `knowledge_base.csv`, hashed and unchanged. Our own files (anchors,
  out-of-scope examples, checklists, options, plan activities, tests) are marked `source=ours`.
  Scenarios, the plan and the quiz are fictional competition examples, not SOPs. Some facts are
  paraphrased from Dada materials and need Dada's approval before external release.
- **What leaves the laptop:** without a key, nothing goes to an AI service (a socket tripwire proves
  this). With a key: the question, the previous question for follow-ups, the live rows and practice
  replies, to OpenRouter with data collection denied. Never the role, alias, progress or history.
- **Stored:** Supabase holds the KB with history, demo aliases, progress, attempt ids and turn
  metadata, **no chat text**. Row-level security is on; only the server holds the key. The browser keeps
  progress and the thread locally.
- **No real employee or customer data.** The app makes no employment decisions.

Details: `docs/privacy_ai_note.md`.
