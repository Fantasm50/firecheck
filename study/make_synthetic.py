"""Synthetic answers for a dry run of the analysis (expert-study-protocol.md, section 8).

NOT real data. Synthetic experts are built from the draft scores plus random noise, so the dry run
checks the pipeline (files -> checks -> statistics -> report), not the hypothesis.

Run:
    .venv/bin/python -m study.make_synthetic            # writes study/data/synthetic/*.csv
"""

import csv
import random
from pathlib import Path

from core.loader import load_bases
from study.analyze import STUDY_ITEMS

OUT = Path(__file__).parent / "data" / "synthetic"
EXPERTS = 8
SEED = 7
CATEGORIES = ["инспектор", "специалист предприятия", "преподаватель"]


def clip(v):
    return max(1, min(5, v))


def write_synthetic(out=OUT, experts=EXPERTS, seed=SEED):
    """Write rankings.csv and scores.csv with synthetic experts into the folder out."""
    rng = random.Random(seed)
    bases = load_bases()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "rankings.csv", "w", encoding="utf-8", newline="") as f_rank, \
            open(out / "scores.csv", "w", encoding="utf-8", newline="") as f_score:
        ranks_out = csv.writer(f_rank)
        scores_out = csv.writer(f_score)
        ranks_out.writerow(["expert", "category", "years", *STUDY_ITEMS])
        scores_out.writerow(["expert", "situation", "s", "o", "d"])
        for n in range(1, experts + 1):
            code = f"Э{n:02d}"
            # stage 1: hidden priority = severity first, occurrence second, plus personal noise
            priority = {i: 3 * bases.scores[i]["s"] + bases.scores[i]["o"] + rng.gauss(0, 2.5) for i in STUDY_ITEMS}
            order = sorted(STUDY_ITEMS, key=lambda i: -priority[i])
            rank = {item: place for place, item in enumerate(order, 1)}
            ranks_out.writerow([code, rng.choice(CATEGORIES), rng.randint(3, 25), *(rank[i] for i in STUDY_ITEMS)])
            # stage 2: draft scores shifted by -1, 0 or +1
            for i in STUDY_ITEMS:
                sc = bases.scores[i]
                scores_out.writerow([code, i, *(clip(sc[k] + rng.choice([-1, 0, 0, 1])) for k in ("s", "o", "d"))])


def main():
    write_synthetic()
    print(f"Синтетические ответы {EXPERTS} экспертов записаны в {OUT}")


if __name__ == "__main__":
    main()
