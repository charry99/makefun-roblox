# Roblox Up-and-Coming forecaster

This entry forecasts each of the chart's first ten places independently from
the snapshots in `history.ndjson`. It combines exponentially time-weighted
observed place frequencies (24-hour half-life) with a Gaussian rank kernel
(weight 0.6, sigma 4 places). The kernel center adjusts each currently listed
game's rank by twice its mean rank movement over the last five adjacent reads.

For each place, the twelve highest scoring games in the frequency/kernel
model share 0.45 probability mass. The forecast then blends that model with
the persistence baseline at 80/20. Persistence assigns 0.5 to the current
game at that place and its neighboring-place probabilities as specified by
the competition starter. The unassigned probability is the unnamed chart
mass. `top10` orders games by their summed expected place across the named
probabilities.

The implementation uses only the Python standard library and is deterministic.
It reads `MAKEFUN_INPUT_DIR/history.ndjson` (default `/input/history.ndjson`)
and writes `MAKEFUN_OUTPUT_DIR/forecast.json` (default `/output/forecast.json`).

Run it with:

```sh
python3 main.py
```

When running locally, set `MAKEFUN_INPUT_DIR` and `MAKEFUN_OUTPUT_DIR` to
directories containing the input files and receiving the forecast.
