"""Tests for core/validity.py: warnings about expiring acts behind the norms base (project-spec.md, 4.11, test T12)."""

import warnings
from datetime import date
from io import BytesIO

import pytest
from docx import Document

from cases import CASE_A
from core.checklist import build_checklist, default_answers
from core.loader import covered_items, load_bases
from core.report import build_report
from core.scoring import OK, evaluate
from core.validity import EXPIRED, SOON, validity_alerts
from test_loader import broken_copy, problems_of


@pytest.fixture(scope="module")
def bases():
    return load_bases()


def levels(bases, on_date):
    return [(a.act[:4], a.level) for a in validity_alerts(bases, on_date)]


# ---------- T12: dates of PPR No 1479 (31.12.2026) and resolution No 1464 (28.02.2027) ----------

def test_t12_acts_and_items(bases):
    acts = {e["act"][:4]: e for e in bases.validity}
    assert acts["ППР "]["last_day"] == date(2026, 12, 31)
    assert acts["пост"]["last_day"] == date(2027, 2, 28)
    assert [i["id"] for i in covered_items(acts["пост"], bases.items)] == ["SYS-001", "SYS-002", "SYS-003"]
    assert all(i.get("ppr") for i in covered_items(acts["ППР "], bases.items))


@pytest.mark.parametrize("on_date, expected", [
    (date(2026, 11, 30), []),                                   # 31 days before the PPR last day
    (date(2026, 12, 1), [("ППР ", SOON)]),                      # 30 days before
    (date(2026, 12, 31), [("ППР ", SOON)]),                     # the last day itself is still valid
    (date(2027, 1, 1), [("ППР ", EXPIRED)]),
    (date(2027, 2, 1), [("ППР ", EXPIRED), ("пост", SOON)]),
    (date(2027, 3, 1), [("ППР ", EXPIRED), ("пост", EXPIRED)]),
])
def test_t12_alert_levels(bases, on_date, expected):
    assert levels(bases, on_date) == expected


def test_t12_alert_text(bases):
    alert = validity_alerts(bases, date(2027, 1, 10))[0]
    assert "срок действия истёк 31.12.2026" in alert.text
    assert f"Пунктов базы на этом акте: {alert.item_count}" in alert.text


def test_report_shows_expired_act(bases):
    answers = {**default_answers(bases), **CASE_A}
    checklist = build_checklist(bases, answers)
    responses = {i["id"]: {"answer": OK} for i in checklist.items}
    result = evaluate(bases, checklist, responses)
    data = build_report(bases, answers, checklist, result, responses, on_date=date(2027, 1, 10))
    text = "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)
    assert "срок действия истёк 31.12.2026" in text


def test_validity_date_must_be_a_date(tmp_path):
    paths = broken_copy(tmp_path, "requirements", "last_day: 2026-12-31", "last_day: скоро")
    assert any("last_day" in p for p in problems_of(paths))


def test_validity_selector_must_match_items(tmp_path):
    paths = broken_copy(tmp_path, "requirements", 'items: "№ 1464"', 'items: "№ 9999"')
    assert any("№ 9999" in p for p in problems_of(paths))


# ---------- guard on the real date: the suite turns red once the base is outdated ----------

def test_base_is_in_force_today(bases):
    alerts = validity_alerts(bases)
    for alert in alerts:
        if alert.level == SOON:
            warnings.warn(alert.text)
    expired = [a.text for a in alerts if a.level == EXPIRED]
    assert not expired, "База норм устарела:\n" + "\n".join(expired)
