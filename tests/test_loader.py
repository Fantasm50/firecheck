"""Tests for core/loader.py: real bases load, broken copies raise DataError (project-spec.md, 4.9.4, test T10)."""

import shutil

import pytest

from core.loader import DEFAULT_PATHS, DataError, load_bases


def broken_copy(tmp_path, key, old, new):
    """Copy all bases to tmp_path and replace text once in one of them. Originals are not touched."""
    paths = {}
    for name, src in DEFAULT_PATHS.items():
        dst = tmp_path / src.name
        shutil.copy(src, dst)
        paths[name] = dst
    text = paths[key].read_text(encoding="utf-8")
    assert text.count(old) == 1, f"test setup: {old!r} must occur once in {key}"
    paths[key].write_text(text.replace(old, new), encoding="utf-8")
    return paths


def problems_of(paths):
    with pytest.raises(DataError) as err:
        load_bases(paths)
    return err.value.problems


# ---------- real data ----------

def test_real_bases_load():
    bases = load_bases()
    assert len(bases.items) == 69
    assert len(bases.scores) == 69
    assert sum(1 for i in bases.items if i.get("condition") is None) == 31
    assert len(bases.themes) == 8
    assert len(bases.scope) == 10
    assert bases.items[0]["id"] == "GEN-001"  # file order is kept
    assert {"many_people", "mass_people", "no_water_no_aupt"} <= bases.flags
    assert "03.02.2025" in bases.edition


def test_every_demo_item_has_theme():
    bases = load_bases()
    themes = {bases.topic_theme[i["topic"]] for i in bases.items}
    assert themes == set(bases.themes)


# ---------- T10: load errors from project-spec.md 8.2 ----------

def test_missing_score(tmp_path):
    paths = broken_copy(tmp_path, "scores",
                        '  - {id: GEN-019, s: 5, o: 2, d: 1, from: warehouse, why: "выход заперт на ключ: прямая угроза жизни; видно при обходе"}\n',
                        "")
    assert any("GEN-019" in p for p in problems_of(paths))


def test_short_matrix_row(tmp_path):
    paths = broken_copy(tmp_path, "scores", "  3: [L, M, M, H, H]", "  3: [L, M, M, H]")
    assert any("S = 3" in p for p in problems_of(paths))


def test_score_out_of_range(tmp_path):
    paths = broken_copy(tmp_path, "scores", "{id: PROD-010, s: 3,", "{id: PROD-010, s: 6,")
    assert any("PROD-010" in p and "S = 6" in p for p in problems_of(paths))


def test_unknown_flag(tmp_path):
    paths = broken_copy(tmp_path, "requirements",
                        "applies_if: [has_dust_collectors]", "applies_if: [has_crane]")
    assert any("has_crane" in p for p in problems_of(paths))


# ---------- other checks of 4.9.4 ----------

def test_duplicate_id(tmp_path):
    paths = broken_copy(tmp_path, "requirements", "{id: GEN-002,", "{id: GEN-001,")
    assert any("id повторяется: GEN-001" in p for p in problems_of(paths))


def test_extra_score(tmp_path):
    paths = broken_copy(tmp_path, "scores", "{id: GEN-019,", "{id: GEN-999,")
    problems = problems_of(paths)
    assert any("GEN-999" in p for p in problems)   # extra score
    assert any("GEN-019" in p for p in problems)   # and the real item lost its score


def test_condition_without_applies_if(tmp_path):
    paths = broken_copy(tmp_path, "requirements", "applies_if: [has_dust_collectors], ", "")
    assert any("PROD-007" in p and "applies_if" in p for p in problems_of(paths))


def test_unknown_q525(tmp_path):
    paths = broken_copy(tmp_path, "requirements", "{id: GEN-001, ppr: \"2\",   q525: Q525-04",
                        "{id: GEN-001, ppr: \"2\",   q525: Q525-99")
    assert any("Q525-99" in p for p in problems_of(paths))


def test_unknown_topic(tmp_path):
    paths = broken_copy(tmp_path, "themes", "smoking, living]", "smoking]")
    assert any("PROD-008" in p and "living" in p for p in problems_of(paths))


def test_all_problems_reported_at_once(tmp_path):
    paths = broken_copy(tmp_path, "scores", "{id: PROD-010, s: 3, o: 3,", "{id: PROD-010, s: 0, o: 9,")
    problems = problems_of(paths)
    assert any("S = 0" in p for p in problems)
    assert any("O = 9" in p for p in problems)
