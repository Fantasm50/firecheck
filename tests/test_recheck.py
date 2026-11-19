"""Tests for the re-inspection of open violations (core/recheck.py, project-spec.md 4.14)."""

from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from cases import CASE_A
from core.checklist import build_checklist, default_answers
from core.loader import load_bases
from core.plan_export import build_plan_xlsx
from core.recheck import apply_recheck, clean_history
from core.scoring import OK, VIOLATION, evaluate
from core.session_file import dump_session, load_session

DAY = date(2026, 12, 1)


@pytest.fixture(scope="module")
def bases():
    return load_bases()


@pytest.fixture
def before(bases):
    answers = {**default_answers(bases), **CASE_A}
    checklist = build_checklist(bases, answers)
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items}
    responses["GEN-019"] = {"answer": VIOLATION, "comment": ""}
    responses["GEN-022"] = {"answer": VIOLATION, "comment": "у станка"}
    plan = {"GEN-019": {"action": "Снять замок", "owner": "Мастер", "due": "2026-11-25", "status": "done"},
            "GEN-022": {"action": "Заменить удлинитель", "owner": "Электрик", "due": "2026-11-25", "status": "new"}}
    return answers, checklist, responses, plan


def test_fixed_violation_is_closed_and_index_grows(bases, before):
    answers, checklist, responses, plan = before
    result = evaluate(bases, checklist, responses)
    r = apply_recheck(responses, plan, {}, [], {"GEN-019": {"fixed": True, "note": "замок снят"},
                                                "GEN-022": {"fixed": False, "note": "нет нового удлинителя"}},
                      result, DAY)
    assert r.responses["GEN-019"] == {"answer": OK, "comment": "Устранено, подтверждено 01.12.2026: замок снят"}
    assert r.closed["GEN-019"] == {"action": "Снять замок", "owner": "Мастер", "verified_on": "2026-12-01",
                                   "note": "замок снят"}
    assert list(r.plan) == ["GEN-022"] and r.plan["GEN-022"]["status"] == "in_work"
    assert r.responses["GEN-022"]["comment"] == "у станка; Не устранено на 01.12.2026: нет нового удлинителя"
    assert r.history == [{"date": "2026-12-01", "index": str(result.index), "violations": 2, "critical": 1}]
    after = evaluate(bases, checklist, r.responses)
    assert after.index > result.index and len(after.critical) == 0
    assert responses["GEN-019"]["answer"] == VIOLATION  # input is not changed


def test_closed_and_history_survive_the_file(bases, before):
    answers, checklist, responses, plan = before
    r = apply_recheck(responses, plan, {}, [], {"GEN-019": {"fixed": True, "note": ""}},
                      evaluate(bases, checklist, responses), DAY)
    s = load_session(bases, dump_session(bases, answers, r.responses, r.plan, closed=r.closed, history=r.history))
    assert s.closed == r.closed and s.history == r.history
    assert s.warnings == []


def test_broken_history_entries_are_dropped():
    assert clean_history([{"date": "2026-12-01", "index": "90.0", "violations": 2}, {"x": 1}, "junk"]) == [
        {"date": "2026-12-01", "index": "90.0", "violations": 2, "critical": 0}]


def test_closed_sheet_in_excel(bases, before):
    answers, checklist, responses, plan = before
    r = apply_recheck(responses, plan, {}, [], {"GEN-019": {"fixed": True, "note": "замок снят"}},
                      evaluate(bases, checklist, responses), DAY)
    after = evaluate(bases, checklist, r.responses)
    wb = load_workbook(BytesIO(build_plan_xlsx(after, r.plan, closed=r.closed,
                                               items={i["id"]: i for i in checklist.items})))
    done = wb["Устранено"]
    assert done["C2"].value.startswith("Запоры") and done["D2"].value == "Снять замок"
    assert done["F2"].value.date() == DAY and done["G2"].value == "замок снят"
