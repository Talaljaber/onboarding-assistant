# Dada Academy — slides

Five slides. One `---` line separates slides. Speaker notes follow each slide.

---

## 1. The problem: answers a new employee can trust

- The first 90 days are full of questions: the company, its values, leave, probation, confidentiality.
- A wrong answer about policy, a number or a contact does real harm.
- So trust is the test:
  - every answer cites its source row, shown verbatim (id · document · page);
  - unsupported questions get a clear refusal, never a guess;
  - no invented names, phones, emails, links or numbers;
  - practice feedback is never a score; the plan is suggested, not official.

Notes: The prototype is Arabic first and right-to-left. It runs on one laptop with `start.bat`, with or
without an API key.

---

## 2. What it does: the five features

| Feature | In the app |
|---|---|
| Welcome and role choice | «مسار المبيعات» / «مسار التوصيل» (fictional training tracks) |
| Question-answer assistant | Answers from the 18 official rows with sources; fixed refusals |
| Practical scenarios | Six official scenarios, three per track; feedback linked to a company value |
| 90-day learning journey | Days 1–7, Day 30, Day 60, Day 90, labelled as a suggested plan |
| Progress tracking | Confirm activities; dashboard with completion percentage |

Extras: «كيف أجبت؟» trace panel, live knowledge-base editing {{VERIFY}}, offline switch, practice quiz.

Notes: Scenarios, plan, quiz and activities are fictional competition examples, not Dada SOPs.

---

## 3. How it works: the server decides, the model words

```
message -> guards (employment, contact) -> tool choice (rules, or LLM checked against fixed lists)
        -> server runs the tool -> e5 + BM25 retrieval -> answer band
        -> optional LLM wording -> verifier -> reply + sources + trace
```

- Retrieval: multilingual e5 (local ONNX) + BM25, fused by rank.
- Verifier: ids must be rows sent, a verbatim quote per id, every number found in the rows, no contacts
  or links. A failed reply is dropped and the offline answer is shown.
- Offline: the matching row verbatim, "not confirmed" with the closest row, or a refusal.
- Model (optional): `deepseek/deepseek-v4.1-flash` via OpenRouter, pinned, temperature 0,
  data collection denied, USD 3 cap. {{VERIFY}}

Notes: The role never reaches the answer prompt. Progress changes only after the user confirms.

---

## 4. Results and limitations

| Set · mode | Correct | Unanswerable refused (or not confirmed) | Invented contacts |
|---|---|---|---|
| DEV · offline | 100/154 | 7/43 (40/43) | 0 |
| DEV · AI | {{DEV_LLM_CORRECT}} | {{DEV_LLM_UNANS_REFUSED}} | {{DEV_LLM_CONTACTS}} |
| Held-out · offline | {{HELDOUT_OFFLINE_CORRECT}} | {{HELDOUT_OFFLINE_UNANS_REFUSED}} ({{HELDOUT_OFFLINE_UNANS_REFUSED_OR_NC}}) | {{HELDOUT_OFFLINE_CONTACTS}} |
| Held-out · AI | {{HELDOUT_LLM_CORRECT}} | {{HELDOUT_LLM_UNANS_REFUSED}} | {{HELDOUT_LLM_CONTACTS}} |

- DEV offline: no answerable question refused; top-1 retrieval 72/80; p95 25 ms.
  AI mode p95 {{LLM_P95_MS}} ms.
- Limits: offline mode refuses few unseen unanswerable questions outright (most get "not confirmed");
  it cannot combine rows; edited rows are matched less confidently offline; 18 rows only.

Notes: Thresholds and prompts were chosen on DEV only. The held-out set was written blind and run once
after the freeze. The jury file was never used for tuning.

---

## 5. Demo and privacy

- Demo: role → two sourced answers → a refusal → a scenario → progress → the other track's scenario →
  live knowledge edit → offline switch.
- Without a key, nothing goes to any AI service; a socket tripwire proves offline mode makes no
  network calls.
- With a key: only the question, the previous question for follow-ups, the rows and practice replies
  go to OpenRouter, with data collection denied. Never the role, alias or progress.
- No chat text is stored on a server. Supabase holds the knowledge base, demo profiles, progress and
  turn metadata; a local file takes over when it is unreachable.
- No real employee data. Some company facts are paraphrased from Dada materials and need Dada's approval
  before external release.

Notes: Full note in `docs/privacy_ai_note.md`; run steps in `README.md`.
