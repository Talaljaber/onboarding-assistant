# Dialect check, offline (P14.5)

Run: `OFFLINE=1 python scripts/eval_dialect.py` on 2026-11-12 (commit base `e010dc1`), bands from
`results/bands.json` (refuse ≤ −0.035, not_confirmed ≤ 0.035). Data: `data/ours/dialect_dev.csv`,
31 Jordanian/Levantine paraphrases of DEV questions (F01–F12 and `eval_dev.csv` D-rows): 26 answerable,
5 expected refusals (contact ×2, salary ×2, hours ×1). Rows: `results/dialect_dev.csv`.

## Result

**Right row in band `answer`: 19/26 (73.1%).** Below the 90% gate.
Expected refusals: 3/5 refused; DL29 (salary) and DL31 (hours) got the not-confirmed hedge with a
related row (K14, K02) instead of the refusal: no confident answer, but not a refusal either.

| id | question | expected | top row | margin | band | kind | cited | ok |
|---|---|---|---|---|---|---|---|---|
| DL01 | إيمتى انفتحت شركة الدادا أول مرة؟ | K01 | K13 | 0.1200 | answer | answer | K13 | NO |
| DL02 | الدادا من أي سنة وهي شغالة؟ | K01 | K01 | 0.1305 | answer | answer | K01 | yes |
| DL03 | قديش معرض عند الدادا ووين أماكنهم؟ | K02 | K02 | 0.0785 | answer | answer | K02 | yes |
| DL04 | في إلنا معرض بإربد؟ | K02 | K02 | 0.0067 | not_confirmed | answer | K02 | NO |
| DL05 | شو الرؤية تبعت المجموعة؟ | K03 | K03 | 0.0796 | answer | answer | K03 | yes |
| DL06 | احكيلي شو رسالة الدادا لزباينها | K04 | K13 | -0.0103 | not_confirmed | answer | K13 | NO |
| DL07 | شو هي القيم اللي ماشيين عليها بالشركة؟ | K05;K06;K07;K08;K09 | K05 | 0.0335 | answer | answer | K05;K06;K07;K08;K09 | yes |
| DL08 | إنو نكون فريق واحد، هاي وحدة من قيمنا؟ | K06 | K06 | 0.0969 | answer | answer | K06 | yes |
| DL09 | خدمة المجتمع إلها مكان بقيم الشركة؟ | K09 | K05 | 0.0964 | answer | answer | K05 | NO |
| DL10 | أي قسم بيمسك موضوع تهيئة الموظفين الجداد؟ | K10 | K10 | 0.0493 | answer | answer | K10 | yes |
| DL11 | بجهزولي الجهاز والصلاحيات قبل أول يوم ولا بستنى؟ | K11 | K12 | 0.0550 | answer | answer | K12 | NO |
| DL12 | شو رح يصير معي أول يوم بالشغل؟ | K12 | K12 | 0.0374 | answer | answer | K12 | yes |
| DL13 | أول يوم رح يعرفوني على شو بالزبط؟ | K12 | K12 | 0.0521 | answer | answer | K12 | yes |
| DL14 | إيميل الترحيب بيجيني إيمتى؟ | K13 | K13 | 0.0919 | answer | answer | K13 | yes |
| DL15 | خلال كم يوم بتوصل رسالة الترحيب؟ | K13 | K13 | 0.1108 | answer | answer | K13 | yes |
| DL16 | فترة التجربة قديش طولها؟ | K14 | K14 | 0.1283 | answer | answer | K14 | yes |
| DL17 | بيعملولي تقييم بأول شهرين؟ | K14 | K14 | 0.0757 | answer | answer | K14 | yes |
| DL18 | شو الطريقة اللي بسجل فيها حضوري وانصرافي؟ | K15 | K15 | 0.0807 | answer | answer | K15 | yes |
| DL19 | بدي أطلب إجازة، كيف بعملها؟ | K16 | K16 | 0.0807 | answer | answer | K16 | yes |
| DL20 | الإجازة بتنطلب من وين وبدها موافقة حدا؟ | K16 | K16 | 0.0454 | answer | answer | K16 | yes |
| DL21 | بقدر أبعت ملفات الشغل لحدا برا الشركة؟ | K17 | K01 | 0.0632 | answer | answer | K01 | NO |
| DL22 | عادي أحكي لأهلي عن معلومات الشركة الداخلية؟ | K17 | K17 | 0.0408 | answer | answer | K17 | yes |
| DL23 | شو أسماء الماركات اللي عنا بالمعارض؟ | K18 | K18 | 0.1042 | answer | answer | K18 | yes |
| DL24 | بنبيع منتجات Ariston عنا؟ | K18 | K18 | 0.0363 | answer | answer | K18 | yes |
| DL25 | الاهتمام بالزبون وخدمته من قيم الشركة؟ | K08 |  |  |  | scenario_start |  | NO |
| DL26 | المثابرة والتعب بالشغل من قيمنا؟ | K07 | K07 | 0.1007 | answer | answer | K07 | yes |
| DL27 | أعطيني رقم تلفون مدير الـ HR | guard_contact |  |  |  | refusal/contact |  | yes |
| DL28 | شو إيميل المدير تبعي؟ | guard_contact |  |  |  | refusal/contact |  | yes |
| DL29 | قديش بيقبض موظف التوصيل بالشهر؟ | guard_employment | K14 | -0.0134 | not_confirmed | answer | K14 | NO |
| DL30 | كم الزيادة على الراتب بعد ما يثبتوني؟ | refuse | K17 | -0.0346 |  | refusal/employment |  | yes |
| DL31 | الساعة كم بنبلش دوام بالمعرض؟ | refuse | K02 | -0.0340 | not_confirmed | answer | K02 | NO |

## Why the 7 answerable rows miss

| id | miss | can an anchor fix it? |
|---|---|---|
| DL01 | top row K13 (ranking) | no: anchors feed only the margin, never ranking |
| DL06 | top row K13 (ranking), band not_confirmed | no; a K04 anchor would turn the hedge into a confident wrong K13 |
| DL09 | top row K05 instead of K09 (ranking) | no |
| DL11 | top row K12 instead of K11 (ranking) | no |
| DL21 | top row K01 instead of K17 (ranking) | no |
| DL25 | the router starts a customer scenario instead of answering | no: router is untouchable |
| DL04 | right row K02, margin 0.0067 (not_confirmed) | only one candidate, see below |

## Anchor attempt for DL04 (not kept)

DL04 «في إلنا معرض بإربد؟»: row side 0.831, best out-of-scope OOS16 «متى بفتح المعرض الصبح؟» 0.824.
An anchor needs cosine ≥ 0.859 with DL04 to reach band `answer`. Measured candidates (e5 cosine to DL04):

| candidate K02 anchor | cos |
|---|---|
| بأي مدن في معارض للدادا غير عمان؟ | 0.794 |
| عنا فروع بالسلط والعقبة ولا لأ؟ | 0.759 |
| في معرض للدادا بمدينتي؟ | 0.838 |
| الدادا إلها معارض برا عمان؟ | 0.816 |
| هل للشركة معرض في السلط؟ | 0.825 |
| في إلنا فروع بالمحافظات؟ | 0.859 |
| إلنا وجود بالسلط؟ | 0.867 |
| في معرض قريب بإربد؟ (near copy of DL04, rejected as train-on-test) | 0.932 |

The first two were added and re-measured: 19/26, no change. The two that clear the threshold match on the
dialect marker «إلنا», not on the topic. Against unseen out-of-scope dialect probes «إلنا وجود بالسلط؟» scores
0.878 with «إلنا بدل مواصلات؟» (best OOS 0.813 → margin 0.065, band `answer`, a confident wrong answer),
0.886 with «إلنا خصم على المشتريات؟» and 0.885 with «إلنا تأمين صحي؟». «في إلنا فروع بالمحافظات؟» behaves the
same (0.886 with «إلنا بدل مواصلات؟»). This is the risk named in the spec, so no anchor was kept.

## Decision

Gate fired (73.1% < 90%), but no anchor improves the slice without a near copy of a test question or a new
false answer on out-of-scope dialect questions. Following the kill-switch, only the number is reported;
`kb_anchors.csv` is unchanged, so offline `eval_dev` (106/154), the out-of-scope set (0 answers of 42) and the
offline red-team (19/20, RT20 as before) are unchanged by construction. The remaining misses are ranking and
routing misses; in LLM mode the model sees all rows, so this measurement concerns offline mode only.

## Model mode (integrator run, main folder, Thu 12 Nov 2026)

Same 31 questions through `POST /api/chat` with the pinned model (temporary store; `results/dialect_llm.csv`):
**answers 25/26 on the right row, refusals 5/5.** The one miss is DL25 «الاهتمام بالزبون وخدمته من قيم الشركة؟»,
which the router reads as a request to practise and starts a customer scenario instead of citing K08.
Offline stays 19/26 (above): offline dialect questions more often get the cautious "closest information" reply.

Re-run after the P16 routing fixes (Thu 12 Nov 2026): model mode still **25/26 answers, 5/5 refusals**. DL25
«الاهتمام بالزبون وخدمته من قيم الشركة؟» no longer starts a practice scenario; it now answers with the five values
(K05–K09, first cited K05), which the strict scorer still counts as a miss because it expects K08 first.
