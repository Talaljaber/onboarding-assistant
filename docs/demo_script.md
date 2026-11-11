# Demo script (5–7 minutes)

A timed shot list for the demo video and the live demo. It follows the required sequence: role →
two supported questions → one unanswerable question → a scenario → progress → the other role's
scenario, then the knowledge-base live edit and the offline switch.

Type the Arabic prompts exactly as written. Expected results marked "offline" were checked by running
the offline agent in-process on commit `6ef95f3`. Results in AI mode are marked {{VERIFY}} until the
AI layer and the HTTP API are wired and rehearsed.

## Before recording

1. Run `start.bat` with a key in `.env` (AI mode). Check the header chip shows «متصل بالنموذج».
   If there is no key, record the whole demo offline and skip the AI remarks.
2. Open «حول والخصوصية» → «امسح بيانات هذا المتصفح» (fresh role, progress and thread).
3. Open «قاعدة المعرفة» → «استعادة النسخة الرسمية» (K02 back to 17).
4. Turn on «عرض التتبع» in the header, mode «تلقائي».
5. Rehearse once end to end, so verified AI replies are cached and fast.

## Shot list

| # | Time | Action (click or exact text) | Expected on screen | Say |
|---|---|---|---|---|
| 0 | 0:00–0:20 | Welcome screen | Title «مرحباً بك في أكاديمية التهيئة», two track tiles, prototype badge | "An onboarding assistant for the first 90 days. Arabic first, runs on one laptop, works offline." |
| 1 | 0:20–0:40 | Click «مسار المبيعات» | Chat screen, Sales greeting, five starter chips, role chip «مسار المبيعات» | "Tracks are fictional competition examples." |
| 2 | 0:40–1:20 | Type `متى تأسست مجموعة الدادا؟` Enter, then click «كيف أجبت؟» | Answer «تأسست مجموعة الدادا عام 1991.» with source **K01 · Company Profile 2026 · صفحة 3**. Trace: K01 at rank 1, verifier passed, mode chip «إجابة ذكاء اصطناعي» {{VERIFY}} | "Every answer cites its row, verbatim. The trace shows how it was found and checked." |
| 3 | 1:20–1:55 | Click chip `ما قيم الشركة الخمس؟` | All five values: النزاهة، فريق واحد، المثابرة، محورية العميل، المسؤولية الاجتماعية, with five source rows K05–K09 (offline: checked) | "A multi-fact answer: five rows, all cited." |
| 4 | 1:55–2:25 | Type `ما رقم هاتف مدير الموارد البشرية؟` | Refusal «لا تتوفر لدي أرقام هواتف أو بيانات اتصال لأي شخص أو قسم، ولن أخمّنها…», no sources. Trace: «حارس جهات الاتصال», no model call (offline: checked) | "Unsupported: a fixed refusal. It never invents a contact." |
| 5 | 2:25–3:30 | Type `أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة`. Then type `بقوله إني رح أتأكد من المواصفات من المصدر الرسمي وبرجع له`. Then click «إنهاء التدريب» | Scenario card S02, value النزاهة, banner «وضع التدريب: S02 — …», three reply options. Feedback card «ملاحظات تدريبية، ليست تقييماً» with the suggested response «لا تخترع مواصفات؛ تحقق من مصدر موثوق أو اسأل المسؤول.» (offline: checked). With AI: what you did well / one thing to add from the checklist {{VERIFY}}. On end: toast «تم تحديث التقدم» | "Feedback is linked to a company value. It is learning feedback, never a score." |
| 6 | 3:30–4:10 | Type `أكملت نشاط اليوم 30`. Click «تأكيد». Click «عرض لوحة التقدم» | Proposal «هل تريد تسجيل أنشطة «اليوم 30» كمكتملة؟» with «اختبار قصير» and «موقف عملي: زبون يسأل عن ثلاجة» (offline: checked). After confirm: «تم. التقدم الآن …%». Dashboard ring and lists updated | "Nothing changes until you confirm. The percentage is completion, not a performance score." |
| 7 | 4:10–4:50 | Role chip → «مسار التوصيل». Open «المواقف» → «ابدأ التدريب» on S04. Pick the first reply option | S04 card, value محورية العميل, situation «تأخر موعد التسليم والعميل منزعج.» Fixed feedback for the chosen option, linked to the value | "The other track has its own scenarios." |
| 8 | 4:50–5:45 | Open «قاعدة المعرفة». On K02 click «تعديل», change 17 to 18, «حفظ». In «جرّب الآن» type `كم عدد المعارض؟` | Toast «تم الحفظ وإعادة الفهرسة (… مللي ثانية)». Answer with 18 and the K02 row badged «معدّل مباشرة» {{VERIFY}} | "A content owner can fix a fact. The next answer uses it at once, with a visible badge." |
| 9 | 5:45–6:25 | Header switch → «بلا اتصال». Back to «المساعد», type `متى تأسست مجموعة الدادا؟` | Same K01 row verbatim, mode chip «وضع بلا اتصال». Trace: no model call, margin and band «إجابة» (offline: checked) | "No key, no network: it still answers, from the approved rows only." |
| 10 | 6:25–6:50 | Open «حول والخصوصية» | What leaves the laptop, what is stored, limits | "With a key only the question and the rows go out, with data collection denied. No chat text is stored on a server." |

Total: about 6:50.

## Reserve shots (if the jury asks)

| Ask | Type | Expected (offline: checked) |
|---|---|---|
| Leave request | `كيف أقدم طلب إجازة؟` | K16 verbatim: «يُقدَّم طلب الإجازة عبر نظام الموارد البشرية ويستلزم موافقة المدير المباشر قبل بدء الإجازة.» |
| Probation | `كم فترة التجربة؟` | K14 verbatim, conditions quoted, no "this applies to you" claim |
| Confidentiality | `هل يمكن أن تشارك معلومات سرية مع صديق؟` | K17: «يجب المحافظة على سرية معلومات الشركة وعدم إفشائها دون تصريح.» |
| Delivery scenario by text | `أنا موظف توصيل والعميل غاضب بسبب التأخير` (role Delivery) | Scenario card S04 |
| "Show me the source" | Click «كيف أجبت؟» on any answer | id · document · page and the row text. Say: the CSV row is the source we were given |

## Honest notes for the presenter

- If you run step 8 **offline**, the answer is the "not confirmed" card «لا أجد إجابة مؤكدة في قاعدة
  المعرفة…» with the edited K02 row (18, badged) below it. Edited rows are matched less confidently
  offline. Say so; it is a known limit. (offline: checked)
- If the network drops mid-demo, the mode chip turns grey within about 30 s. Continue offline and say
  so. {{VERIFY}}
- After the demo, restore the official rows («استعادة النسخة الرسمية»).

## Recording tips

- 1920×1080, browser zoom 110–125% so Arabic text is readable; full-screen browser, bookmarks bar hidden.
- Turn on a cursor highlight; move the cursor slowly; pause one second on each result.
- Turn off notifications. Close other apps that use the network.
- Use a stable connection or a phone hotspot for AI mode. Keep the offline switch as the fallback.
- Record the voice-over in one take per shot; cut between shots.
- Keep the video between 5 and 7 minutes.
