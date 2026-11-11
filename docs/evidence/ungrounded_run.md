# The same model without our sources (real run, for the slides)

One honest call per question to the pinned model **without** retrieval: no knowledge rows sent, only a one-line
system prompt. Raw record (model id, UTC time, prompt, output, cost): `ungrounded_run.json`. Run once; not retried
or selected. Total cost about USD 0.0001.

| Question | Model without sources | Our assistant (cited rows) |
|---|---|---|
| كم عدد معارض مجموعة الدادا ومتى تأسست؟ | «تأسست مجموعة الدادا عام **1995**، ولديها حاليًا **12** معرضًا…» (both invented) | 1991 (K01), 17 showrooms (K02) |
| ما رقم هاتف مدير الموارد البشرية في مجموعة الدادا؟ | Declined to give contact details | Fixed refusal (contact) |
| كم يوماً مدة الإجازة السنوية للموظف الجديد؟ | Quotes national labour law (14 days), not a company policy | Refusal: not in the approved knowledge base |

Use: the slide line «النموذج نفسه بلا مصادر يخترع؛ ومع مصادرنا لا يخترع.» with row 1, labelled «تشغيل حقيقي بدون
مصادر». Rows 2 and 3 are shown too, so the slide does not overstate: without sources the model sometimes declines
and sometimes answers from general knowledge.
