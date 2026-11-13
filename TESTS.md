# TESTS — NVIDIA CEO forecast entry, third attempt (`entry/main.py`)

## Reference: house baseline, v1, v2, v3

| | loss | median error | 90% coverage |
|---|---|---|---|
| House baseline (starter), practice p00–p05 | **0.363589** | 0.767503 | 0.949642 |
| v1 "Adaptive steppy-price forecaster" | **0.272353** | 0.767503 | 0.859212 |
| v2 (widths: floor 0.0005, inner growth, trend asymmetry) | **0.267677** | 0.767503 | 0.914714 |
| **v3 (v2 + sum-to-one median k=1 + price-scaled sigma floor)** | **0.257654** | **0.746646** | **0.948926** |

## Local scorer validation

No `grade-local` exists for this competition (program/v1: scorer and
reference data stay on the server; the kit's `RULES.txt` says so, and this
VM has no Docker). The local scorer (`dev/score.py`, built by the v1
builder) replicates the sealed scorer exactly — pinball loss
`100 * max(tau*(y-q), (tau-1)*(y-q))` averaged over every
(case, market, minute, tau) — with answers fetched from Polymarket's public
price history and the grid rule from `RULES.txt`. **Validation: the local
scorer reproduces the house baseline EXACTLY — loss 0.363589, median error
0.767503, coverage 0.949642.** v2's 0.267677 was re-verified with the same
scorer before this build started (exact reproduction), and the clean v3
`entry/main.py` was scored fresh: 0.257654, per-case identical to the
parameterised variant run.

## Final entry — measured scores (local scorer, `dev/score.py`)

| case | checkpoint (UTC) | markets | v2 loss | v3 loss | delta |
|---|---|---|---|---|---|
| p00 | 2026-11-12 06:00 | 19 | 0.468502 | 0.424192 | -0.0443 |
| p01 | 2026-11-12 10:00 | 19 | 0.306293 | 0.295257 | -0.0110 |
| p02 | 2026-11-12 14:00 | 19 | 0.320164 | 0.325327 | +0.0052 |
| p03 | 2026-11-12 18:00 | 23 | 0.249670 | 0.250036 | +0.0004 |
| p04 | 2026-11-12 22:00 | 24 | 0.199938 | 0.184337 | -0.0156 |
| p05 | 2026-11-13 02:00 | 24 | 0.121565 | 0.123088 | +0.0015 |
| **overall** | | | **0.267677** | **0.257654** | **-0.0100 (-3.7%)** |

**v3 wins 3 of 6 cases (p00, p01, p04) and loses 3 slightly (p02, p03,
p05).** The p00 win (-0.044) dominates the total; the three losses sum to
+0.007. Median error falls 0.7675 → 0.7466 (-2.7%) — the first median
improvement in three attempts (v1 and v2 both kept 0.767503).

## Hold-out validation (split-half + per-case)

The six cases were split into first half (p00–p02, volatile) and second
half (p03–p05, quiet), the same split v2 used:

| candidate | first half | second half | overall |
|---|---|---|---|
| v2 | 0.364986 | 0.190391 | 0.267677 |
| **v3** | **0.348259** | **0.185820** | **0.257654** |

**v3 wins BOTH halves** (-0.0167 volatile, -0.0046 quiet). Per-case it is
3 wins / 3 small losses, so the hold-out verdict is "wins on both halves,
driven by the volatile half" — the same pattern as v2's widths, and the
same caveat: if the final runs quiet with S ≈ 1.00, the gain shrinks
toward the quiet-half level (-0.005).

The two constants are plateau values, not sharp argmins: k ∈ [0.9, 1.1]
× floor ∈ [0.004, 0.005] all score 0.2576–0.2578, and k = 1.0 is the
theoretical value (exact renormalisation), not a fitted one.

## Runtime / determinism / validity

- All 6 practice cases in **0.57 s total (~0.1 s/case)** — far under the
  8 s/case cap.
- **Determinism: two full runs write byte-identical output** (`diff -r`
  clean). Pure float arithmetic, no randomness, no dict-order dependence.
- Output sizes 223–292 KB per case, well under the 1,048,576-byte cap.
  Shape validated by the scorer: exactly one row per market in the case,
  240 rows × 5 quantiles each, all finite in [0, 1], non-decreasing per row.
  `valid=True` on all six cases.
- Imports: json, math, os only (stdlib).
- Edge cases tested (synthetic case, `dev/edge/`): a market with a single
  price, a market with two prices, a 1,441-minute flat market, a market
  with a late jump, an all-zero market, and a case whose prices sum to
  1.96 (extreme S) — all run cleanly with valid, monotone output.

## How v3 was chosen (experiment log)

All numbers are local-scorer practice losses (v2 0.267677, baseline
0.363589). Full scripts in `dev/`: `build_data.py` (panel Nov 10–13),
`explore.py` / `explore2.py` / `explore3.py`, `regress.py`, `diag.py`,
`main_var.py` + `runvar.sh` (parameterised variant runner).

**The structural fact (dev/build_data.py, explore.py):** the sample is
two regimes. Nov 10–11: 6 markets, sum S swinging 2.91 → 0.34, the
frontrunner (Kress) collapsing 0.485 → 0.0495. From Nov 12 02:35: 19–24
markets, S ≈ 0.82–1.09 — the settled regime the final will resemble.
Every analysis below uses the settled regime (t ≥ Nov 12 06:00) unless
noted, because the early chaos is not the final's regime.

**Median analysis (dev/regress.py, settled regime, 6,200 samples):**
pooled OLS of the 240-min move on 9 features has R² = 0.149, but it lives
in the MEAN (a few big movers). LAD (median) regression: in-sample
median |residual| 0.00146 vs persistence 0.00150 — a 2.7% gain, and the
single-feature LAD coefficients for trend60, trend240, devMA480 and
sumresid are ≈ 0. **The conditional median of the move is ~0 for every
price-based feature.** That is why every drift formulation (v1, v2, and
this build) loses, and why the median is the bottleneck.

**Per-tau diagnostics on v2 (dev/diag.py):** tau 0.50 loss 0.384 (28.7%
of total), tau 0.75 0.375 (28.1%), tau 0.25 0.299 (22.4%), tau 0.95
0.187 (14.0%), tau 0.05 0.093 (6.9%). The inner quantiles dominate
(78.8% combined). PIT deciles are dominated by the tie mass (51.4% of
minutes have y exactly equal to the checkpoint price — steppy prices),
with y above x (28.6%) more often than below (20.0%) but down-moves
bigger. To reach 0.22 from 0.2677 via the median alone, median error
would need to fall ~62% — refuted by the LAD result.

**Volatility analysis (dev/explore3.py, settled regime):** |240-min move|
is predicted by price level (corr +0.55; mean 0.0024 for x < 0.01 vs
0.056 for x ≥ 0.30), own recent jumps (corr +0.48; mean |move| 0.045
if a jump in the last 30 min vs 0.003 if none in 240+ min), and RMS-120
(+0.50). Event-level jumps in OTHER markets add almost nothing
(+0.04–0.07). Hour of day looks strong (09–14 UTC: 0.012–0.027 vs
05–06 UTC: 0.001–0.002) but is two days of data — see the rejected list.

**One-factor-at-a-time from the v2 base:**

| variant | loss | verdict |
|---|---|---|
| sum-to-one k=0.1 / 0.2 / 0.3 | 0.266441 / 0.265287 / 0.264245 | helps, monotonic |
| sum-to-one k=0.4 / 0.5 / 0.7 / 1.0 | 0.263282 / 0.262510 / 0.261483 / **0.260906** | **turn at k=1.0** |
| sum-to-one k=1.5 / 2.0 | 0.263994 / 0.272864 | overshoot — confirms k=1.0 |
| sum k=1.0, constant shift profile | 0.271054 | linear accrual is right |
| sum k=1.0, sqrt(h/240) profile | 0.261134 | ≈ linear |
| price-scaled floor c=0.002 / 0.005 | 0.266889 / 0.265281 | helps |
| price-scaled floor c=0.008 / 0.010 / 0.015 | 0.271741 / 0.278335 / 0.298559 | too wide |
| **sum k=1.0 + floor 0.005 (v3)** | **0.257654** | **shipped** |
| sum k=1.0 + floor 0.004 | 0.257646 | plateau twin |
| sum k=0.9/1.1 + floor 0.004/0.005 | 0.257743–0.257761 | flat plateau |
| floor linear-in-x c=0.01 / quadratic c=0.02 | 0.258844 / 0.259810 | sqrt form wins |
| sigma widen by \|S-1\|, d=0.5 / 1.0 | 0.258175 / 0.258816 | loses |

**Rejected (all worse than v2 0.267677):**

| idea | best score |
|---|---|
| devMA480 drift, shrinkage 0.1 | 0.269598 |
| Hawkes tslj sigma multiplier (A 0.5–1.0, τ 30–60) | 0.269810–0.278361 |
| hour-of-day sigma modulation (half-strength) | 0.284610 |
| outer widening x1.2 (jump insurance) | 0.268713 (cost +0.0010 on practice) |

Why Hawkes loses despite the strong tslj correlation: RMS-120 already
captures recent jumpiness, and the extra widening overshoots — coverage
rises to 0.92 but loss rises. Why hour loses: the 09–14 UTC "effect" is
two days of data and mostly one news event, not a diurnal pattern.

**Jump insurance (measured, NOT shipped):** widening the outer
quantiles x1.1 → x1.2 on top of v3 costs +0.0016 on practice (0.259231).
It is the note's insurance trade — costs a little on practice, buys a
lot if the final is jumpier than practice. The shipped v3 does not
include it; the submit decision can add it (one constant) if the parent
judges the final likelier jumpy than the practice window.

## Honest gaps

1. **The 0.22 stretch target was NOT reached.** v3 scores 0.257654 —
   0.038 short. Rank ~3–5 on the live practice board needs ≈0.22, and
   no principled change tested gets there. The gap needs a genuinely
   better median, and the LAD evidence says the conditional median is
   already ~optimal for every price-based signal. The remaining
   untested direction is trade-flow / order-book signals from the
   Polymarket CLOB API (fitted offline; the graded program cannot fetch
   live) — judged low expected value in the remaining time: the last
   price already reflects the last trade, and the conditional median is
   ~0 for every price feature, so flow would have to beat that.
2. **Practice is not the final.** Six practice cases over 24 hours; the
   final is twelve cases over 48 unseen hours. v3's edge is the sum
   correction (helps when S deviates from 1, as it did at 5 of 6
   checkpoints) plus wider floors for high-price markets. If the final
   runs with S ≈ 1.00 and quiet, v3 is ~v2 plus the floor (+≈0.005).
   If a CEO announcement hits, jump minutes punish narrow bands — v3's
   coverage is 0.949 (above the nominal 0.9), which is the right side
   of that bet, and the outer-x1.2 insurance variant exists if wanted.
3. **Per-case hold-out is 3–3.** v3 wins both split-halves, but per case
   it loses p02 (+0.0052), p03 (+0.0004) and p05 (+0.0015). The overall
   gain is driven by p00 (-0.044), the case with the largest |S-1|
   (1.0785) and the most volatile window. That dependence is real and
   stated here.
4. **The house model forecast's practice score is unknown.** The prize
   gate is the better of the baseline (0.363589) and the house model on
   the FINAL. v3's margin over the baseline is 29.1% on practice.
5. **Only 6 cases / 128 market-cases** underlie every tuning decision.
   Constants were picked from flat plateaus (k = 1.0 is theoretical;
   floor 0.004–0.005 is flat to 8e-6), not sharp optima — but 6 cases
   is still 6 cases.
6. **Scores here are LOCAL estimates**, not server grades — validated by
   the exact baseline reproduction, but the server's final dataset is its
   own recording, and Polymarket may serve slightly different history
   than the recorder captured.

## Still needed for submission (NOT done — main agent's steps)

- GitHub repo (proposed: `faridhasyim99/nvidia-ceo-forecast-3`, owner
  `faridhasyim99`) created AFTER the competition opened, with `main.py` +
  `LICENSE` + `README.md` at the root. Not created here: no GitHub
  auth/token is held.
- Transcripts bundle + pre-submit check from the kit dir:
  `node cli/makefun.mjs check --kit . --repo <repo> --transcripts transcripts.tar.gz`
  (bundle names ONLY this builder session; the main session is
  auto-discovered as parent — the joke-v2 slicing pattern).
- Submit before **21:00 UTC 13 Nov 2026 (04:00 WIB 14 Nov)**:
  `node cli/makefun.mjs submit --competition
  polymarket-nvidia-ceo-forecast-01 --repo-url
  https://github.com/faridhasyim99/nvidia-ceo-forecast-3 --commit <sha>
  --title "Adaptive steppy-price forecaster v3" --bundle transcripts.tar.gz
  --keypair ../makefun-keypair.json`
  (entry is signed; the keypair wallet is the payout wallet. Max 10
  submissions in all, v1 used 1; the last submission before the deadline
  is the final entry — submitting v3 REPLACES v1/v2.)
- Entry files total: main.py 8,057 + LICENSE 1,100 + README.md + TESTS.md
  — the exact snapshot cap is enforced by `check`; if it fails, trim
  TESTS.md first, never main.py.

## Main-agent revision — SAT_T retune (2026-11-13, after local check)

The local `check` failed `thinking_revised`: the entrypoint main.py took its final content from a single builder message (written once, never revised). The fix required a genuine revision in a bundled session, so the main agent ran the entry through the local scorer and tested a small grid of untried constants (SAT_T, TREND_A, PFLOOR_C, INNER_BGROW, SIGMA_WINDOW).

- Jump insurance (OUTER_WIDEN 1.1 → 1.2) was tested first and REJECTED: it loses on every case including the jumpy p00 (+0.0006), overall 0.259231 vs 0.257654. The insurance narrative fails empirically.
- SAT_T scan (the only real gain): 60: 0.256585, 90: 0.255955, 120: 0.256382, 150: 0.256997, 180 (shipped): 0.257654, 240: 0.258848. The curve turns at 90–120. 120 adopted over 90: same overall gain within noise, but 120 does not lose the volatile half (+0.0004, noise) while winning the quiet half (−0.0026), and keeps higher 90% coverage (0.9366 vs 0.9270) for the final's jump risk.
- All other tested constants were noise or worse (TREND_A 0.15: 0.257888, 0.25: 0.257598; PFLOOR_C 0.0045: 0.257481; INNER_BGROW 0.6: 0.258014; SIGMA_WINDOW 60: 0.257419, 240: 0.267753).

Revised v3 (SAT_T 120): practice loss **0.256382** (was 0.257654), median error 0.746646, coverage_90 0.936621, valid=True all 6 cases; deterministic (two runs byte-identical). Per case: p00 0.425255, p01 0.296172, p02 0.324625, p03 0.247400, p04 0.183670, p05 0.118486.
