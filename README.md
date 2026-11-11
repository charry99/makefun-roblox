# Roblox Up-and-Coming Forecaster

A deterministic Python 3 forecaster for the Roblox Up-and-Coming chart. It reads the supplied snapshots and writes one place-by-place forecast without network access or third-party packages.

## Forecast model

For each of the first ten places, the forecast combines three signals:

1. Historical place frequencies, weighted by a 24-hour half-life.
2. A Gaussian rank kernel with weight 0.6 and a four-place standard deviation. The kernel is centered on each game's last observed rank adjusted by its average movement over up to the last five read-to-read transitions, projected by a factor of two.
3. The persistence distribution from the competition starter, blended at 20%.

The highest twelve games in the frequency-plus-kernel distribution are named at each place and scaled to 0.45 total probability before the persistence blend. Remaining mass is left unnamed, as the scoring contract requires. The top-ten order is estimated from the named probability-weighted ranks. Ties are resolved by universe ID, making repeat runs byte-identical.

The model handles short charts by only using observed places for frequency and by omitting unavailable persistence neighbors. One- and two-snapshot histories use zero drift where there are too few shared observations.

## Run

The default input and output directories are /input and /output. Locally, set the environment variables to point to the competition input and a writable output directory:

    MAKEFUN_INPUT_DIR=/path/to/input MAKEFUN_OUTPUT_DIR=/path/to/output python3 main.py

The program reads history.ndjson and, when present, task.json; it writes forecast.json.
