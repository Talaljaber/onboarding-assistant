# data/ours — files we authored

Every row in every file here has `source=ours`. These are **competition examples written by the team**,
not Dada SOPs or official policy. The official data lives in `data/official/` (hashed, never edited).

Format: UTF-8 without BOM, LF line endings, one header row, `source` is always the last column,
written with Python's `csv` module. `scripts/check_ours.py` validates every file (schemas, enums, ids,
references into `data/official/`, regexes) and prints `ours OK: <counts>`.

`eval_heldout.csv` (and `HELDOUT_SEALED.md`) belong to a separate author and are **sealed**: builders never
open them, and `check_ours.py` skips them.

## out_of_scope.csv — 40 rows
Questions the knowledge base does not cover. The offline mode embeds the enabled rows and uses the
margin "best KB row cosine − best out-of-scope cosine" to pick the answer / not-confirmed / refuse band.

| column | meaning |
|---|---|
| `id` | `OOS01`…`OOS40` |
| `question_ar` | an out-of-scope question (Jordanian dialect or MSA) |
| `category` | `contact` 6, `salary` 5, `prices` 3, `hours` 4, `benefits` 3, `transport` 2, `smalltalk` 4, `discounts` 2, `resignation` 3, `remote` 2, `commission` 2, `holidays` 2, `warranty` 2 |
| `enabled` | `true`/`false`; the server may disable a row in memory after a KB edit |
| `source` | `ours` |

## scenario_checklists.csv — 18 rows (3 per scenario S01–S06)
Key actions derived from each scenario's `suggested_good_response_ar`. The LLM marks items met/missing;
the server writes the feedback from these sentences (never a score).

| column | meaning |
|---|---|
| `scenario_id` | `S01`…`S06` (official `role_scenarios.csv`) |
| `item_id` | `S0x-C1`…`S0x-C3` |
| `text_ar` | the key action (sent to the LLM) |
| `done_ar` | "what you did well" sentence shown when the item is met |
| `add_ar` | "one thing to add" sentence shown when the item is missing |
| `source` | `ours` |

## scenario_customer_lines.csv — 6 rows (one per scenario, P14.3)
One authored Jordanian-Arabic customer pressure line per scenario: natural follow-up pressure to promise or
confirm something the trainee cannot know. The server returns it as `Feedback.customer_ar`; the client shows
it once per practice run. Each line is Arabic only, at most 160 characters and passes the small-talk checks
(no number, name, time, contact, honorific or policy noun); `tests/test_customer_lines.py` enforces this.

| column | meaning |
|---|---|
| `scenario_id` | `S01`…`S06` |
| `customer_ar` | the customer's line |
| `source` | `ours` |

## scenario_options.csv — 18 rows (3 per scenario, exactly one best)
Offline practice: the user picks one of three replies and sees fixed feedback linked to a company value.

| column | meaning |
|---|---|
| `scenario_id` | `S01`…`S06` |
| `option_id` | `S0x-O1`…`S0x-O3` (the best option is not always O1) |
| `text_ar` | a plausible reply |
| `is_best` | `true` for exactly one option per scenario; its value equals the scenario's `company_value` |
| `company_value` | Integrity, One Team, Perseverance, Customer Centricity or Social Responsibility |
| `feedback_ar` | names the value in Arabic (النزاهة، فريق واحد، المثابرة، محورية العميل، المسؤولية الاجتماعية) and explains why the option fits or not; no digits, no scores |
| `source` | `ours` |

## content_en.csv — 135 rows (P16.3)
Authored English for the fixed learning content, a helper for the English UI only (Arabic stays the
reference; the official CSVs stay Arabic). Keyed by stable ids so the Arabic files can be reworded without a
merge conflict here. `tests/test_content_en.py` checks that every shown Arabic item has a row, that no row is
orphaned, that the English has no Arabic letters, contact or link, and adds no number the Arabic lacks.
Not covered on purpose: checklist `text_ar` (model input only), K-rows (cited verbatim) and the model's tip.

| column | meaning |
|---|---|
| `key` | `goal:<milestone>`, `activity:<id>`, `scenario:<S>`, `suggested:<S>`, `customer:<S>`, `option:<O>`, `option_feedback:<O>`, `check_done:<C>`, `check_add:<C>`, `quiz:<Q>`, `quiz:<Q>:<A\|B\|C>`, `reply:<name>` |
| `text_en` | the faithful English; value names use the official English (`Customer Centricity`, `One Team`, …) |
| `source` | `ours` |

## plan_activities.csv — 16 rows (8 per role)
The suggested 90-day plan's activities; progress percent = done / 8 for the role.

| column | meaning |
|---|---|
| `role` | `Sales` or `Delivery` |
| `milestone` | `Days 1-7`, `Day 30`, `Day 60`, `Day 90` (official plan names) |
| `activity_id` | `SA-…` (Sales) / `DE-…` (Delivery), e.g. `SA-D1-read-company`, `SA-D30-quiz`, `DE-D60-s05`, `DE-D90-summary` |
| `kind` | `read`, `quiz`, `scenario` or `summary` |
| `refs` | `;`-separated K/S/Q ids (empty only for the summary) |
| `title_ar` | short Arabic title shown on the plan and progress screens |
| `source` | `ours` |

## eval_dev.csv — 154 rows
The DEV set: every threshold and prompt choice is made on it (never on the jury file or the held-out set).
It contains F01–F12 (the official sample FAQ, ids kept), the former experiment sets already seen
(DEV own + unanswerable, HELD, FRESH; ids re-numbered `D…`), guard cases and their substring traps
(`مفصل`, `مراتب`, `كم عدد المعارض`, `كم رقم المعرض`), multi-row, partial, injection, follow-up, English,
scenario, progress, plan and greeting rows.

| column | meaning |
|---|---|
| `id` | `F01`…`F12`, then `D001`… |
| `question_ar` | the user message; follow-up rows hold `<previous> ||| <current>` (split on the first ` \|\|\| `: the left part is `last_user_message`, the right part is `message`) |
| `expected_behaviour` | `answer`, `partial`, `refuse`, `guard_employment`, `guard_contact`, `scenario`, `progress`, `plan`, `greet` |
| `expected_ids` | `;`-separated K ids (answer/partial rows only; list rows carry all five values) |
| `expected_scenario` | `S01`…`S06` for scenario rows |
| `expected_milestone` | `Days 1-7`/`Day 30`/`Day 60`/`Day 90` for progress rows (optional on plan rows) |
| `must_match` | `\|`-separated regexes; **all** must match the normalised answer (plan Part C §4.1). Pieces never use alternation, because `\|` is the separator |
| `must_not_match` | `\|`-separated regexes; **none** may match the normalised answer |
| `category` | `fact`, `list`, `multi`, `partial`, `probation`, `leave`, `confidentiality`, `unanswerable`, `contact`, `employment`, `scenario`, `progress`, `plan`, `english`, `injection`, `followup`, `greet` |
| `source` | `ours` |

Harness conventions: scenario rows send the prompt, then the fixed reply «سأتحقق من المصدر وأعود إليه»;
progress rows send the prompt, then `confirm`. Scenario and progress prompts name the role in the text
(`مبيعات` / `توصيل`); when the text names no role, use `Sales`.

## dialect_dev.csv — 31 rows (P14.5)
Jordanian/Levantine dialect paraphrases of DEV questions (sample FAQ F01–F12 and `eval_dev.csv`), written
after reading those two files only; no question copies an `eval_dev.csv` or `kb_anchors.csv` question.
Measured offline by `scripts/eval_dialect.py` (`docs/evidence/dialect_offline.md`). Never used for tuning.

| column | meaning |
|---|---|
| `id` | `DL01`…`DL31` |
| `question_ar` | the dialect question |
| `expected_behaviour` | `answer` (26), `guard_contact` (2), `guard_employment` (1), `refuse` (2) |
| `expected_ids` | expected K-ids for `answer` rows (`;`-separated), empty otherwise |
| `paraphrase_of` | the DEV question it paraphrases (F- or D-id) |

## factcheck_dev.csv — 24 rows (P14.2 Rumour Check)
Rumours written by the team from the official K-rows (never from a held-out or jury file), one sentence
each, for `scripts/eval_factcheck.py`. The gate is **0 false `supported`**: a rumour labelled `supported`
while `supported` is not in `acceptable`, or `supported` citing another row than `expected_id`.

| column | meaning |
|---|---|
| `id` | `FC01`… |
| `text_ar` | the rumour (one sentence, no split mark) |
| `expected` | the right label: `supported`, `differs`, `contradicts`, `related`, `not_found`, `guarded` |
| `acceptable` | `;`-separated labels that are not wrong for this rumour (always includes `expected`; `related` is a safe miss) |
| `expected_id` | the K-row the verdict should cite (empty when none) |
| `note` | why the row is there |
| `source` | `ours` |
