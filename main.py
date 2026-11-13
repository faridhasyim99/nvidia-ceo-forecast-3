# polymarket-nvidia-ceo-forecast-01 entry, third attempt: adaptive
# steppy-price forecaster, v3.
#
# Forecasts the Yes price of every trading market of Polymarket's
# "Next CEO of NVIDIA?" event, one minute at a time, 4 hours ahead, as five
# quantiles (0.05, 0.25, 0.5, 0.75, 0.95) per market per minute.
#
# Model (Python 3.13 standard library only, no network, deterministic).
# v3 = v2 (practice loss 0.267677) plus two changes, each validated on the
# six practice cases AND on a split-half hold-out (first half p00-p02 vs
# second half p03-p05; see TESTS.md):
#
#   1. SUM-TO-ONE MEDIAN CORRECTION (the one real median gain found).
#      The 24 markets are mutually exclusive outcomes of one event, so
#      their Yes prices should sum to ~1. At the checkpoints they do not:
#      S = 0.81-1.09. The median is shrunk toward the renormalised price
#      x/S with k = 1 (exact renormalisation):
#          median(h) = x - x*(S-1)/S * (h/240)
#      The shift accrues linearly with the horizon (the mispricing
#      corrects over the window; a constant shift scores worse, 0.2711).
#      k = 1 is the turn of the curve (k = 0.7: 0.2615, k = 1.0: 0.2609,
#      k = 1.5: 0.2640, k = 2.0: 0.2729) and the principled value, not an
#      argmin. Alone it scores 0.260906 (median error 0.7675 -> 0.7466).
#      Why this works while every drift failed: a LAD (median) regression
#      of the 240-minute move on every price-based feature (trend windows,
#      MA deviations, RMS, jump counts, price level) finds the conditional
#      median is ~0 for all of them -- the median is already optimal
#      single-market. The sum residual is the one signal that lives
#      BETWEEN markets, invisible to any per-market model.
#
#   2. PRICE-SCALED SIGMA FLOOR. A quiet market's band was too narrow
#      for the jump that eventually comes, and the jump a market can
#      make scales with its price level (mean |240-min move|: 0.0024 for
#      x < 0.01, 0.056 for x >= 0.30). The floor becomes
#          max(0.0005, 0.005 * sqrt(x*(1-x)))
#      (0.0023 at x = 0.30, 0.0005 at x = 0.01). Alone it scores
#      0.265281; 0.008 and above are worse (0.2717). The sqrt form beats
#      linear-in-x (0.2588) and quadratic (0.2598) forms on the combo.
#
#   Everything else is v2 unchanged: per-market RMS-120 sigma (capped at
#   0.005), spread(h) = sigma * sqrt(h / (1 + h/180)), inner width
#   b(h) = 0.4 + 0.5*h/240, outer x1.1, trend-conditioned asymmetry
#   +/-20% on the reversion side (60-min trend).
#
# Practice score (LOCAL scorer, see TESTS.md): loss 0.257654 vs v2's
# 0.267677 (-3.7%) and the house baseline's 0.363589 (-29.1%). Per case:
# p00 0.4242, p01 0.2953, p02 0.3253, p03 0.2500, p04 0.1843, p05 0.1231
# (wins 3 of 6 cases; loses p02 +0.0052, p03 +0.0004, p05 +0.0015 --
# the p00 win, -0.044, dominates). Split-half: volatile half 0.3483 vs
# v2's 0.3650, quiet half 0.1858 vs 0.1904 -- wins BOTH halves.
#
# HONEST LIMIT: this does NOT reach the 0.22 stretch target (rank ~3-5
# on the live practice board). The gap needs a genuinely better median,
# and the evidence says the conditional median is already ~optimal for
# every price-based signal tested (LAD in-sample gain 2.7% at h = 240;
# every drift form loses; Hawkes jump clustering, hour-of-day and
# event-level jump counts all lose on the scorer). v3 is the best
# defensible entry found, not a breakthrough. The final is 12 unseen
# cases: if the sum deviates from 1 there as it did in practice, the
# correction helps; if S sits at 1.00, v3 is ~v2 plus the wider floor.
#
# Usage (mirrors the kit starter):
#   mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
# The grader runs one case at a time with only that case's file in /input;
# the program reads every *.in file it finds, in name order, and writes one
# /output/<id>.out per case. Runs in ~0.1 s per case locally, far under the
# 8 s cap; two runs on the same case write byte-identical output.

import json
import math
import os
from os import path

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

# The quantile levels the contest scores, in the order each row lists them.
QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
# Standard normal quantiles at those levels.
Z_OUTER = 1.644854
Z_INNER = 0.674490

# Sigma estimation window: last 120 minutes of 1-minute prices.
SIGMA_WINDOW = 120
SIGMA_FLOOR = 0.0005
SIGMA_CAP = 0.005
# Price-scaled sigma floor: max(SIGMA_FLOOR, PFLOOR_C * sqrt(x*(1-x))).
PFLOOR_C = 0.005
# Horizon saturation: spread(h) = sigma * sqrt(h / (1 + h / SAT_T)).
SAT_T = 180.0
# Outer (5%/95%) widening factor.
OUTER_WIDEN = 1.1
# Inner (25%/75%) narrowing: b(h) = INNER_B0 + INNER_BGROW * h / horizon.
INNER_B0 = 0.4
INNER_BGROW = 0.5
# Trend-conditioned asymmetry: 60-minute trend window and side factor.
TREND_WINDOW = 60
TREND_A = 0.2
# Sum-to-one median correction: shrink toward x/S with k = 1 (exact).
SUM_K = 1.0


def price6(x):
    """x clamped to [0, 1] and rounded to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, x)) * 1e6) / 1e6 + 0.0


def estimate_sigma(prices, x):
    """Per-market 1-minute RMS over the last SIGMA_WINDOW minutes,
    floored at max(SIGMA_FLOOR, PFLOOR_C * sqrt(x*(1-x))) and capped."""
    seg = prices[-SIGMA_WINDOW - 1:] if len(prices) > SIGMA_WINDOW else prices
    if len(seg) < 2:
        rms = SIGMA_FLOOR
    else:
        ss = 0.0
        for i in range(len(seg) - 1):
            d = seg[i + 1] - seg[i]
            ss += d * d
        rms = math.sqrt(ss / (len(seg) - 1))
    floor = max(SIGMA_FLOOR, PFLOOR_C * math.sqrt(max(x * (1.0 - x), 0.0)))
    return min(SIGMA_CAP, max(floor, rms))


def forecast(market, horizon, sum_s=1.0):
    """240 rows (horizon rows) of five quantiles for one market."""
    prices = market["prices"]
    if not prices:
        raise ValueError("market %s has no prices" % market["id"])
    x = prices[-1]
    sigma = estimate_sigma(prices, x)
    # 60-minute trend: positive when the market rose into the checkpoint.
    # Mean reversion: widen the side opposite the trend, narrow the other.
    ref = prices[-1 - TREND_WINDOW] if len(prices) > TREND_WINDOW else prices[0]
    t = x - ref
    sgn = 1.0 if t > 0 else (-1.0 if t < 0 else 0.0)
    lo_m = 1.0 + TREND_A * sgn
    hi_m = 1.0 - TREND_A * sgn
    # Sum-to-one median correction: median drifts toward x/S, accruing
    # linearly with the horizon. Zero when S == 1.
    med_shift = -SUM_K * x * (sum_s - 1.0) / sum_s if sum_s > 0 else 0.0
    rows = []
    for h in range(1, horizon + 1):
        spread = sigma * math.sqrt(h / (1.0 + h / SAT_T))
        b = INNER_B0 + INNER_BGROW * (h / float(horizon))
        z = (-Z_OUTER * OUTER_WIDEN * lo_m, -Z_INNER * b * lo_m, 0.0,
             Z_INNER * b * hi_m, Z_OUTER * OUTER_WIDEN * hi_m)
        med = x + med_shift * (h / float(horizon))
        rows.append([price6(med + zi * spread) for zi in z])
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    inputs = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    for fname in inputs:
        cid = fname[:-3]
        with open(path.join(INPUT_DIR, fname), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        if (len(case["quantiles"]) != len(QUANTILES)
                or any(t != q for t, q in zip(case["quantiles"], QUANTILES))):
            raise ValueError("%s asks for quantiles %r, not %r"
                             % (fname, case["quantiles"], QUANTILES))
        horizon = case["horizon_minutes"]
        sum_s = sum(m["prices"][-1] for m in case["markets"])
        forecasts = [{"id": m["id"], "q": forecast(m, horizon, sum_s)}
                     for m in case["markets"]]
        with open(path.join(OUTPUT_DIR, cid + ".out"), "w",
                  encoding="utf-8") as fh:
            fh.write(json.dumps({"forecasts": forecasts}) + "\n")


if __name__ == "__main__":
    main()
