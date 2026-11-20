"""Tests for core/report.py: the DOCX opens and holds the numbers of reference test T8 (project-spec.md, 4.7, 7)."""

from datetime import date
from io import BytesIO

import pytest
from docx import Document

from cases import CASE_A, CASE_B
from core.checklist import build_checklist, default_answers
from core.loader import load_bases
from core.report import build_report
from core.scoring import NA, OK, VIOLATION, evaluate


@pytest.fixture(scope="module")
def bases():
    return load_bases()


def make_report(bases, case, special, default=OK):
    answers = {**default_answers(bases), **case}
    checklist = build_checklist(bases, answers)
    responses = {i["id"]: {"answer": default} for i in checklist.items}
    responses.update(special)
    result = evaluate(bases, checklist, responses)
    data = build_report(bases, answers, checklist, result, responses, on_date=date(2026, 12, 15))
    return Document(BytesIO(data)), result


def text_of(doc):
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


@pytest.fixture(scope="module")
def t8(bases):
    na = {"answer": NA, "comment": "территория не принадлежит предприятию"}
    special = {"GEN-022": {"answer": VIOLATION}, "PROD-010": {"answer": VIOLATION, "comment": "у станков"},
               "TER-001": na, "TER-002": na}
    return make_report(bases, CASE_A, special)


def test_title_and_summary(t8):
    doc, _ = t8
    text = text_of(doc)
    assert "Кейс А. Малая столярная мастерская" in text
    assert "15.12.2026" in text
    assert "03.02.2025" in text
    assert "94.6 %" in text
    assert "соответствует: 35; не соответствует: 2; не применимо: 2" in text
    assert "По анкете скрыто пунктов: 30" in text
    assert "Критических нарушений (угроза жизни, S = 5): 0" in text
    assert "высокий — 1, средний — 1, низкий — 0" in text
    assert "обязательных для всех объектов: TER-001, TER-002" in text


def test_critical_status_in_summary(bases):
    doc, _ = make_report(bases, CASE_A, {"GEN-019": {"answer": VIOLATION}})
    text = text_of(doc)
    assert "Критических нарушений (угроза жизни, S = 5): 1 — устранить в первую очередь: ППР № 1479, п. 26" in text
    assert "97.4 %" in text


def test_register_order_and_columns(t8):
    doc, _ = t8
    register = next(t for t in doc.tables if t.rows[0].cells[0].text == "№")
    rows = register.rows[1:]
    assert len(rows) == 2
    assert rows[0].cells[1].text == "ППР № 1479, п. 35 а, б"      # GEN-022 first (high)
    assert rows[0].cells[5].text == "высокий"
    assert rows[1].cells[1].text == "ППР № 1479, п. 132"          # PROD-010 second (medium)
    assert "Комментарий: у станков" in rows[1].cells[2].text
    assert [c.text for c in register.rows[0].cells][-2:] == ["Срок устранения", "Ответственный"]


def test_matrix_counts(t8):
    doc, _ = t8
    matrix = next(t for t in doc.tables if t.cell(0, 0).text == "S \\ O")
    # row 3 is S = 3 (rows go 5, 4, 3, 2, 1)
    assert matrix.cell(3, 3).text == "1" and matrix.cell(3, 5).text == "1"
    filled = sum(1 for r in range(1, 6) for c in range(1, 6) if matrix.cell(r, c).text)
    assert filled == 2


def test_na_and_coverage(t8):
    doc, _ = t8
    text = text_of(doc)
    assert "Пункты «не применимо»" in text
    assert "территория не принадлежит предприятию" in text
    coverage = next(t for t in doc.tables if t.rows[0].cells[0].text == "Вопрос")
    assert len(coverage.rows) == 11  # header + 10 questions
    statuses = [row.cells[3].text for row in coverage.rows[1:]]
    assert statuses.count("есть нарушения") == 2
    assert statuses.count("к объекту не относится (по анкете)") == 2


def test_warnings_and_unverified_mark(t8):
    doc, _ = t8
    text = text_of(doc)
    assert "п. 2 приказа МЧС России от 14.07.2026 № 525" in text
    assert "черновые" in text
    assert "действуют до 31.12.2026" in text


def test_raised_o_and_unverified_doc_item(bases):
    special = {"PROD-010": {"answer": VIOLATION, "o_raise": 1, "o_reason": "стружка по всему цеху"},
               "DOC-002": {"answer": VIOLATION}}
    doc, result = make_report(bases, CASE_B, special)
    text = text_of(doc)
    assert "Вероятность O повышена с 3 до 4: стружка по всему цеху" in text
    assert "4*" in text
    assert "[требует сверки]" in text                 # DOC items have verified: false
    assert "приказ № 525, вопросы 1.6 и 2.13" in text  # DOC-002 has no PPR item, source is printed


def test_no_violations(bases):
    doc, result = make_report(bases, CASE_A, {})
    text = text_of(doc)
    assert "100.0 %" in text
    assert "Нарушений не выявлено." in text
    assert "Пункты «не применимо»" not in text
