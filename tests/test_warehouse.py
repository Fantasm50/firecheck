"""Tests for the second object type, the warehouse (task 3.3, warehouse-ppr.md, project-spec.md 4.1)."""

from datetime import date
from io import BytesIO

import pytest
from docx import Document

import app
from cases import CASE_A
from core.checklist import build_checklist, default_answers
from core.loader import load_bases
from core.report import build_report
from core.scoring import OK, VIOLATION, evaluate
from core.session_file import dump_session, load_session
from test_loader import broken_copy, problems_of


@pytest.fixture(scope="module")
def bases():
    return load_bases()


def warehouse(bases, **extra):
    answers = {**default_answers(bases), "object_type": "warehouse", "people_max": 8, "workplaces_per_floor": 4,
               **extra}
    return build_checklist(bases, answers)


def ids(checklist):
    return {i["id"] for i in checklist.items}


def test_default_type_is_production(bases):
    assert default_answers(bases)["object_type"] == "production"
    checklist = build_checklist(bases, {**default_answers(bases), **CASE_A})
    assert checklist.object_type == "production"
    assert not any(i.startswith("WH-") for i in ids(checklist))
    assert "GEN-014" not in ids(checklist) and "GEN-014" not in {i["id"] for i in checklist.hidden}
    assert checklist.hidden_count == 30  # warehouse items are not "hidden by the questionnaire" for a shop


def test_plain_warehouse(bases):
    checklist = warehouse(bases)
    assert checklist.object_type == "warehouse"
    assert len(checklist.items) == 38
    assert {"WH-001", "WH-004", "WH-007", "WH-008", "WH-010", "WH-013", "PROD-008"} <= ids(checklist)
    assert "GEN-021" not in ids(checklist)  # replaced by the stricter item 293 (WH-007, WH-008)
    assert not {i for i in ids(checklist) if i.startswith("PROD-")} - {"PROD-008"}
    assert len(checklist.hidden) == 44


def test_gas_pack_follows_the_questionnaire(bases):
    gas = ids(warehouse(bases, stores_gas_cylinders=True))
    assert {"WH-002", "WH-G01", "WH-G02", "WH-G03", "WH-G04", "WH-G05", "WH-G06", "WH-G08", "WH-G10"} <= gas
    assert "WH-G09" not in gas
    oxygen = ids(warehouse(bases, stores_oxygen_cylinders=True))
    assert {"WH-G01", "WH-G06", "WH-G08", "WH-G09"} <= oxygen and "WH-G02" not in oxygen


def test_flags_of_the_other_type_do_not_count(bases):
    shop = build_checklist(bases, {**default_answers(bases), **CASE_A, "has_ramp": True, "has_mezzanines": True})
    assert not {"WH-005", "GEN-014"} & ids(shop)
    store = warehouse(bases, has_dust_collectors=True)
    assert "PROD-007" not in ids(store)


def test_gen_038_keeps_the_warehouse_exception(bases):
    item = next(i for i in bases.items if i["id"] == "GEN-038")
    assert "кроме складских зданий для их хранения" in item["check"]
    assert "warehouse" in item["object_types"]


def test_demo_warehouse(bases):
    answers = {**default_answers(bases), **app.DEMO_WAREHOUSE}
    checklist = build_checklist(bases, answers)
    responses = {i["id"]: {"answer": VIOLATION if i["check"].startswith(app.DEMO_WAREHOUSE_VIOLATIONS) else OK}
                 for i in checklist.items}
    result = evaluate(bases, checklist, responses)
    assert len(checklist.items) == 38
    assert [v.id for v in result.violations] == ["WH-010", "WH-002", "WH-007", "WH-005", "EXT-003"]
    assert str(result.index) == "86.8"
    assert [v.id for v in result.critical] == ["WH-010"]
    coverage = {q: (n, status) for q, n, status in result.coverage}
    assert len(coverage) == 11 and coverage["Q525-17"] == (6, "есть нарушения")

    text = "\n".join(p.text for p in Document(BytesIO(build_report(
        bases, answers, checklist, result, responses, on_date=date(2026, 11, 21)))).paragraphs)
    assert "Тип объекта: склад" in text
    assert "Остальные 16 вопросов листа" in text


def test_session_keeps_the_type(bases):
    checklist = warehouse(bases, has_ramp=True)
    answers = {**default_answers(bases), "object_type": "warehouse", "people_max": 8, "workplaces_per_floor": 4,
               "has_ramp": True}
    responses = {i["id"]: {"answer": OK} for i in checklist.items}
    session = load_session(bases, dump_session(bases, answers, responses))
    assert session.checklist.object_type == "warehouse" and session.complete


def test_flag_must_be_asked_for_the_item_type(tmp_path):
    paths = broken_copy(tmp_path, "questionnaire", "id: has_ramp, object_types: [warehouse, production]",
                        "id: has_ramp, object_types: [production]")
    problems = problems_of(paths)
    assert any("WH-005" in p and "has_ramp" in p and "warehouse" in p for p in problems)


def test_reuse_must_point_to_production_items(tmp_path):
    paths = broken_copy(tmp_path, "warehouse", "territory: [TER-001, TER-002]", "territory: [TER-001, TER-009]")
    assert any("TER-009" in p for p in problems_of(paths))


# ---------- variant Б: storage rooms of a production building ----------

def shop(bases, **extra):
    return build_checklist(bases, {**default_answers(bases), **CASE_A, **extra})


def test_storage_rooms_add_storage_items_to_a_shop(bases):
    plain = shop(bases, has_ramp=True)                     # storage question without the gate: ignored
    assert not any(i.startswith("WH-") for i in ids(plain)) and plain.hidden_count == 30
    assert "Q525-17" not in plain.scope
    rooms = shop(bases, has_storage_rooms=True, has_ramp=True)
    assert {"WH-001", "WH-004", "WH-005", "WH-007", "WH-008"} <= ids(rooms)
    assert not {"WH-010", "WH-011", "WH-013", "GEN-014"} & ids(rooms)  # general items stay warehouse-only
    assert rooms.scope[-4:] == ["Q525-17", "Q525-19", "Q525-21", "Q525-22"]
    assert len(rooms.items) == len(plain.items) + 5


def test_storage_rooms_coverage_and_questions(bases):
    from core.checklist import asked_flags
    checklist = shop(bases, has_storage_rooms=True, stores_gas_cylinders=True)
    responses = {i["id"]: {"answer": OK} for i in checklist.items}
    responses["WH-G02"] = {"answer": VIOLATION}
    coverage = {q: status for q, _, status in evaluate(bases, checklist, responses).coverage}
    assert coverage["Q525-17"] == "есть нарушения" and len(coverage) == 11
    closed = {f["id"] for f in asked_flags(bases, "production", {})}
    opened = {f["id"] for f in asked_flags(bases, "production", {"has_storage_rooms": True})}
    assert "has_storage_rooms" in closed and "has_ramp" not in closed
    assert opened - closed == {"stores_flammable_packages", "stores_gas_cylinders", "stores_oxygen_cylinders",
                               "has_open_storage", "has_ramp", "does_repacking", "has_incandescent_lamps",
                               "has_rail_tracks"}


def test_gate_does_not_touch_a_warehouse(bases):
    assert ids(warehouse(bases, has_ramp=True)) == ids(warehouse(bases, has_ramp=True, has_storage_rooms=True))
