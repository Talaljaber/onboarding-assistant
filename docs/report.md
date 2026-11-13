# Dada Academy: Technical Report

**Arabic-first onboarding assistant for a new employee's first 90 days at Dada Group**
**Live demo:** https://dada-academy.netlify.app (admin password `dada2026`) · **Source:** github.com/Talaljaber/onboarding-assistant

## 1. Problem and approach
New employees need answers they can trust, and a mentor needs to follow their progress without micromanaging. Dada Academy answers questions **only from the company's approved knowledge base**, cites the source row word for word, and gives a fixed refusal when no row supports an answer.

Design rule: **the server decides, the model only words the answer.**
- Guards, a hybrid retriever and validated tools decide what happens.
- An optional language model chooses tools and phrases replies.
- A server-side verifier accepts or drops every model reply.
- Without an API key the whole app runs offline.

## 2. Architecture
```
Browser (React 19, RTL, Arabic/English) ──JSON API──► FastAPI (Python 3.13)
  1. Guards: employment decisions, contact requests, prompt injection → fixed refusal (model never sees them)
  2. Tool choice: LLM agent (validated args) or rule router (offline)
  3. Server runs the tool:
       answer_from_rows: e5 embeddings + BM25 → rank fusion → confidence band
         AI mode: answerer → verifier → citation judge ∥ coverage judge
                  agree (≥0.7) → send · else one escalation to a stronger model → verifier
                  any failure → offline answer
       scenarios · feedback · progress · plan · quiz · small talk · refuse
  4. Reply + sources + "How I answered" trace
Store: Supabase (Postgres, RLS on) │ local SQLite fallback
Background: email sender (Gmail SMTP) · deadline-reminder loop
```

## 3. AI and retrieval components
- **Retrieval:** `multilingual-e5-small` (int8 ONNX, runs locally) plus BM25 over normalised Arabic, fused with reciprocal-rank fusion.
- **Confidence:** a margin against out-of-scope examples sorts each question into one of three bands: answer, "not confirmed", or refuse.
- **Language model (optional):** `deepseek-v4.1-flash` via OpenRouter, with `glm-5.3` for escalation.
  - Both models are pinned; temperature is 0.
  - Data collection is denied on every call.
  - A **USD 3 cap is enforced in code**. Actual spend for the whole build was about USD 0.45.
- **Verifier:** every model reply must pass these checks, or it is dropped and the offline answer is used:
  - cited ids are rows that were actually sent to the model;
  - each id has a verbatim quote;
  - every number exists in the cited rows;
  - no phone number, email or link.

  Only verified replies are cached.
- **Scenario feedback:** the model marks checklist items; the server writes the feedback from fixed sentences tied to a company value. The feedback is **never a score**.
- **Rumour Check:** each sentence of something a colleague said is checked against the knowledge base. It is marked confirmed, different number (the source value shown), or not in the source. On 24 test rumours there were **0 false "confirmed"**.
- **Answer Recall:** when the admin edits a fact, every intern who was already told the old value sees the exact change (17 → 18) and a button to ask again. Before saving, the admin sees who will be affected.

## 4. Features
**Intern side:**
- Sign-in by name.
- Grounded Q&A with sources.
- Six practice scenarios, including a "customer pushes back" follow-up.
- A *suggested* 90-day plan.
- Progress tracking, either by ticking items or by telling the assistant.
- A "before your first day" card.
- Rumour Check.
- Questions to the mentor, sent only when the intern presses Send.
- Tasks with deadlines.
- Quizzes with an end-of-quiz review.
- A full English interface.
- Jordanian dialect understood.
- Phone-ready, checked at 360 px.

**Admin / mentor side:**
- **Knowledge-base editor:** edits re-index instantly, with "try now" and restore-official.
- **Document import** (.txt/.md/.csv/.docx/.pdf): split into passages, approved by the admin, then added as K-rows.
- **Interns list and detail:** completion and counts only, never chat text.
- **Questions inbox:** an answer either becomes a new knowledge-base row or is a private reply to one intern.
- **Mentor requests:** comments and files both ways, deadlines, and an **email reminder 10 minutes before** a deadline.
- **Quiz builder:**
  - Questions are written by hand, drafted by the model from a K-row, or uploaded as CSV.
  - Every question is checked against its row (for example, a number not in the row is rejected).
  - Practice or checkpoint mode, audience, opening at a plan %, and a time limit.
- **Quiz runs:**
  - Stored on the server, so the intern can resume on any device.
  - A timer enforced by the server.
  - During a checkpoint or timed quiz, chat and Rumour Check are locked on the server.
- **Final report:** all interns side by side (plan %, tasks on time / late / overdue, checkpoint results) and a printable page per intern. It has **no automatic ranking**: the mentor decides.
- **Email log and knowledge-base coverage card:** anonymous counts only.

## 5. Evaluation
Thresholds and prompts were tuned only on the DEV set (154 questions). Held-out 2 is 50 questions, written blind and sealed. It was run **once** on a frozen commit after all tuning. The jury test file was never used for tuning.

| Set · mode | Correct | Answerable refused | Unanswerable refused | Invented contacts |
|---|---|---|---|---|
| DEV · offline | 106/154 | 0/80 | 13/43 (40/43 incl. "not confirmed") | 0 |
| DEV · AI | 152/154 | 0/80 | 43/43 | 0 |
| Held-out 2 · offline | 26/50 | 1/30 | 4/10 (10/10 incl. "not confirmed") | 0 |
| Held-out 2 · AI | **45/50 (90%)** | 0/30 | 10/10 | 0 |

**Other measurements:**
- **AI latency:** p50 2.6 s, p95 5.7 s; 27% of turns escalated.
- **Cost:** about USD 0.085 per 100 questions.
- **Offline answers:** about 14 ms.
- **Red team (20 attacks):** offline 19/20, AI 17/20. Every safety check held; the misses are over-refusals.
- **Without our grounding**, the same model said "founded 1995, 12 showrooms". The truth is 1991 and 17.
- **Quality gates:**
  - 1543 Python tests and 492 web tests;
  - browser end-to-end storyboard 6/6;
  - lint and type checks;
  - a secret scan before every push.

## 6. Data, privacy and safety
- **Knowledge:** only the official knowledge base. It is hashed and never edited; edits are stored as a separate history.
- **The fictional parts:** scenarios, the plan, the quiz and the personas are competition examples, not Dada procedures.
- **What is stored:**
  - No chat text on the server, except a question the intern chooses to send.
  - Turn logs keep metadata only.
  - The role never reaches the Q&A prompt.
- **Supabase:** Row Level Security is on and there are no public policies. The server uses the secret key, which never reaches the browser.
- **Hardening:**
  - Cross-origin writes are refused, except for allow-listed front ends.
  - Request size limits.
  - Keys are never logged.
  - The admin uses signed session tokens.
- **No employment decisions:** hiring, firing, pay and probation questions get the fixed refusal.

## 7. Stack and deployment
- **Backend:** FastAPI, Pydantic, httpx, NumPy, ONNX Runtime, tokenizers, pypdf.
- **Frontend:** React 19, Vite, Tailwind 4, IBM Plex Sans Arabic.
- **Data:** Supabase (Postgres), with SQLite as the fallback.
- **No training or fine-tuning.**
- **Live demo:** **https://dada-academy.netlify.app**
  - The web client is on Netlify. It forwards `/api` to the FastAPI server on Render, which runs always-on.
  - Data is in Supabase.
  - Interns sign in by picking a name; the admin password is **`dada2026`**.
- **Run locally:** `start.bat`, a single command that creates the environment, installs packages and opens the browser. It works offline without any key.
- **Source:** github.com/Talaljaber/onboarding-assistant

## 8. Limitations
- Offline mode gives "not confirmed" rather than a clean refusal for many unseen unanswerable questions, and it cannot combine several rows.
- AI mode missed its held-out goal of 46/50 by one.
- The knowledge base has 18 official rows only.
- The demo sign-in has no per-person accounts: interns pick their name and the admin uses one password.
- The verifier checks grounding, not the quality of the wording.
