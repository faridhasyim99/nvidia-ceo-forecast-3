# Adaptive steppy-price forecaster v3

Forecasts the Yes price of every trading market of Polymarket's
"Next CEO of NVIDIA?" event, one minute at a time, 4 hours ahead, as five
quantiles (0.05, 0.25, 0.5, 0.75, 0.95) per market per minute.

Method: persistence median plus two validated corrections — a sum-to-one
median correction (the 24 markets are mutually exclusive outcomes, so
their Yes prices should sum to ~1; the median is shrunk toward the
renormalised price x/S with k = 1) and a price-scaled sigma floor
(max(0.0005, 0.005·sqrt(x·(1−x)))) — on top of v2's per-market RMS-120
sigma, horizon-saturating spreads and trend-conditioned band asymmetry.

Python 3.13 standard library only (json, math, os), deterministic, no
network, no model calls. Runs in ~0.1 s per case.

Practice loss (local scorer): **0.257654** vs v1 0.272353, v2 0.267677,
house baseline 0.363589.

Referral code: vz5h17qh
