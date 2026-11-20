"""Check the norms base against the text of the PPR (project-spec.md, 4.11, test T13).

For every PPR item the base refers to, data/sources_lock.yaml keeps a short fingerprint
(hash) of the item text in the edition the base was verified against. When a new edition
of the PPR appears, run this check on its .docx: it lists the items whose text changed or
disappeared and the base items that rest on them. A person then re-reads those items:
the program finds changes, it does not decide whether the base is still correct.

Run from the project folder:
    .venv/bin/python -m core.sources                  # check against the default source file
    .venv/bin/python -m core.sources <new_ppr.docx>   # check against a new edition
    .venv/bin/python -m core.sources --update         # save fingerprints after a manual check
"""

import hashlib
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from docx import Document

from core.loader import DEFAULT_PATHS, PROJECT_DIR

LOCK_PATH = PROJECT_DIR / "data" / "sources_lock.yaml"
DEFAULT_SOURCE = PROJECT_DIR / "sources" / "ppr-1479-red-2025-02-03.docx"

RULES_START = "ПРАВИЛА ПРОТИВОПОЖАРНОГО РЕЖИМА"  # text before it is the resolution itself (its own items 1-3)
RULES_END = "Приложение N 1"                     # appendices have their own numbering
ITEM_START = re.compile(r"^(\d+(?:\(\d+\))?)\.\s")        # "26. ...", "2(1). ..."
SECTION_HEADING = re.compile(r"^[IVXLC]+\.\s")             # "II. Территории ..."
EDITION_NOTE = re.compile(r"^\((в ред\.|.*введен|.*утратил)")  # "(в ред. Постановления ... N 90)"


def rule_items(path):
    """Text of every item of the Rules in a .docx: {"26": "...", "2(1)": "..."}."""
    paragraphs = [p.text.strip() for p in Document(path).paragraphs]
    texts, current, inside = {}, None, False
    for text in paragraphs:
        if not inside:
            inside = text.upper().startswith(RULES_START)
            continue
        if text.startswith(RULES_END):
            break
        if not text or SECTION_HEADING.match(text) or EDITION_NOTE.match(text):
            continue
        match = ITEM_START.match(text)
        if match:
            current = match.group(1)
            texts[current] = []
        if current:
            texts[current].append(text)
    return {number: " ".join(lines) for number, lines in texts.items()}


def fingerprint(text):
    """Short hash of the text; spaces and the letter ё are normalized, so formatting does not matter."""
    normal = " ".join(text.replace("ё", "е").split())
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()[:16]


def item_numbers(ppr):
    """PPR item numbers from the ppr field: "54 абз. 4" -> ["54"], "354 г, д; 355" -> ["354", "355"]."""
    numbers = []
    for part in re.split(r"[,;]", str(ppr)):
        match = re.match(r"\s*(\d+(?:\(\d+\))?)", part)
        if match:
            numbers.append(match.group(1))
    return numbers


def base_references(items):
    """PPR item number -> ids of base items that cite it; and ids of items without a PPR reference."""
    refs, manual = {}, []
    for item in items:
        numbers = item_numbers(item["ppr"]) if item.get("ppr") else []
        if not numbers:
            manual.append(item["id"])
        for number in numbers:
            refs.setdefault(number, []).append(item["id"])
    return refs, manual


@dataclass
class Report:
    unchanged: list = field(default_factory=list)  # PPR item numbers with the same text
    changed: dict = field(default_factory=dict)    # number -> base item ids
    missing: dict = field(default_factory=dict)    # number -> base item ids (no such item in the source)
    unlocked: dict = field(default_factory=dict)   # number -> base item ids (no fingerprint saved yet)
    manual: list = field(default_factory=list)     # base items without a PPR reference (DOC-*, SYS-*)

    @property
    def ok(self):
        return not (self.changed or self.missing or self.unlocked)


def compare(source_items, lock_points, refs, manual):
    """Compare the item texts of a source with the saved fingerprints, for the items the base cites."""
    report = Report(manual=manual)
    for number in sorted(refs, key=_number_key):
        if number not in source_items:
            report.missing[number] = refs[number]
        elif number not in lock_points:
            report.unlocked[number] = refs[number]
        elif fingerprint(source_items[number]) != lock_points[number]:
            report.changed[number] = refs[number]
        else:
            report.unchanged.append(number)
    return report


def _number_key(number):
    main, _, sub = number.partition("(")
    return int(main), int(sub.rstrip(")") or 0)


def read_base_items(path=None):
    """Items of one requirements file, or of both bases (production and warehouse) by default."""
    items = []
    for one in [path] if path else [DEFAULT_PATHS["requirements"], DEFAULT_PATHS["warehouse"]]:
        with open(one, encoding="utf-8") as f:
            items += yaml.safe_load(f)["requirements"]
    return items


def make_lock(source_path, items, edition):
    """Fingerprints of every PPR item the base cites, for data/sources_lock.yaml."""
    source_items = rule_items(source_path)
    refs, _ = base_references(items)
    absent = [n for n in refs if n not in source_items]
    if absent:
        raise ValueError("в источнике нет пунктов: " + ", ".join(sorted(absent, key=_number_key)))
    return {
        "meta": {"source": Path(source_path).name, "edition": edition, "made": date.today().isoformat(),
                 "note": "Сохранять только после ручной сверки пунктов базы с этой редакцией."},
        "points": {n: fingerprint(source_items[n]) for n in sorted(refs, key=_number_key)},
    }


def print_report(report, source_name):
    print(f"Сверка базы с источником: {source_name}")
    print(f"Без изменений: {len(report.unchanged)} пунктов ППР.")
    for title, group in [("ИЗМЕНИЛСЯ ТЕКСТ", report.changed), ("НЕТ В ИСТОЧНИКЕ", report.missing),
                         ("НЕТ ОТПЕЧАТКА (запустите --update после сверки)", report.unlocked)]:
        if group:
            print(f"\n{title}:")
            for number, ids in group.items():
                print(f"  п. {number} -> {', '.join(ids)}")
    print(f"\nСверяются вручную (нет ссылки на пункт ППР): {', '.join(report.manual)}")
    print("\nИтог: " + ("всё совпадает." if report.ok else "есть расхождения, перечитайте эти пункты."))


def main(args):
    update = "--update" in args
    paths = [a for a in args if not a.startswith("--")]
    source = Path(paths[0]) if paths else DEFAULT_SOURCE
    if not source.exists():
        print(f"Нет файла источника: {source}")
        return 2
    items = read_base_items()
    if update:
        with open(DEFAULT_PATHS["requirements"], encoding="utf-8") as f:
            edition = yaml.safe_load(f)["meta"]["edition"]
        lock = make_lock(source, items, edition)
        with open(LOCK_PATH, "w", encoding="utf-8") as f:
            f.write("# Fingerprints of PPR items cited by the base (core/sources.py). Generated, do not edit.\n")
            yaml.safe_dump(lock, f, allow_unicode=True, sort_keys=False)
        print(f"Сохранено отпечатков: {len(lock['points'])} -> {LOCK_PATH.name}")
        return 0
    with open(LOCK_PATH, encoding="utf-8") as f:
        lock = yaml.safe_load(f)
    refs, manual = base_references(items)
    report = compare(rule_items(source), lock["points"], refs, manual)
    print_report(report, source.name)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
