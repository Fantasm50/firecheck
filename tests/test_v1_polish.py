"""Tests for the V1 improvements of 2026-11-21 (service-roadmap.md 2.1–2.4; project-spec.md 4.6, 4.9.2)."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from docx import Document

from cases import CASE_A
from core.checklist import build_checklist, default_answers
from core.loader import load_bases
from core.report import build_report
from core.scoring import HAS_UNKNOWN, OK, UNKNOWN, VIOLATION, check_responses, evaluate


@pytest.fixture(scope="module")
def bases():
    return load_bases()


@pytest.fixture(scope="module")
def case_a(bases):
    answers = {**default_answers(bases), **CASE_A}
    return answers, build_checklist(bases, answers)


def text_of(doc):
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            parts.extend(c.text for c in row.cells)
    return "\n".join(parts)


# ---------- 2.1 hidden items with the reason ----------

def test_hidden_items_are_listed_with_condition(bases, case_a):
    _, checklist = case_a
    hidden = {i["id"]: i for i in checklist.hidden}
    assert len(hidden) == checklist.hidden_count == 30
    assert not hidden.keys() & {i["id"] for i in checklist.items}
    assert hidden["HOT-001"]["condition"] == "проводятся огневые работы"
    assert all(i.get("condition") for i in checklist.hidden)  # every hidden item has a reason to show


def test_report_lists_hidden_items(bases, case_a):
    answers, checklist = case_a
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items}
    result = evaluate(bases, checklist, responses)
    text = text_of(Document(BytesIO(build_report(bases, answers, checklist, result, responses,
                                                 on_date=date(2026, 11, 21)))))
    assert "Пункты, не включённые по анкете" in text
    assert "проводятся огневые работы" in text
    assert "Остальные 17 вопросов листа" in text


# ---------- 2.3 «не знаю, уточнить» ----------

def test_unknown_is_not_rated_and_listed(bases, case_a):
    _, checklist = case_a
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items}
    responses["GEN-022"] = {"answer": VIOLATION, "comment": ""}
    responses["DOC-001"] = {"answer": UNKNOWN, "comment": "спросить у собственника"}
    assert check_responses(bases, checklist.items, responses) == []    # comment is optional, answer is valid
    result = evaluate(bases, checklist, responses)
    rated = len(checklist.items) - 1                                   # DOC-001 is not rated
    assert result.index == (Decimal(rated - 1) * 100 / rated).quantize(Decimal("0.1"))
    assert [i["id"] for i in result.unknown] == ["DOC-001"]
    assert [v.id for v in result.violations] == ["GEN-022"]
    status = dict((q, s) for q, _, s in result.coverage)
    assert status["Q525-01"] == HAS_UNKNOWN                            # DOC-001 belongs to question 1


def test_violation_outranks_unknown_in_coverage(bases, case_a):
    _, checklist = case_a
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items}
    responses["GEN-019"] = {"answer": UNKNOWN, "comment": ""}
    responses["GEN-020"] = {"answer": VIOLATION, "comment": ""}       # same question 4
    status = dict((q, s) for q, _, s in evaluate(bases, checklist, responses).coverage)
    assert status["Q525-04"] == "есть нарушения"


def test_report_has_unknown_section(bases, case_a):
    answers, checklist = case_a
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items}
    responses["DOC-001"] = {"answer": UNKNOWN, "comment": "спросить у собственника"}
    result = evaluate(bases, checklist, responses)
    text = text_of(Document(BytesIO(build_report(bases, answers, checklist, result, responses))))
    assert "Пункты, требующие уточнения" in text and "спросить у собственника" in text
    assert "требует уточнения: 1" in text


# ---------- 2.4 hints ----------

def test_new_hints(bases):
    items = {i["id"]: i for i in bases.items}
    assert "проектной документации на здание нет" in items["GEN-018"]["note"]
    assert "других отопительных приборов и систем" in items["HEAT-001"]["note"]


# ---------- food and fish processing sites (food-industry-ppr.md, 2026-11-21) ----------

def test_food_site_items_follow_the_questionnaire(bases):
    answers = {**default_answers(bases), **CASE_A, "has_drying_chambers": True, "has_solid_fuel_stoves": True,
               "has_exhaust_ventilation": True, "uses_gas_cylinders": True, "has_freezing_pipelines": True}
    ids = {i["id"] for i in build_checklist(bases, answers).items}
    assert {"PROD-012", "HEAT-003", "HEAT-004", "GEN-025", "GEN-038", "PROD-013"} <= ids
    plain = {i["id"] for i in build_checklist(bases, {**default_answers(bases), **CASE_A}).items}
    assert not plain & {"PROD-012", "HEAT-003", "HEAT-004", "GEN-025", "GEN-038", "PROD-013"}
    items = {i["id"]: i for i in bases.items}
    assert items["HEAT-003"]["periodic"].startswith("печи — не реже 1 раза в 3 месяца")
    assert "жировые отложения" in items["GEN-025"]["check"]
