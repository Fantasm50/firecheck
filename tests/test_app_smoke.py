"""Smoke test of the Streamlit interface without a browser: questionnaire -> demo -> result."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_demo_flow_through_the_interface():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Анкета объекта"
    assert "Не вводите реальные данные предприятия" in at.info[0].value  # prototype notice on every screen
    next(b for b in at.button if b.label.startswith("Демо")).click().run()
    assert not at.exception
    assert at.title[0].value == "Результат самопроверки: Механический цех (демо)"
    assert "Критических нарушений: 1" in at.error[0].value
    assert at.metric[0].value == "86.0 %"
    assert "Не вводите реальные данные предприятия" in at.info[0].value


def test_saved_check_is_restored_on_the_screens():
    """What apply_session puts into the state after loading a file: the checklist screen shows the answers."""
    import json

    from cases import CASE_A
    from core.checklist import build_checklist, default_answers
    from core.loader import load_bases
    from core.scoring import OK, VIOLATION
    from core.session_file import dump_session, load_session

    bases = load_bases()
    answers = {**default_answers(bases), **CASE_A}
    checklist = build_checklist(bases, answers)
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items[:20]}
    responses["GEN-019"] = {"answer": VIOLATION, "comment": "замок"}
    session = load_session(bases, dump_session(bases, answers, responses))
    assert json.loads(dump_session(bases, answers, responses))["format"] == "firecheck-session"

    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    import app
    widgets = app.session_widgets(session.responses)
    assert widgets["a_GEN-019"] == VIOLATION and widgets["c_GEN-019"] == "замок"
    at.session_state.answers = session.answers
    at.session_state.checklist = session.checklist
    at.session_state.responses = session.responses
    at.session_state.widgets = widgets
    at.session_state.step = "fill"
    at.run()
    assert not at.exception
    assert at.title[0].value == "Чек-лист: Кейс А. Малая столярная мастерская"
    assert any(f"Отвечено {len(session.responses)} из {len(checklist.items)}" in str(p.proto) for p in at.get("progress"))


def test_result_screen_shows_plan_and_overdue():
    at = AppTest.from_file(APP, default_timeout=60).run()
    next(b for b in at.button if b.label.startswith("Демо")).click().run()
    assert not at.exception
    assert any(h.value == "План устранения нарушений" for h in at.subheader)
    # a plan with a past deadline, as if loaded from a file
    violation = next(i for i, r in at.session_state.responses.items() if r["answer"] == "violation")
    at.session_state.plan_snapshot = {violation: {"action": "x", "owner": "y", "due": "2020-01-01",
                                                  "status": "in_work"}}
    at.session_state.plan_rev = 99
    at.run()
    assert not at.exception
    assert any("Просрочено мероприятий: 1" in w.value for w in at.warning)


def test_recheck_through_the_interface():
    at = AppTest.from_file(APP, default_timeout=60).run()
    next(b for b in at.button if b.label.startswith("Демо")).click().run()
    next(b for b in at.button if b.label.startswith("Повторная проверка")).click().run()
    assert not at.exception
    assert at.title[0].value.startswith("Повторная проверка")
    radios = [r for r in at.radio if r.key and r.key.startswith("k_")]
    assert len(radios) == 6                      # six open violations in the demo
    for n, r in enumerate(radios):
        r.set_value("fixed" if n == 0 else "open")
    at.run()
    next(b for b in at.button if b.label.startswith("Сохранить итоги")).click().run()
    assert not at.exception
    assert at.title[0].value.startswith("Результат самопроверки")
    assert any("индекс было 86.0 %" in s.value and "нарушений 6 → 5" in s.value for s in at.success)
    assert any("Критических нарушений" in s.value and "нет" in s.value for s in at.success)


def test_result_shows_coverage_line():
    at = AppTest.from_file(APP, default_timeout=60).run()
    next(b for b in at.button if b.label.startswith("Демо")).click().run()
    assert any("по этому объекту проверено вопросов" in c.value and "из 27" in c.value for c in at.caption)
    assert any("скрыто пунктов: 20" in e.label for e in at.expander)
