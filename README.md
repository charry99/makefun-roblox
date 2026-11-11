# Roblox Up-and-Coming Forecaster

This entry forecasts each of the first ten chart places independently using only the supplied history. It uses Python 3.13 and the standard library; it makes no network requests and uses no randomness.

For every place, the forecast combines time-weighted historical place frequencies (24-hour half-life) with a Gaussian kernel centered on each game's latest rank adjusted by its mean rank drift over up to the last five reads. The kernel weight is 0.6 with a four-place standard deviation. It keeps the twelve most likely named games and rescales their probabilities to a total of 0.45. A 20% blend of the persistence baseline adds probability to the latest chart order and its immediate neighbors.

The returned top10 is ordered by each candidate's expected rank using the named place probabilities, with deterministic universe-id tie-breaking. Histories with one or two snapshots work without drift estimates; missing places on short charts are skipped, and missing persistence neighbors are omitted.

## Run

Place history.ndjson and task.json in the input directory, then run:

    MAKEFUN_INPUT_DIR=/path/to/input MAKEFUN_OUTPUT_DIR=/path/to/output python3 main.py

The default directories are /input and /output. The program writes forecast.json to the output directory. task.json may set places and output; absent values default to ten places and forecast.json.

The output has exactly two top-level keys: probabilities, with rows containing universe_id, place, and p, and top10, a list of ten distinct universe ids.
