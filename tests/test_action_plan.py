"""Tests for the corrective action plan (core/action_plan.py, project-spec.md 4.13)."""

from datetime import date, datetime
from io import BytesIO

import pytest
from docx import Document

from cases import CASE_A
from core.action_plan import clean_plan, due_text, is_overdue, overdue_ids, parse_due
from core.checklist import build_checklist, default_answers
from core.loader import load_bases
from core.report import build_report
from core.scoring import OK, VIOLATION, evaluate
from core.session_file import dump_session, load_session

TODAY = date(2026, 11, 19)


@pytest.fixture(scope="module")
def bases():
    return load_bases()


def test_parse_due_accepts_editor_values():
    assert parse_due("2026-12-01") == date(2026, 12, 1)
    assert parse_due(datetime(2026, 12, 1, 0, 0)) == date(2026, 12, 1)  # pandas Timestamp is a datetime
    assert parse_due("") is None and parse_due(None) is None and parse_due("завтра") is None
    assert parse_due(float("nan")) is None  # empty cell


def test_clean_plan_keeps_only_current_violations():
    raw = {"GEN-019": {"action": " Снять замок ", "owner": "Мастер", "due": "2026-12-01", "status": "in_work"},
           "OLD-001": {"action": "x"},
           "GEN-020": {"status": "wrong", "due": "не дата"}}
    plan = clean_plan(raw, ["GEN-019", "GEN-020", "GEN-022"])
    assert list(plan) == ["GEN-019", "GEN-020", "GEN-022"]
    assert plan["GEN-019"] == {"action": "Снять замок", "owner": "Мастер", "due": "2026-12-01", "status": "in_work"}
    assert plan["GEN-020"] == {"action": "", "owner": "", "due": "", "status": "new"}
    assert plan["GEN-022"]["status"] == "new"


def test_overdue_means_late_and_not_closed():
    assert is_overdue({"due": "2026-11-18", "status": "in_work"}, TODAY)
    assert not is_overdue({"due": "2026-11-19", "status": "new"}, TODAY)      # due today is not late yet
    assert not is_overdue({"due": "2026-11-01", "status": "done"}, TODAY)
    assert not is_overdue({"due": "", "status": "new"}, TODAY)
    plan = {"A": {"due": "2026-11-01", "status": "new"}, "B": {"due": "2026-11-01", "status": "verified"}}
    assert overdue_ids(plan, TODAY) == ["A"]


def test_due_text():
    assert due_text({"due": "2026-12-01", "status": "in_work"}) == "01.12.2026 (в работе)"
    assert due_text({"due": "2026-12-01", "status": "new"}) == "01.12.2026"
    assert due_text({"due": "", "status": "done"}) == "(устранено)"
    assert due_text({}) == ""


def case_a_with_violations(bases):
    answers = {**default_answers(bases), **CASE_A}
    checklist = build_checklist(bases, answers)
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items}
    responses["GEN-019"] = {"answer": VIOLATION, "comment": ""}
    responses["GEN-022"] = {"answer": VIOLATION, "comment": ""}
    return answers, checklist, responses


def test_plan_is_saved_and_loaded(bases):
    answers, _, responses = case_a_with_violations(bases)
    plan = {"GEN-019": {"action": "Снять замок", "owner": "Мастер", "due": "2026-12-01", "status": "in_work"}}
    s = load_session(bases, dump_session(bases, answers, responses, plan))
    assert s.plan["GEN-019"] == plan["GEN-019"]
    assert s.plan["GEN-022"]["status"] == "new"   # every violation gets an entry
    assert set(s.plan) == {"GEN-019", "GEN-022"}


def test_file_without_plan_still_loads(bases):
    import json
    answers, _, responses = case_a_with_violations(bases)
    data = json.loads(dump_session(bases, answers, responses))
    del data["plan"]
    s = load_session(bases, json.dumps(data).encode())
    assert s.warnings == [] and set(s.plan) == {"GEN-019", "GEN-022"}


def test_plan_fills_report_columns(bases):
    answers, checklist, responses = case_a_with_violations(bases)
    result = evaluate(bases, checklist, responses)
    plan = {"GEN-019": {"action": "Снять замок", "owner": "Мастер смены", "due": "2026-12-01", "status": "in_work"}}
    doc = Document(BytesIO(build_report(bases, answers, checklist, result, responses, on_date=TODAY, plan=plan)))
    register = next(t for t in doc.tables if t.rows[0].cells[0].text == "№")
    row = next(r for r in register.rows[1:] if r.cells[1].text == "ППР № 1479, п. 26")
    assert "Мероприятие: Снять замок" in row.cells[2].text
    assert row.cells[6].text == "01.12.2026 (в работе)"
    assert row.cells[7].text == "Мастер смены"
