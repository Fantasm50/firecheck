"""Tests for core/sources.py: the base is checked against the PPR text (project-spec.md, 4.11, test T13)."""

import pytest
import yaml
from docx import Document

from core.sources import (DEFAULT_SOURCE, LOCK_PATH, base_references, compare, fingerprint, item_numbers,
                          read_base_items, rule_items)


def make_docx(path, paragraphs):
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)
    return path


EDITION_1 = [
    "ПОСТАНОВЛЕНИЕ",
    "1. Утвердить прилагаемые Правила.",               # item of the resolution, not of the Rules
    "ПРАВИЛА ПРОТИВОПОЖАРНОГО РЕЖИМА В РОССИЙСКОЙ ФЕДЕРАЦИИ",
    "I. Общие положения",
    "1. Запоры на дверях открываются без ключа.",
    "(в ред. Постановления Правительства РФ от 03.02.2025 N 90)",
    "а) второй абзац пункта;",
    "2. Очистка не реже 1 раза в год.",
    "2(1). Документация хранится на объекте.",
    "Приложение N 1",
    "1. Строка приложения, не пункт Правил.",
]


@pytest.fixture
def edition_1(tmp_path):
    return make_docx(tmp_path / "v1.docx", EDITION_1)


# ---------- reading the Rules ----------

def test_rule_items_only_from_the_rules(edition_1):
    items = rule_items(edition_1)
    assert list(items) == ["1", "2", "2(1)"]
    assert items["1"] == "1. Запоры на дверях открываются без ключа. а) второй абзац пункта;"  # note dropped
    assert "приложения" not in " ".join(items.values())


def test_fingerprint_ignores_spaces_and_yo():
    assert fingerprint("Очистка  ещё\nраз") == fingerprint("Очистка еще раз")
    assert fingerprint("не реже 1 раза") != fingerprint("не реже 2 раз")


@pytest.mark.parametrize("ppr, expected", [
    ("26", ["26"]), ("16 б", ["16"]), ("17(1)", ["17(1)"]), ("35 а, б", ["35"]),
    ("354 г, д; 355", ["354", "355"]), ("54 абз. 4", ["54"]), ("60, 397", ["60", "397"]),
])
def test_item_numbers(ppr, expected):
    assert item_numbers(ppr) == expected


# ---------- T13: a new edition with a changed and a removed item ----------

def test_t13_changes_are_found(tmp_path, edition_1):
    lock = {n: fingerprint(t) for n, t in rule_items(edition_1).items()}
    edition_2 = make_docx(tmp_path / "v2.docx", [
        p.replace("1 раза в год", "1 раза в полгода") for p in EDITION_1 if not p.startswith("2(1)")
    ])
    base = [{"id": "A-1", "ppr": "1"}, {"id": "A-2", "ppr": "2 абз. 1"}, {"id": "A-3", "ppr": "2(1)"},
            {"id": "A-4", "ppr": "1, 3"}, {"id": "D-1", "ppr": None, "source": "пост. № 1464"}]
    refs, manual = base_references(base)
    report = compare(rule_items(edition_2), lock, refs, manual)
    assert report.unchanged == ["1"]
    assert report.changed == {"2": ["A-2"]}
    assert report.missing == {"2(1)": ["A-3"], "3": ["A-4"]}
    assert report.manual == ["D-1"]
    assert not report.ok


def test_t13_same_edition_is_ok(edition_1):
    items = rule_items(edition_1)
    refs, manual = base_references([{"id": "A-1", "ppr": "1"}, {"id": "A-2", "ppr": "2"}])
    report = compare(items, {n: fingerprint(t) for n, t in items.items()}, refs, manual)
    assert report.ok and report.unchanged == ["1", "2"]


# ---------- the real base and data/sources_lock.yaml ----------

def test_every_cited_ppr_item_has_a_fingerprint():
    # fails when an item citing a new PPR item is added to the base without a manual check (--update)
    refs, _ = base_references(read_base_items())
    with open(LOCK_PATH, encoding="utf-8") as f:
        points = yaml.safe_load(f)["points"]
    assert sorted(set(refs) - set(points)) == []


@pytest.mark.skipif(not DEFAULT_SOURCE.exists(), reason="sources/ is kept locally, not in git")
def test_real_source_matches_lock():
    with open(LOCK_PATH, encoding="utf-8") as f:
        points = yaml.safe_load(f)["points"]
    refs, manual = base_references(read_base_items())
    report = compare(rule_items(DEFAULT_SOURCE), points, refs, manual)
    assert report.ok, f"изменились: {report.changed}, нет в источнике: {report.missing}"
