"""Rank statistics for the expert study (expert-study-protocol.md, section 8). Standard library only.

All functions take plain lists of numbers. Rank 1 means "fix first".
"""

import math


def average_ranks(values):
    """Ranks 1..n of values in ascending order; tied values get the mean of their ranks."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        mean_rank = (start + end) / 2 + 1
        for k in range(start, end + 1):
            ranks[order[k]] = mean_rank
        start = end + 1
    return ranks


def _tie_sum(values, power):
    """Sum over groups of tied values of f(t), where t is the group size: t*(t-1)/2 or t**3 - t."""
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    if power == 2:
        return sum(t * (t - 1) / 2 for t in counts.values())
    return sum(t ** 3 - t for t in counts.values())


def kendall_tau_b(x, y):
    """Kendall's tau-b between two lists of equal length; it accounts for ties in both lists."""
    n = len(x)
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = x[i] - x[j], y[i] - y[j]
            if dx * dy > 0:
                concordant += 1
            elif dx * dy < 0:
                discordant += 1
    n0 = n * (n - 1) / 2
    denominator = math.sqrt((n0 - _tie_sum(x, 2)) * (n0 - _tie_sum(y, 2)))
    if denominator == 0:
        return float("nan")  # one of the lists is constant
    return (concordant - discordant) / denominator


def spearman_rho(x, y):
    """Spearman's rho: Pearson correlation of average ranks."""
    rx, ry = average_ranks(x), average_ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if sx == 0 or sy == 0:
        return float("nan")
    return cov / (sx * sy)


def kendall_w(rankings):
    """Kendall's coefficient of concordance W with the correction for ties.

    rankings: list of m lists, each with ranks of the same n objects.
    W = 12 S / (m^2 (n^3 - n) - m * sum of T), T = sum over tie groups of (t^3 - t).
    """
    m, n = len(rankings), len(rankings[0])
    totals = [sum(r[i] for r in rankings) for i in range(n)]
    mean_total = sum(totals) / n
    s = sum((t - mean_total) ** 2 for t in totals)
    ties = sum(_tie_sum(r, 3) for r in rankings)
    return 12 * s / (m ** 2 * (n ** 3 - n) - m * ties)


def _upper_gamma_q(a, x):
    """Regularized upper incomplete gamma Q(a, x): series for x < a + 1, continued fraction otherwise."""
    if x <= 0:
        return 1.0
    log_front = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1:
        term = total = 1 / a
        k = a
        for _ in range(1000):
            k += 1
            term *= x / k
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return 1 - total * math.exp(log_front)
    # Lentz's continued fraction
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return h * math.exp(log_front)


def chi2_sf(x, df):
    """P(chi-square with df degrees of freedom > x)."""
    return _upper_gamma_q(df / 2, x / 2)


def kendall_w_test(rankings):
    """W, chi-square statistic m (n - 1) W and its p-value with n - 1 degrees of freedom."""
    m, n = len(rankings), len(rankings[0])
    w = kendall_w(rankings)
    chi2 = m * (n - 1) * w
    return w, chi2, chi2_sf(chi2, n - 1)


def top_k_overlap(rank_a, rank_b, k):
    """How many of the k first objects by rank_a are also among the k first by rank_b (ties by index)."""
    first = lambda ranks: set(sorted(range(len(ranks)), key=lambda i: (ranks[i], i))[:k])
    return len(first(rank_a) & first(rank_b))


def median_round_up(values):
    """Median of integer scores; a .5 median (even count) is rounded up (protocol, section 8)."""
    v = sorted(values)
    n = len(v)
    mid = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return math.ceil(mid)


def percentile(sorted_values, q):
    """Percentile q (0..100) of an already sorted list, linear interpolation."""
    pos = (len(sorted_values) - 1) * q / 100
    low = math.floor(pos)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)
