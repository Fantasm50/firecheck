"""Tests for core/checklist.py: reference test T6 (project-spec.md, 8.2), derived flags, answer checks."""

import pytest

from cases import CASE_A, CASE_B, CASE_C
from core.checklist import AnswersError, build_checklist, by_theme, check_answers, default_answers, true_flags
from core.loader import load_bases


@pytest.fixture(scope="module")
def bases():
    return load_bases()


def answers(bases, case):
    """Fill the empty questionnaire with the answers of a case."""
    return {**default_answers(bases), **case}


def ids(checklist):
    return {item["id"] for item in checklist.items}


def conditional(checklist):
    return {item["id"] for item in checklist.items if item.get("applies_if")}


# ---------- T6: checklists of the synthetic cases ----------

CASE_A_ITEMS = {
    "DOC-001", "EXT-001", "EXT-002", "EXT-003", "EXT-004", "EXT-005",
    "GEN-001", "GEN-002", "GEN-006", "GEN-007", "GEN-009", "GEN-012", "GEN-013", "GEN-016",
    "GEN-017", "GEN-018", "GEN-019", "GEN-020", "GEN-021", "GEN-022", "GEN-023", "GEN-024",
    "GEN-027", "GEN-033", "GEN-034", "GEN-037", "HEAT-001", "INS-001", "INS-002",
    "PROD-001", "PROD-005", "PROD-007", "PROD-008", "PROD-010", "TER-001", "TER-002",
    "SYS-001", "SYS-002", "SYS-003",  # no systems, "do not know" whether required (2026-11-17)
}


def test_case_a(bases):
    checklist = build_checklist(bases, answers(bases, CASE_A))
    assert len(checklist.items) == 39
    assert ids(checklist) == CASE_A_ITEMS
    assert conditional(checklist) == {"EXT-005", "GEN-017", "HEAT-001", "PROD-005", "PROD-007",
                                      "SYS-001", "SYS-002", "SYS-003"}
    assert not ids(checklist) & {"GEN-003", "GEN-004", "HEAT-002", "GEN-032", "GEN-035"}
    assert not any(i.startswith("HOT-") for i in ids(checklist))
    assert checklist.hidden_count == 30  # 24 + 6 food-site items (2026-11-21)


def test_case_a_water_not_required(bases):
    checklist = build_checklist(bases, answers(bases, {**CASE_A, "water_required": "no"}))
    assert len(checklist.items) == 38
    assert "EXT-005" not in ids(checklist)


def test_required_systems(bases):
    # SYS-* appear when a system is absent and it is required or unknown; "no" or having it hides them
    def sys_ids(**extra):
        return sorted(i for i in ids(build_checklist(bases, answers(bases, {**CASE_A, **extra})))
                      if i.startswith("SYS-"))
    assert sys_ids() == ["SYS-001", "SYS-002", "SYS-003"]
    assert sys_ids(aps_required="no", soue_required="yes", aupt_required="no") == ["SYS-002"]
    assert sys_ids(has_aps=True, has_soue=True, aupt_required="yes") == ["SYS-003"]
    assert sys_ids(has_aps=True, has_soue=True, has_aupt=True) == []


def test_case_b(bases):
    checklist = build_checklist(bases, answers(bases, CASE_B))
    assert len(checklist.items) == 48
    assert conditional(checklist) == {
        "DOC-002", "EXT-005", "GEN-003", "GEN-004", "GEN-015", "GEN-017", "GEN-026",
        "GEN-031", "GEN-032", "HEAT-001", "HEAT-002",
        "HOT-001", "HOT-002", "HOT-003", "HOT-004", "HOT-005", "HOT-006",
    }


def test_case_c(bases):
    checklist = build_checklist(bases, answers(bases, CASE_C))
    assert len(checklist.items) == 41
    assert conditional(checklist) == {
        "DOC-002", "DOC-003", "GEN-003", "GEN-008", "GEN-017", "GEN-026",
        "PROD-002", "PROD-004", "PROD-005", "PROD-011",
    }


def test_items_keep_file_order(bases):
    checklist = build_checklist(bases, answers(bases, CASE_B))
    order = [item["id"] for item in bases.items]
    positions = [order.index(item["id"]) for item in checklist.items]
    assert positions == sorted(positions)


# ---------- derived flags (4.1) ----------

def flags_for(bases, **case):
    return true_flags(bases, answers(bases, {"people_max": 0, "workplaces_per_floor": 0, **case}))


def test_many_people(bases):
    assert "many_people" in flags_for(bases, people_max=50)
    assert "many_people" in flags_for(bases, workplaces_per_floor=10)
    assert "many_people" not in flags_for(bases, people_max=49, workplaces_per_floor=9)


def test_mass_people(bases):
    assert "mass_people" in flags_for(bases, people_max=50)
    assert "mass_people" not in flags_for(bases, people_max=49, workplaces_per_floor=30)


def test_no_water_no_aupt(bases):
    assert "no_water_no_aupt" in flags_for(bases, water_required="unknown")
    assert "no_water_no_aupt" in flags_for(bases, water_required="yes")
    assert "no_water_no_aupt" not in flags_for(bases, water_required="no")
    assert "no_water_no_aupt" not in flags_for(bases, has_indoor_hydrants=True)
    assert "no_water_no_aupt" not in flags_for(bases, has_aupt=True)


def test_hot_work_still_needs_shield_without_water_requirement(bases):
    # item 410: shields are required where hot works are done, even if water supply is not required
    case = {**CASE_A, "water_required": "no", "does_hot_work": True}
    assert "EXT-005" in ids(build_checklist(bases, answers(bases, case)))


# ---------- questionnaire checks (4.9.1) ----------

def test_default_answers(bases):
    empty = default_answers(bases)
    assert empty["water_required"] == "unknown"
    assert empty["has_aps"] is False
    assert empty["people_max"] is None


def test_empty_numbers_are_rejected(bases):
    with pytest.raises(AnswersError) as err:
        build_checklist(bases, default_answers(bases))
    assert len(err.value.problems) == 2  # people_max and workplaces_per_floor


@pytest.mark.parametrize("bad", [-1, 2.5, True, "8"])
def test_bad_number(bases, bad):
    problems = check_answers(bases, answers(bases, {**CASE_A, "people_max": bad}))
    assert len(problems) == 1


def test_bad_choice_and_unknown_key(bases):
    problems = check_answers(bases, answers(bases, {**CASE_A, "water_required": "maybe", "has_crane": True}))
    assert any("maybe" in p for p in problems)
    assert any("has_crane" in p for p in problems)


def test_bad_flag_value(bases):
    problems = check_answers(bases, answers(bases, {**CASE_A, "has_aps": "да"}))
    assert len(problems) == 1


# ---------- grouping by theme (4.3) ----------

def test_by_theme_case_a(bases):
    groups = by_theme(bases, build_checklist(bases, answers(bases, CASE_A)).items)
    names = [name for name, _ in groups]
    assert "Огневые работы" not in names  # empty themes are skipped
    assert names == [t for t in bases.themes if t in names]  # table order kept
    assert sum(len(group) for _, group in groups) == 39
    evacuation = dict(groups)["Эвакуация"]
    assert [i["id"] for i in evacuation] == ["GEN-009", "GEN-018", "GEN-019", "GEN-020", "GEN-037", "GEN-024"]
