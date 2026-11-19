"""Tests for core/plan_export.py: the corrective action plan as an Excel file (project-spec.md 4.13)."""

from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from cases import CASE_A
from core.checklist import build_checklist, default_answers
from core.loader import load_bases
from core.plan_export import HEADERS, build_plan_xlsx
from core.scoring import OK, VIOLATION, evaluate

TODAY = date(2026, 11, 19)


@pytest.fixture(scope="module")
def sheet():
    bases = load_bases()
    answers = {**default_answers(bases), **CASE_A}
    checklist = build_checklist(bases, answers)
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items}
    responses["GEN-019"] = {"answer": VIOLATION, "comment": ""}   # S = 5, first
    responses["GEN-022"] = {"answer": VIOLATION, "comment": ""}
    result = evaluate(bases, checklist, responses)
    plan = {"GEN-019": {"action": "Снять замок", "owner": "Мастер", "due": "2026-11-01", "status": "in_work"},
            "GEN-022": {"action": "Заменить удлинитель", "owner": "Электрик", "due": "2026-12-01", "status": "new"}}
    data = build_plan_xlsx(result, plan, "Кейс А", on_date=TODAY)
    return load_workbook(BytesIO(data)).active


def test_title_and_headers(sheet):
    assert sheet["A1"].value == "План устранения нарушений: Кейс А"
    assert "19.11.2026" in sheet["A2"].value
    assert [c.value for c in sheet[4]] == HEADERS


def test_rows_in_priority_order_with_plan(sheet):
    first, second = sheet[5], sheet[6]
    assert first[1].value == "ППР № 1479, п. 26" and first[3].value == "высокий"
    assert first[4].value == "Снять замок" and first[5].value == "Мастер" and first[7].value == "в работе"
    assert first[6].value == datetime(2026, 11, 1)          # a real date, not text
    assert second[4].value == "Заменить удлинитель" and second[7].value == "новое"
    assert sheet[7][0].value is None                         # only two violations


def test_overdue_is_marked(sheet):
    assert sheet["I5"].value == "да"                           # 01.11 < 19.11, still in work
    assert sheet["G5"].fill.fgColor.rgb.endswith("F4C7C3")
    assert sheet["I6"].value in (None, "")                     # due in December


def test_status_list_and_header_frozen(sheet):
    validations = sheet.data_validations.dataValidation
    assert any("в работе" in v.formula1 and "H5:H6" in str(v.sqref) for v in validations)
    assert sheet.freeze_panes == "A5"
