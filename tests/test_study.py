"""Tests for the expert study analysis (study/, expert-study-protocol.md section 8).

Statistics are checked on small examples counted by hand, so the formulas can be trusted
without scipy.
"""

import csv
import math

import pytest

from core.loader import load_bases
from core.scoring import VIOLATION, make_violation, sort_key
from study.analyze import STUDY_ITEMS, StudyDataError, analyze, load_study, rule_ranks
from study.make_synthetic import write_synthetic
from study.stats import (average_ranks, chi2_sf, kendall_tau_b, kendall_w, median_round_up, spearman_rho,
                         top_k_overlap)


@pytest.fixture(scope="module")
def bases():
    return load_bases()


# ---------- statistics on hand-counted examples ----------

def test_average_ranks():
    assert average_ranks([10, 20, 20, 30]) == [1, 2.5, 2.5, 4]
    assert average_ranks([3, 1, 2]) == [3, 1, 2]


def test_tau_b():
    assert kendall_tau_b([1, 2, 3, 4], [1, 2, 3, 4]) == 1
    assert kendall_tau_b([1, 2, 3, 4], [4, 3, 2, 1]) == -1
    # pairs: 4 concordant, 0 discordant, one tie in x, one tie in y: 4 / sqrt(5 * 5) = 0.8
    assert kendall_tau_b([1, 2, 2, 3], [1, 2, 3, 3]) == pytest.approx(0.8)


def test_spearman():
    # no ties: 1 - 6 * 4 / (5 * 24) = 0.8
    assert spearman_rho([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) == pytest.approx(0.8)
    assert spearman_rho([1, 2, 3], [30, 20, 10]) == pytest.approx(-1)


def test_kendall_w():
    same = [[1, 2, 3, 4]] * 3
    assert kendall_w(same) == pytest.approx(1)
    # rank sums 6, 7, 8, 9; S = 5; W = 12 * 5 / (9 * 60) = 1/9
    assert kendall_w([[1, 2, 3, 4], [1, 2, 3, 4], [4, 3, 2, 1]]) == pytest.approx(1 / 9)


def test_chi2_sf():
    assert chi2_sf(2, 2) == pytest.approx(math.exp(-1))      # df = 2: exactly exp(-x / 2)
    assert chi2_sf(30.1435, 19) == pytest.approx(0.05, abs=1e-4)  # table value of chi-square, df 19, p 0.05
    assert chi2_sf(3.8415, 1) == pytest.approx(0.05, abs=1e-4)


def test_median_round_up_and_top_k():
    assert median_round_up([1, 2, 3]) == 2
    assert median_round_up([3, 4]) == 4
    assert median_round_up([2, 2, 3, 3]) == 3
    assert top_k_overlap([1, 2, 3, 4], [2, 1, 4, 3], 2) == 2
    assert top_k_overlap([1, 2, 3, 4], [4, 3, 2, 1], 2) == 0


# ---------- rules use the service code ----------

def test_rule_b_matches_service_order(bases):
    draft = {i: (bases.scores[i]["s"], bases.scores[i]["o"], bases.scores[i]["d"]) for i in STUDY_ITEMS}
    ranks = rule_ranks(bases, draft, "b")
    by_rule = [i for _, i in sorted(zip(ranks, STUDY_ITEMS))]
    items = {i["id"]: i for i in bases.items}
    service = [v.id for v in sorted((make_violation(bases, items[i], {"answer": VIOLATION}) for i in STUDY_ITEMS),
                                    key=sort_key)]
    assert by_rule == service


def test_rule_a_and_c_keep_ties(bases):
    draft = {i: (bases.scores[i]["s"], bases.scores[i]["o"], bases.scores[i]["d"]) for i in STUDY_ITEMS}
    a = dict(zip(STUDY_ITEMS, rule_ranks(bases, draft, "a")))
    assert a["GEN-019"] == a["GEN-020"]  # both RPN 10
    assert a["PROD-005"] == 1            # RPN 64, the largest of the 20
    c = rule_ranks(bases, draft, "c")
    assert len(set(c)) == 3              # three groups


# ---------- files and the whole pipeline ----------

def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_bad_rankings_are_reported(tmp_path):
    good = list(range(1, 21))
    bad = [1] + list(range(1, 20))  # rank 1 twice, no rank 20
    write_csv(tmp_path / "rankings.csv", ["expert", "category", "years", *STUDY_ITEMS],
              [["Э01", "", "", *good], ["Э02", "", "", *bad]])
    with pytest.raises(StudyDataError) as err:
        load_study(tmp_path)
    assert any("Э02" in p for p in err.value.problems)


def test_scores_must_cover_all_items(tmp_path):
    write_csv(tmp_path / "rankings.csv", ["expert", "category", "years", *STUDY_ITEMS], [["Э01", "", "", *range(1, 21)]])
    write_csv(tmp_path / "scores.csv", ["expert", "situation", "s", "o", "d"], [["Э01", "GEN-019", 5, 2, 6]])
    with pytest.raises(StudyDataError) as err:
        load_study(tmp_path)
    assert any("от 1 до 5" in p for p in err.value.problems)


def test_synthetic_run_is_reproducible(bases, tmp_path):
    write_synthetic(tmp_path, experts=6, seed=1)
    experts = load_study(tmp_path)
    first = analyze(bases, experts, runs=200)
    second = analyze(bases, experts, runs=200)
    assert first["w"] == second["w"] and first["diff_ci"] == second["diff_ci"]
    assert 0 <= first["w"] <= 1
    for r in "abc":
        assert -1 <= first["rules"][r]["tau_b"] <= 1


def test_identical_experts_agree_fully(bases, tmp_path):
    # every expert ranks exactly by rule (b) on the draft scores and gives the draft scores
    draft = {i: (bases.scores[i]["s"], bases.scores[i]["o"], bases.scores[i]["d"]) for i in STUDY_ITEMS}
    ranks = [int(r) for r in rule_ranks(bases, draft, "b")]
    write_csv(tmp_path / "rankings.csv", ["expert", "category", "years", *STUDY_ITEMS],
              [[f"Э0{n}", "", "", *ranks] for n in range(1, 4)])
    write_csv(tmp_path / "scores.csv", ["expert", "situation", "s", "o", "d"],
              [[f"Э0{n}", i, *draft[i]] for n in range(1, 4) for i in STUDY_ITEMS])
    out = analyze(bases, load_study(tmp_path), runs=50)
    assert out["w"] == pytest.approx(1)
    assert out["rules"]["b"]["tau_b"] == pytest.approx(1)
    assert out["score_gap"]["S"] == (0, 0)
