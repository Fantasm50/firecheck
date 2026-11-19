"""Tests for core/session_file.py: save a self-check to a file and load it back (project-spec.md, 4.12)."""

import json
from datetime import date

import pytest

from cases import CASE_A
from core.checklist import build_checklist, default_answers
from core.loader import load_bases
from core.scoring import NA, OK, VIOLATION, evaluate
from core.session_file import SessionFileError, dump_session, load_session


@pytest.fixture(scope="module")
def bases():
    return load_bases()


@pytest.fixture
def case_a(bases):
    answers = {**default_answers(bases), **CASE_A}
    checklist = build_checklist(bases, answers)
    responses = {i["id"]: {"answer": OK, "comment": ""} for i in checklist.items}
    responses["GEN-019"] = {"answer": VIOLATION, "comment": "замок", "o_raise": 1, "o_reason": "все выходы"}
    responses["TER-001"] = {"answer": NA, "comment": "территории нет"}
    return answers, checklist, responses


def test_round_trip_gives_the_same_result(bases, case_a):
    answers, checklist, responses = case_a
    raw = dump_session(bases, answers, responses, today=date(2026, 11, 19))
    s = load_session(bases, raw)
    assert s.warnings == [] and s.complete
    assert s.answers == answers
    assert s.responses == responses
    assert evaluate(bases, s.checklist, s.responses).index == evaluate(bases, checklist, responses).index
    assert json.loads(raw)["saved"] == "2026-11-19"


def test_partial_check_can_be_continued(bases, case_a):
    answers, checklist, responses = case_a
    partial = dict(list(responses.items())[:10])
    s = load_session(bases, dump_session(bases, answers, partial))
    assert not s.complete
    assert s.warnings == [f"Без ответа осталось пунктов: {len(checklist.items) - 10}."]


@pytest.mark.parametrize("raw, text", [
    (b"\x89PNG not json", "не читается"),
    (b'{"hello": 1}', "не файл проверки этого сервиса"),
    (json.dumps({"format": "firecheck-session", "version": 99}).encode(), "неизвестная версия"),
])
def test_foreign_or_broken_files_are_refused(bases, raw, text):
    with pytest.raises(SessionFileError) as err:
        load_session(bases, raw)
    assert text in err.value.problems[0]


def test_bad_questionnaire_in_file_is_refused(bases, case_a):
    answers, _, responses = case_a
    raw = dump_session(bases, {**answers, "people_max": -5}, responses)
    with pytest.raises(SessionFileError):
        load_session(bases, raw)


def test_outdated_file_is_loaded_with_warnings(bases, case_a):
    answers, checklist, responses = case_a
    data = json.loads(dump_session(bases, answers, responses))
    data["base_edition"] = "ред. от 30.03.2023"
    data["answers"]["old_question"] = True
    data["responses"]["OLD-001"] = {"answer": OK}
    data["responses"]["GEN-020"] = {"answer": "maybe"}
    s = load_session(bases, json.dumps(data).encode())
    text = " ".join(s.warnings)
    assert "другой редакции базы норм" in text
    assert "old_question" in text
    assert "OLD-001" in text and "GEN-020" in text
    assert "OLD-001" not in s.responses and "GEN-020" not in s.responses
    assert not s.complete  # GEN-020 lost its wrong answer
