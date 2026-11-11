# Demo script (5–7 minutes)

A timed shot list for the demo video and the live demo. It follows the required sequence: role →
two supported questions → one unanswerable question → a scenario → progress → the other role's
scenario, then the knowledge-base live edit and the offline switch.

Type the Arabic prompts exactly as written. They are the storyboard prompts that
`scripts/smoke_api.py` runs against the HTTP API, and the browser smoke (`tests/e2e`, offline, see
`docs/screenshots/INDEX.md`) clicks through the same steps. Expected results marked "offline: checked"
were seen in those offline runs. In AI mode the model words the answer, so the text can differ from the
row; the cited rows, the checks and the sources panel are the same.

## Before recording

1. Run `start.bat` with a key in `.env` (AI mode). Open «الإعدادات» (the round button at the top) and check the status reads «متصل بالنموذج».
   If there is no key, record the whole demo offline and skip the AI remarks.
2. Open «الإعدادات» → «حول التطبيق» → «امسح بيانات هذا المتصفح» (signed out, fresh progress and thread).
3. On the sign-in screen choose «مسؤول» → enter the admin password (`dada2026` unless `ADMIN_PASSWORD` is
   set), then «قاعدة المعرفة» → «استعادة النسخة الرسمية» (K02 back to 17). Sign out of the admin interface.
   (In a second browser profile you can keep the admin signed in for step 8.)
4. In «الإعدادات», turn on «عرض التتبع» and leave the mode on «تلقائي».
5. Rehearse once end to end, so verified AI replies are cached and fast.

## Shot list

| # | Time | Action (click or exact text) | Expected on screen | Say |
|---|---|---|---|---|
| 0 | 0:00–0:20 | Sign-in screen | Title «مرحباً بك في أكاديمية التهيئة», «متدرب» / «مسؤول», four intern names, the note that they are fictional demo personas | "An onboarding assistant for the first 90 days. Arabic first, runs on one laptop, works offline." |
| 1 | 0:20–0:40 | «متدرب» → «سارة الخطيب» → «دخول» | Chat screen, Sales greeting, five starter chips, header chip «سارة · المبيعات» | "Interns are fictional demo personas; the admin sets each one's track." |
| 2 | 0:40–1:20 | Type `متى تأسست مجموعة الدادا؟` Enter, then click «كيف أجبت؟» | An answer giving 1991 with source **K01 · Company Profile 2026 · صفحة 3** (offline: the row verbatim, «تأسست مجموعة الدادا عام 1991.», checked). With AI: mode chip «إجابة ذكاء اصطناعي», trace shows K01 at rank 1 and the verifier («التحقق») checks | "Every answer cites its row, verbatim. The trace shows how it was found and checked." |
| 3 | 1:20–1:55 | Click chip `ما قيم الشركة الخمس؟` | All five values: النزاهة، فريق واحد، المثابرة، محورية العميل، المسؤولية الاجتماعية, with five source rows K05–K09 (offline: checked) | "A multi-fact answer: five rows, all cited." |
| 4 | 1:55–2:25 | Type `ما رقم هاتف مدير الموارد البشرية؟` | Refusal «لا تتوفر لدي أرقام هواتف أو بيانات اتصال لأي شخص أو قسم، ولن أخمّنها…», no sources. Trace: «حارس جهات الاتصال», no model call (offline: checked) | "Unsupported: a fixed refusal. It never invents a contact." |
| 5 | 2:25–3:30 | Type `أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة`. Then type `بقوله إني رح أتأكد من المواصفات من المصدر الرسمي وبرجع له`. Then click «إنهاء التدريب» | Scenario card S02, value النزاهة, banner «وضع التدريب: S02 — …»; offline it also shows three reply options. Feedback card «ملاحظات تدريبية، وليست تقييماً»; offline it shows «الرد المقترح في المادة التدريبية»: «لا تخترع مواصفات؛ تحقق من مصدر موثوق أو اسأل المسؤول.» (offline: checked). With AI: «ما أحسنت فيه» / «أضف هذا» from the scenario checklist, plus at most one short checked tip. On end: toast «تم تحديث التقدم: …%» and the line «انتهى التدريب.» | "Feedback is linked to a company value. It is learning feedback, never a score." |
| 6 | 3:30–4:10 | Type `أكملت نشاط اليوم 30`. Click «تأكيد». Click «عرض لوحة التقدم» | Proposal «هل تريد تسجيل أنشطة «اليوم 30» كمكتملة؟» with «اختبار قصير» and «موقف عملي: زبون يسأل عن ثلاجة» (offline: checked). After confirm: «تم. التقدم الآن …%». Dashboard ring and lists updated | "Nothing changes until you confirm. The percentage is completion, not a performance score." |
| 7 | 4:10–4:50 | «الإعدادات» → «تسجيل الخروج». Sign in as «عمر حداد» (Delivery). Open «المواقف» → «ابدأ التدريب» on S04. Pick the first reply option | S04 card, value محورية العميل, situation «تأخر موعد التسليم والعميل منزعج.» Fixed feedback for the chosen option, linked to the value | "The other track has its own scenarios." |
| 7b | 4:50–5:10 | Sign out → «مسؤول» → admin password. «المتدربون», then click «سارة الخطيب» | The interns list: سارة الخطيب with the Day 30 completion, questions asked and last active; the others «لم يبدأ». Her detail page: plan with completion dates, S02 practised once (النزاهة), the K-rows her questions cited, the timeline | "The admin sees each intern's progress: completion and practice counts, never a score, and never the chat text." |
| 8 | 5:10–5:55 | In the admin interface open «قاعدة المعرفة». On K02 click «تعديل», change 17 to 18, «حفظ». In «جرّب الآن» type `كم عدد المعارض؟` | Toast «تم الحفظ وإعادة الفهرسة (… مللي ثانية)». Answer with 18 and the K02 row badged «معدّل مباشرة» (offline: checked, screenshot 15) | "A content owner can fix a fact. The next answer uses it at once, with a visible badge." |
| 9 | 5:55–6:35 | Header switch → «بلا اتصال». Back to «المساعد», type `متى تأسست مجموعة الدادا؟` | Same K01 row verbatim, mode chip «وضع بلا اتصال». Trace: no model call, margin and band «إجابة» (offline: checked) | "No key, no network: it still answers, from the knowledge-base rows only." |
| 10 | 6:35–7:00 | Open «حول والخصوصية» | What leaves the laptop, what is stored, limits | "With a key only the question (and the previous one for short follow-ups), the rows and practice replies go out, with data collection denied. No chat text is stored on a server." |

Total: about 7:00.

## Reserve shots (if the jury asks)

| Ask | Type | Expected (offline: checked) |
|---|---|---|
| Leave request | `كيف أقدم طلب إجازة؟` | K16 verbatim: «يُقدَّم طلب الإجازة عبر نظام الموارد البشرية ويستلزم موافقة المدير المباشر قبل بدء الإجازة.» |
| Probation | `كم فترة التجربة؟` | K14 verbatim, conditions quoted, no "this applies to you" claim |
| Confidentiality | `هل يمكن أن تشارك معلومات سرية مع صديق؟` | K17: «يجب المحافظة على سرية معلومات الشركة وعدم إفشائها دون تصريح.» |
| Delivery scenario by text | `أنا موظف توصيل والعميل غاضب بسبب التأخير` (role Delivery) | Scenario card S04 |
| "Show me the source" | Click «كيف أجبت؟» on any answer | id · document · page and the row text. Say: the CSV row is the source we were given |
| "Can it learn a new document?" (optional, admin) | «قاعدة المعرفة» → «استيراد مستند», choose a small approved `.txt`/`.docx` (leave «التنظيم بالذكاء الاصطناعي» off), «رفع واستخراج المقاطع»; on the review screen approve one passage; ask about it in «جرّب الآن» | Passages in document order with page and topic; after «اعتماد» the passage becomes the next K-row (link to the editor); the answer cites it word for word, badged «مضاف مباشرة». Say: nothing from the file is answerable until approved, the file itself is not kept. Afterwards «استعادة النسخة الرسمية» removes the row |

## Honest notes for the presenter

- After the admin steps (7b, 8), open `#/chat` for step 9: the intern stays signed in in the same browser
  (the admin interface has its own header without the intern screens).
- Step 8 also works **offline**: a small edit such as 17 → 18 keeps the row's anchor questions, so the
  answer band holds. A row added live, or rewritten heavily, may get the "not confirmed" card
  «لا أجد إجابة مؤكدة في قاعدة المعرفة.» offline with the row below it. Say so if a juror tries it; it is
  a known limit.
- If the network drops mid-demo, each answer falls back to the offline result in the same request (its
  chip reads «وضع بلا اتصال»); the status in «الإعدادات» changes to «بلا اتصال بالنموذج» at its next check
  (every 30 s). Continue offline and say so.
- Only the admin reaches the knowledge editor and the interns screens (one shared password, no accounts).
  Interns sign in by name with no password: demo only, a production version adds real authentication.
  If the server restarted, sign in again at «دخول المسؤول».
- After the demo, restore the official rows («استعادة النسخة الرسمية»).

## Recording tips

- 1920×1080, browser zoom 110–125% so Arabic text is readable; full-screen browser, bookmarks bar hidden.
- Turn on a cursor highlight; move the cursor slowly; pause one second on each result.
- Turn off notifications. Close other apps that use the network.
- Use a stable connection or a phone hotspot for AI mode. Keep the offline switch as the fallback.
- Record the voice-over in one take per shot; cut between shots.
- Keep the video between 5 and 7 minutes.
