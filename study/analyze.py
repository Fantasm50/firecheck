"""Analysis of the expert study (expert-study-protocol.md, section 8).

Input: a folder with two CSV files (UTF-8, comma separated, can be edited in Excel):
    rankings.csv  - stage 1: expert,category,years,<20 situation ids>; each cell is a rank 1..20, 1 = fix first
    scores.csv    - stage 2: expert,situation,s,o,d; integers 1..5
An expert may appear in one file only (two-panel design) or in both (one panel).

Run:
    .venv/bin/python -m study.analyze study/data/synthetic
    .venv/bin/python -m study.analyze study/data/synthetic --out study/synthetic-report.md
"""

import argparse
import csv
import random
from pathlib import Path
from types import SimpleNamespace

from core.loader import load_bases
from core.scoring import GROUP_RANK, group, sort_key
from study.stats import (average_ranks, kendall_tau_b, kendall_w_test, median_round_up, percentile,
                         spearman_rho, top_k_overlap)

# Cards of appendix A of the protocol, in card order
STUDY_ITEMS = [
    "GEN-019", "GEN-020", "SYS-001", "GEN-034", "HOT-001", "PROD-005", "EXT-001", "GEN-009", "GEN-031", "GEN-012",
    "GEN-008", "GEN-022", "HEAT-001", "TER-002", "GEN-027", "TER-001", "GEN-002", "GEN-004", "EXT-003", "DOC-005",
]
RULES = {
    "a": "(а) RPN = S × O × D",
    "b": "(б) правило сервиса (п. 4.5)",
    "c": "(в) только группа приоритета",
}
BOOTSTRAP_RUNS = 2000
SEED = 2026  # fixed seed: the same data always give the same intervals


class StudyDataError(Exception):
    """Raised when the CSV files are filled in wrongly. Holds the list of problems."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("Данные исследования заполнены неверно:\n- " + "\n- ".join(problems))


# ---------- loading and checks ----------

def load_study(folder):
    """Read both CSV files into a list of experts: {"id", "category", "years", "ranks", "scores"}."""
    folder = Path(folder)
    experts = {}
    problems = []
    n = len(STUDY_ITEMS)

    with open(folder / "rankings.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = row["expert"].strip()
            missing = [i for i in STUDY_ITEMS if not (row.get(i) or "").strip()]
            if missing:
                problems.append(f"{code}: нет рангов для {', '.join(missing)}")
                continue
            try:
                ranks = [int(row[i]) for i in STUDY_ITEMS]
            except ValueError:
                problems.append(f"{code}: ранг должен быть целым числом")
                continue
            if sorted(ranks) != list(range(1, n + 1)):
                problems.append(f"{code}: ранги должны быть числами 1…{n} без повторов")
                continue
            experts[code] = {"id": code, "category": row.get("category", ""), "years": row.get("years", ""),
                             "ranks": ranks, "scores": None}

    path = folder / "scores.csv"
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                code, item = row["expert"].strip(), row["situation"].strip()
                if item not in STUDY_ITEMS:
                    problems.append(f"{code}: неизвестная ситуация {item}")
                    continue
                try:
                    sod = tuple(int(row[k]) for k in ("s", "o", "d"))
                except ValueError:
                    problems.append(f"{code}, {item}: S, O, D должны быть целыми числами")
                    continue
                if not all(1 <= v <= 5 for v in sod):
                    problems.append(f"{code}, {item}: S, O, D должны быть от 1 до 5")
                    continue
                expert = experts.setdefault(code, {"id": code, "category": "", "years": "", "ranks": None,
                                                   "scores": None})
                expert["scores"] = expert["scores"] or {}
                expert["scores"][item] = sod
    for e in experts.values():
        if e["scores"] is not None and set(e["scores"]) != set(STUDY_ITEMS):
            problems.append(f"{e['id']}: баллы есть не для всех {n} ситуаций")

    if problems:
        raise StudyDataError(problems)
    return list(experts.values())


# ---------- rules (a), (b), (c) ----------

def rule_ranks(bases, scores, rule):
    """Ranks of STUDY_ITEMS under a rule; scores: item id -> (S, O, D)."""
    if rule == "a":
        return average_ranks([-scores[i][0] * scores[i][1] * scores[i][2] for i in STUDY_ITEMS])
    if rule == "c":
        return average_ranks([GROUP_RANK[group(bases, scores[i][0], scores[i][1])] for i in STUDY_ITEMS])
    # rule (b): the same sort key as in the service (core/scoring.py), so no ties
    items = [SimpleNamespace(id=i, s=scores[i][0], o=scores[i][1], d=scores[i][2],
                             group=group(bases, scores[i][0], scores[i][1])) for i in STUDY_ITEMS]
    position = {v.id: n for n, v in enumerate(sorted(items, key=sort_key), 1)}
    return [float(position[i]) for i in STUDY_ITEMS]


def consensus(rankers):
    """Mean rank of each situation over experts (the reference ranking, protocol section 8)."""
    return [sum(e["ranks"][k] for e in rankers) / len(rankers) for k in range(len(STUDY_ITEMS))]


def median_scores(scorers):
    """Median S, O, D of each situation over experts, .5 rounded up."""
    return {i: tuple(median_round_up([e["scores"][i][k] for e in scorers]) for k in range(3))
            for i in STUDY_ITEMS}


def taus(bases, reference, scores):
    return {r: kendall_tau_b(rule_ranks(bases, scores, r), reference) for r in RULES}


# ---------- bootstrap ----------

def bootstrap(bases, experts, runs=BOOTSTRAP_RUNS, seed=SEED):
    """Resample experts with replacement inside each kind (ranks only, scores only, both).

    Returns sorted lists of tau-b for each rule and of the difference tau(b) - tau(a).
    """
    rng = random.Random(seed)
    kinds = {}
    for e in experts:
        kinds.setdefault((e["ranks"] is not None, e["scores"] is not None), []).append(e)
    results = {r: [] for r in RULES}
    diff = []
    for _ in range(runs):
        sample = [rng.choice(group_) for group_ in kinds.values() for _ in group_]
        rankers = [e for e in sample if e["ranks"] is not None]
        scorers = [e for e in sample if e["scores"] is not None]
        t = taus(bases, consensus(rankers), median_scores(scorers))
        for r in RULES:
            results[r].append(t[r])
        diff.append(t["b"] - t["a"])
    return {r: sorted(v) for r, v in results.items()}, sorted(diff)


# ---------- full analysis ----------

def analyze(bases, experts, runs=BOOTSTRAP_RUNS):
    rankers = [e for e in experts if e["ranks"] is not None]
    scorers = [e for e in experts if e["scores"] is not None]
    if len(rankers) < 2 or not scorers:
        raise StudyDataError(["нужно не меньше 2 экспертов с рангами и 1 с баллами"])
    reference = consensus(rankers)
    expert_scores = median_scores(scorers)
    draft_scores = {i: (bases.scores[i]["s"], bases.scores[i]["o"], bases.scores[i]["d"]) for i in STUDY_ITEMS}
    w, chi2, p = kendall_w_test([e["ranks"] for e in rankers])
    boot, diff = bootstrap(bases, experts, runs)

    out = {
        "n_rankers": len(rankers), "n_scorers": len(scorers),
        "w": w, "chi2": chi2, "p": p, "reference": reference,
        "expert_scores": expert_scores, "draft_scores": draft_scores, "rules": {}, "draft_rules": {},
        "diff_ci": (percentile(diff, 2.5), percentile(diff, 97.5)), "runs": runs,
        "per_expert": {e["id"]: {r: kendall_tau_b(e["ranks"], rule_ranks(bases, expert_scores, r)) for r in RULES}
                       for e in rankers},
    }
    for r in RULES:
        ranks = rule_ranks(bases, expert_scores, r)
        out["rules"][r] = {
            "tau_b": kendall_tau_b(ranks, reference), "rho": spearman_rho(ranks, reference),
            "top5": top_k_overlap(ranks, reference, 5), "top10": top_k_overlap(ranks, reference, 10),
            "ci": (percentile(boot[r], 2.5), percentile(boot[r], 97.5)),
        }
        draft = rule_ranks(bases, draft_scores, r)
        out["draft_rules"][r] = {"tau_b": kendall_tau_b(draft, reference), "top5": top_k_overlap(draft, reference, 5)}
    out["score_gap"] = {}
    for k, name in enumerate("SOD"):
        gaps = [abs(draft_scores[i][k] - expert_scores[i][k]) for i in STUDY_ITEMS]
        out["score_gap"][name] = (sum(gaps) / len(gaps), sum(1 for g in gaps if g >= 2))
    return out


def report(out, title):
    """Markdown report in Russian."""
    f = lambda x: f"{x:.3f}"
    lines = [
        f"# {title}", "",
        f"Экспертов с ранжированием: {out['n_rankers']}; с баллами S, O, D: {out['n_scorers']}. "
        f"Бутстреп: {out['runs']} повторов, seed {SEED}.", "",
        "## ИВ1. Согласованность экспертов", "",
        f"- W Кендалла = **{f(out['w'])}**; χ² = {out['chi2']:.2f}, ст. свободы {len(STUDY_ITEMS) - 1}, "
        f"p = {out['p']:.2g}.",
        "- Порог «достаточной» согласованности берётся из учебника (протокол, раздел 8), здесь не задаётся.", "",
        "## ИВ2. Правила на экспертных баллах против эталона", "",
        "| Правило | τ-b | 95 % интервал τ-b | ρ Спирмена | Совпадение топ-5 | Совпадение топ-10 |",
        "|---|---|---|---|---|---|",
    ]
    for r, name in RULES.items():
        x = out["rules"][r]
        lines.append(f"| {name} | {f(x['tau_b'])} | {f(x['ci'][0])} … {f(x['ci'][1])} | {f(x['rho'])} | "
                     f"{x['top5']} из 5 | {x['top10']} из 10 |")
    low, high = out["diff_ci"]
    verdict = ("интервал целиком выше нуля: гипотеза подтверждается" if low > 0 else
               "интервал целиком ниже нуля: RPN лучше, гипотеза отвергается" if high < 0 else
               "интервал включает ноль: разница не доказана")
    lines += ["", f"**Разность τ-b(б) − τ-b(а):** 95 % интервал {f(low)} … {f(high)} — {verdict}.", "",
              "## По каждому эксперту (описательно)", "",
              "| Эксперт | " + " | ".join(RULES.values()) + " |", "|---|" + "---|" * len(RULES)]
    for code, t in out["per_expert"].items():
        lines.append(f"| {code} | " + " | ".join(f(t[r]) for r in RULES) + " |")
    lines += ["", "## ИВ3. Черновые баллы против экспертных", "",
              "| Шкала | Средняя абсолютная разница | Ситуаций с разницей ≥ 2 |", "|---|---|---|"]
    for name, (mean_gap, big) in out["score_gap"].items():
        lines.append(f"| {name} | {mean_gap:.2f} | {big} из {len(STUDY_ITEMS)} |")
    lines += ["", "| Правило на черновых баллах | τ-b с эталоном | Совпадение топ-5 |", "|---|---|---|"]
    for r, name in RULES.items():
        x = out["draft_rules"][r]
        lines.append(f"| {name} | {f(x['tau_b'])} | {x['top5']} из 5 |")
    order = sorted(range(len(STUDY_ITEMS)), key=lambda k: out["reference"][k])
    lines += ["", "## Эталон: средний ранг экспертов", "",
              "| Место | Ситуация | Средний ранг | Медиана S, O, D |", "|---|---|---|---|"]
    for place, k in enumerate(order, 1):
        item = STUDY_ITEMS[k]
        lines.append(f"| {place} | {item} | {out['reference'][k]:.2f} | {', '.join(map(str, out['expert_scores'][item]))} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Анализ экспертного исследования (expert-study-protocol.md)")
    parser.add_argument("folder", help="папка с rankings.csv и scores.csv")
    parser.add_argument("--out", help="сохранить отчёт в файл .md")
    parser.add_argument("--runs", type=int, default=BOOTSTRAP_RUNS, help="число повторов бутстрепа")
    args = parser.parse_args()
    text = report(analyze(load_bases(), load_study(args.folder), args.runs), f"Результаты: {args.folder}")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
