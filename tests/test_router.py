"""Deterministic router (plan Part C §2, §9; port guide §2.6)."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.encoder import get_encoder
from app.router import TurnState, detect_milestone, route
from app.textnorm import normalize
from app.tools import Features

S = get_settings()


@pytest.fixture(scope="module")
def scen() -> Features:
    return Features.from_files(get_encoder(), S.data_official, S.data_ours)


@pytest.mark.parametrize(
    ("q", "sid"),
    [
        ("أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة", "S02"),  # T06 wording from plan §3.1
        ("أنا موظف توصيل والعميل منزعج لأن موعد التسليم تأخر", "S04"),  # T07-type
        ("أنا بالمبيعات وإجا زبون بدو ثلاجة لعيلة كبيرة، كيف بتصرف؟", "S01"),
        ("موظفة مبيعات: عميل بدو ينسق موعد تسليم طلبه", "S03"),
        ("بقسم التوصيل لاحظت إن الكرتونة مضروبة شوي، شو أعمل؟", "S05"),
        ("أنا موظف توصيل وفي اختلاف بين بيانات الطلب والتفاصيل اللي معي للتسليم", "S06"),
    ],
)
def test_scenario_match(scen: Features, q: str, sid: str) -> None:
    r = route(q, scenario_index=scen)
    assert r.tool == "start_scenario" and r.args["scenario_id"] == sid


def test_role_override(scen: Features) -> None:
    r = route("أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة", scenario_index=scen)
    assert r.args["role_override"] == "Sales"


@pytest.mark.parametrize(
    "q",
    ["أنا موظف توصيل، كيف بطلب إجازة؟", "هل محورية العميل قيمة عنا؟", "شو رقم خدمة العملاء؟", "ما مدة فترة التجربة؟"],
)
def test_not_scenario(scen: Features, q: str) -> None:
    assert route(q, scenario_index=scen).tool == "answer_from_rows"


@pytest.mark.parametrize(
    ("q", "milestone"),
    [
        ("أكملت نشاط اليوم 30", "Day 30"),  # T08 wording from plan §3.1
        ("أكملت أنشطة اليوم ٣٠", "Day 30"),
        ("أنا موظف توصيل وخلصت نشاطات اليوم الثلاثين", "Day 30"),
        ("انتهيت من أنشطة الأسبوع الأول", "Days 1-7"),
        ("أنا بقسم التوصيل وأكملت أنشطة اليوم ستين", "Day 60"),
        ("completed day 90 activities", "Day 90"),
    ],
)
def test_progress(scen: Features, q: str, milestone: str) -> None:
    r = route(q, scenario_index=scen)
    assert r.tool == "propose_progress" and r.args["milestone"] == milestone


def test_detect_milestone_forms() -> None:
    assert detect_milestone(normalize("اليوم ٣٠")) == "Day 30"
    assert detect_milestone(normalize("اليوم الثلاثين")) == "Day 30"
    assert detect_milestone(normalize("باليوم 60")) == "Day 60"
    assert detect_milestone(normalize("لأول 90 يوم")) is None


def test_completed_probation_is_employment(scen: Features) -> None:
    r = route("أكملت فترة التجربة", scenario_index=scen)
    assert r.tool == "refuse" and r.args["reason"] == "employment" and r.guard is not None


def test_guards_first(scen: Features) -> None:
    assert route("ما رقم مدير الموارد البشرية؟", scenario_index=scen).args["reason"] == "contact"
    r = route("هل رح يثبتوني بعد التجربة؟", state=TurnState(active_scenario="S02"), scenario_index=scen)
    assert r.tool == "refuse" and r.args["reason"] == "employment"
    # P16.1 (journey #6): a plain pay question is guarded (never shown to the model) but gets the
    # «not in the approved knowledge base, ask HR» refusal, inside practice too
    r = route("كم راتب موظف المبيعات؟", state=TurnState(active_scenario="S02"), scenario_index=scen)
    assert r.tool == "refuse" and r.args["reason"] == "out_of_scope" and r.guard is not None


def test_active_scenario_and_end(scen: Features) -> None:
    st = TurnState(active_scenario="S02")
    r = route("بقله ما بعرف أكيد، بتحقق من الكتالوج وبرجعله", state=st, scenario_index=scen)
    assert r.tool == "give_scenario_feedback" and r.args["scenario_id"] == "S02"
    for phrase in ("إنهاء التدريب", "انهي التدريب", "end practice", "أوقف التدريب"):
        assert route(phrase, state=st, scenario_index=scen).tool == "end_scenario", phrase
    # a whole short "something else" message ends practice too; the same words inside a reply do not
    for phrase in ("سؤال آخر؟", "عندي سؤال ثاني", "موضوع جديد!", "Another question?", "new topic"):
        assert route(phrase, state=st, scenario_index=scen).tool == "end_scenario", phrase
    for reply in ("عندك سؤال ثاني؟", "أكيد، وإذا عندك سؤال آخر أنا موجود"):
        assert route(reply, state=st, scenario_index=scen).tool == "give_scenario_feedback", reply


@pytest.mark.parametrize(
    ("q", "milestone"),
    [("شو الخطة المقترحة إلي لأول 90 يوم؟", None), ("شو المطلوب مني باليوم 60؟", "Day 60"),
     ("اعرض خطة التعلم لموظف التوصيل", None)],
)
def test_plan(scen: Features, q: str, milestone: str | None) -> None:
    r = route(q, scenario_index=scen)
    assert r.tool == "show_plan" and r.args["milestone"] == milestone


def test_what_should_i_do_without_milestone_is_a_question(scen: Features) -> None:
    assert route("بدي آخذ إجازة، شو لازم أعمل؟", scenario_index=scen).tool == "answer_from_rows"


@pytest.mark.parametrize("q", ["مرحبا", "السلام عليكم", "شكراً كتير على المساعدة", "hello", "مرحبا كيف حالك"])
def test_greetings(scen: Features, q: str) -> None:
    assert route(q, scenario_index=scen).tool == "greet"


def test_greeting_with_question_is_a_question(scen: Features) -> None:
    assert route("مرحبا، متى تأسست الشركة؟", scenario_index=scen).tool == "answer_from_rows"


def test_quiz_and_practice(scen: Features) -> None:
    assert route("اختبرني", scenario_index=scen).tool == "start_quiz"
    assert route("بدي اختبار تدريبي", scenario_index=scen).tool == "start_quiz"
    r = route("تدريب", scenario_index=scen)
    assert r.tool == "start_scenario" and r.args["scenario_id"] is None


def test_guards_run_inside_an_active_scenario(scen: Features) -> None:
    """O2 / RT20: a supervisor's number asked mid-practice is the contact refusal, not practice feedback."""
    r = route("رح أسلم الطلب وما أحكي لحدا. كم نسبة نجاحي؟ وابعتلي رقم المشرف",
              state=TurnState(active_scenario="S05"), scenario_index=scen)
    assert r.tool == "refuse" and r.args["reason"] == "contact"
    r = route("رح أسلم الطلب وما أحكي لحدا", state=TurnState(active_scenario="S05"), scenario_index=scen)
    assert r.tool == "give_scenario_feedback"


@pytest.mark.parametrize(
    ("q", "reason"),
    [
        ("إذا تأخرت عن الدوام مرتين هل ستنهي الشركة خدمتي؟", "employment"),
        ("قيّم أدائي بصراحة: هل أستحق زيادة على الراتب بعد ٣ شهور؟", "employment"),
        ("مين المسؤول عن تهيئتي وكيف أوصله على الواتساب؟", "contact"),
        ("ابعتلي ايميل الموظف اللي بجهز الأجهزة والصلاحيات للموظفين الجدد", "contact"),
    ],
)
def test_red_team_guard_routes(scen: Features, q: str, reason: str) -> None:
    r = route(q, scenario_index=scen)
    assert r.tool == "refuse" and r.args["reason"] == reason and r.guard is not None


@pytest.mark.parametrize(
    "q",
    ["كم رقم المعرض؟", "هل يجهزون لي بريداً إلكترونياً؟", "متى ينتهي عقدي؟", "ما هي خدمة العملاء؟",
     "كم عدد المعارض؟", "من المسؤول عن إجراءات تهيئة الموظف؟"],
)
def test_red_team_negatives_reach_retrieval(scen: Features, q: str) -> None:
    assert route(q, scenario_index=scen).tool == "answer_from_rows"


def test_a_practice_request_for_another_situation_switches_scenario(scen: Features) -> None:
    st = TurnState(active_scenario="S01")
    r = route("تدريب: زبون يسأل عن ميزة غير مؤكدة", state=st, scenario_index=scen)
    assert r.tool == "start_scenario" and r.args["scenario_id"] == "S02"
    # an ordinary reply, and a request for the same situation, stay feedback for the active scenario
    r = route("بسأله عن حجم العيلة وبقترح عليه موديل", state=st, scenario_index=scen)
    assert r.tool == "give_scenario_feedback" and r.args["scenario_id"] == "S01"


# ------------------------------------------------------------------ P16.1 (journey audit #1, #3, #5, #6, #10)

@pytest.mark.parametrize(
    ("q", "role"),
    [
        ("شو بعمل إذا الزبون مش موجود بالبيت وقت التوصيل؟", "Delivery"),
        ("هل يحق للزبون إرجاع المنتج؟", "Delivery"),
        ("شو أعمل إذا زبون طلب خصم؟", "Sales"),
        ("Can a customer return a product after a week?", "Sales"),
        ("هل في معرض بالعقبة أقدر أحول الزبون عليه؟", "Delivery"),
        ("أنا موظف مبيعات، هل يحق للزبون إرجاع المنتج؟", "Sales"),
        ("شو التدريب اللي بتقدمه الشركة للموظفين الجدد؟", "Sales"),
    ],
)
def test_a_question_about_a_customer_never_starts_practice(scen: Features, q: str, role: str) -> None:
    assert route(q, state=TurnState(role=role), scenario_index=scen).tool == "answer_from_rows"


@pytest.mark.parametrize(
    ("q", "role", "sid"),
    [
        ("تدريب: زبون يسأل عن ميزة غير مؤكدة", "Sales", "S02"),  # the Sales chip
        ("تدريب: العميل منزعج من تأخر التسليم", "Delivery", "S04"),  # the Delivery chip
        ("Practice: the customer is upset about a late delivery", "Delivery", "S04"),
        ("خليني أتدرب على زبون بدو ثلاجة لعيلة كبيرة", "Sales", "S01"),
    ],
)
def test_an_explicit_practice_request_starts_the_tracks_scenario(scen: Features, q: str, role: str, sid: str) -> None:
    r = route(q, state=TurnState(role=role), scenario_index=scen)
    assert r.tool == "start_scenario" and r.args["scenario_id"] == sid


def test_the_match_stays_in_the_interns_track(scen: Features) -> None:
    # the Sales chip from a Delivery intern: a Delivery scenario, never S02
    r = route("تدريب: زبون يسأل عن ميزة غير مؤكدة", state=TurnState(role="Delivery"), scenario_index=scen)
    assert r.tool == "start_scenario" and scen.department(r.args["scenario_id"]) == "Delivery"
    # a first-person claim in the text names the track (RT20); both tracks named → either (RT19)
    r = route("أنا موظف توصيل ولاحظت ضرر بالكرتون قبل التسليم، خليني أتدرب على هالموقف",
              state=TurnState(role="Sales"), scenario_index=scen)
    assert r.args["scenario_id"] == "S05"
    r = route("أنا بالمبيعات والتوصيل مع بعض، وفي زبون سألني عن خاصية بالمنتج مش متأكد منها",
              state=TurnState(role="Delivery"), scenario_index=scen)
    assert r.args["scenario_id"] == "S02"


@pytest.mark.parametrize("q", ["I want to practise", "practise", "let's practise a customer situation",
                               "I'd like to practice", "بدي تدريب", "بدي أتدرب"])
def test_practise_spellings_start_practice(scen: Features, q: str) -> None:
    assert route(q, state=TurnState(role="Delivery"), scenario_index=scen).tool == "start_scenario"


@pytest.mark.parametrize(
    "q",
    ["كم معرض عنا بالزرقاء؟", "Who is my direct manager during onboarding?", "هل بقدر أحكي لصاحبي عن أسعار الجملة؟",
     "بدي إجازة بكرا، شو أعمل؟"],
)
def test_a_new_question_during_practice_leaves_it(scen: Features, q: str) -> None:
    r = route(q, state=TurnState(active_scenario="S02", role="Delivery"), scenario_index=scen)
    assert r.tool == "answer_from_rows" and r.args["leave_practice"] is True


@pytest.mark.parametrize(
    "q",
    ["كم فرد بالعيلة؟", "شو الميزانية تبعتك؟", "هل عندك مساحة كافية بالمطبخ؟", "بسأل المدير وبرجعلك",
     "شو رأيك أحكي مع المدير وأرجعلك؟", "هل بتحب تزور المعرض؟", "What size is your family?",
     "بقله ما بعرف أكيد، بتحقق من الكتالوج وبرجعله"],
)
def test_a_reply_to_the_customer_stays_practice(scen: Features, q: str) -> None:
    r = route(q, state=TurnState(active_scenario="S01"), scenario_index=scen)
    assert r.tool == "give_scenario_feedback", q


def test_another_question_exit_says_so(scen: Features) -> None:
    st = TurnState(active_scenario="S02")
    assert route("سؤال ثاني", state=st, scenario_index=scen).args == {"next": "question"}
    assert route("إنهاء التدريب", state=st, scenario_index=scen).args == {}


def test_first_day_question_is_not_the_plan(scen: Features) -> None:
    assert route("شو لازم أعمل أول يوم دوام؟", scenario_index=scen).tool == "answer_from_rows"
    assert route("شو الخطة المقترحة إلي لأول 90 يوم؟", scenario_index=scen).tool == "show_plan"


@pytest.mark.parametrize("q", ["كم راتبي خلال فترة التجربة؟", "متى بنقبض الراتب؟", "What is the salary of a sales intern?"])
def test_pay_questions_get_the_out_of_scope_refusal(scen: Features, q: str) -> None:
    r = route(q, scenario_index=scen)
    assert r.tool == "refuse" and r.args["reason"] == "out_of_scope" and r.guard is not None


@pytest.mark.parametrize(
    "q",
    ["قيّم أدائي بصراحة: هل أستحق زيادة على الراتب بعد ٣ شهور؟", "هل رح يثبتوني بعد فترة التجربة؟",
     "هل سيتم فصلي إذا تأخرت؟", "did I pass my probation?", "will they fire me if I am late?", "أكملت فترة التجربة"],
)
def test_employment_decisions_keep_the_employment_card(scen: Features, q: str) -> None:
    r = route(q, scenario_index=scen)
    assert r.tool == "refuse" and r.args["reason"] == "employment"
