# Roblox Up-and-Coming Forecast — make.fun entry

Predicts the Roblox Up-and-Coming chart's top 10 at every hour of the 72 hours
after entries close (competition `roblox-up-and-coming-forecast-01`, $500 pool,
1st $100 / 2nd $70 / 3rd $50 / 4th–10th $20 / 11th–20th $14, escrowed USDC on
Solana). A prize needs a log score strictly above the best house entry: the
persistence baseline and the house model forecast.

## Entry

`main.py` — Python 3.13, standard library only, no network. Reads
`/input/history.ndjson` and `/input/task.json`, writes `/output/forecast.json`
(`{probabilities: [{universe_id, place, p}], top10: [...]}`).

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## Approach

The chart churns fast: in the practice history the top 10 changed in 42 of 44
consecutive reads (median 6 places), and early leaders decay within days. So
the forecast blends three signals per place:

1. **Time-weighted place frequencies** (half-life 24h) — how often each game
   actually held each place, recent reads weighted more.
2. **Gaussian kernel around a drift-adjusted predicted rank** — last rank plus
   the mean rank drift over the last 5 reads, times 2; sigma 4 places.
   Spreads mass over the places a game could plausibly land on, instead of
   betting on one.
3. **20% blend with the persistence baseline** (the kit starter) — steadies
   the model on the rare reads where the chart barely moves.

Per place only the 12 most probable games are named, rescaled to sum to
0.45; the other 0.55 stays unnamed and is shared equally by every game the
place does not name. With ~90 games on the chart the unnamed share is about
0.006 per game (ln -5.1), far better than the log-score floor of ln(1e-4) =
-9.21, so naming a game whose true probability is below the unnamed share
would hurt. The top10 point guess is the 10 games with the lowest expected
rank.

## Validation (walk-forward, contest log-score rule)

Kit practice history: 34 snapshots, 2026-10-30 to 2026-11-07. Three splits
(train 0–19 / 0–24 / 0–29, tested on the reads after each cut):

| split | baseline (starter) | this forecaster | diff |
|-------|-------------------|-----------------|------|
| A (14 test reads) | -742.49 | -596.12 | +146.37 |
| B (9 test reads)  | -467.71 | -361.05 | +106.65 |
| C (4 test reads)  | -120.03 | -126.04 | -6.01 |
| **Total (27 reads)** | **-1330.22** | **-1083.21** | **+247.01** |

+9.1 nats per read, +0.91 per place per read, over the persistence baseline.
The tuned parameters (half-life 24h, kernel weight 0.6, sigma 4.0, cap 0.45,
blend 0.2, drift factor 2.0) sit on a flat optimum — neighbouring settings
score within ~2 nats — so the model is not knife-edge tuned to one split.
Split C (4 reads, an unusually stable stretch) is the only losing split.

Honest limits: the real bar is the house *model* forecast, which is unseen —
beating the persistence baseline does not guarantee beating it. The forecast
is one static matrix for the whole 72h window, so it estimates the average
distribution, not each hour. No created dates survive in the archive
snapshots, so the 28-day age-out is proxied only by first-seen time and rank
drift.

## Files

- `main.py` — the entry program (built in-session for the transcript gate)
- `README.md` — this file
- `LICENSE` — MIT
