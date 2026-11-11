#!/usr/bin/env python3
"""Forecast Roblox Up-and-Coming chart places from its recorded history."""

import json
import math
import os
from datetime import datetime


PLACES = 10
HALF_LIFE_HOURS = 24.0
KERNEL_WEIGHT = 0.6
KERNEL_SIGMA = 4.0
DRIFT_MULTIPLIER = 2.0
PERSISTENCE_BLEND = 0.2
NAMED_MASS = 0.45
NAMED_GAMES = 12


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_history(path):
    snapshots = []
    with open(path, "r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            raw = json.loads(line)
            rows = sorted(raw.get("up_and_coming") or [], key=lambda row: row["rank"])
            chart = [int(row["universe_id"]) for row in rows]
            snapshots.append({
                "time": timestamp(raw["at"]),
                "chart": chart,
                "rank": {uid: i + 1 for i, uid in enumerate(chart)},
            })
    return snapshots


def persistence_forecast(last_chart):
    result = {}
    for place in range(1, PLACES + 1):
        probs = {}
        if place <= len(last_chart):
            probs[last_chart[place - 1]] = 0.5
            if place == 1:
                if len(last_chart) > 1:
                    probs[last_chart[1]] = 0.3
            else:
                probs[last_chart[place - 2]] = 0.15
                if place < len(last_chart):
                    probs[last_chart[place]] = 0.15
        result[place] = probs
    return result


def forecast(snapshots):
    if not snapshots:
        raise ValueError("history.ndjson contains no snapshots")

    latest = snapshots[-1]
    last_chart = latest["chart"]
    baseline = persistence_forecast(last_chart)
    freq = {place: {} for place in range(1, PLACES + 1)}
    weight_sums = {place: 0.0 for place in range(1, PLACES + 1)}

    for snapshot in snapshots:
        age = (latest["time"] - snapshot["time"]).total_seconds() / 3600.0
        weight = 0.5 ** (max(0.0, age) / HALF_LIFE_HOURS)
        for place in range(1, min(PLACES, len(snapshot["chart"])) + 1):
            uid = snapshot["chart"][place - 1]
            freq[place][uid] = freq[place].get(uid, 0.0) + weight
            weight_sums[place] += weight

    # Rank drift is the mean rank change over the last five adjacent reads
    # where the game appeared in both reads. Positive drift means falling.
    predicted_rank = {}
    lookback_start = max(0, len(snapshots) - 5)
    for uid, rank in latest["rank"].items():
        changes = []
        for index in range(lookback_start, len(snapshots) - 1):
            older = snapshots[index]["rank"]
            newer = snapshots[index + 1]["rank"]
            if uid in older and uid in newer:
                changes.append(newer[uid] - older[uid])
        drift = sum(changes) / len(changes) if changes else 0.0
        predicted_rank[uid] = rank + drift * DRIFT_MULTIPLIER

    probabilities = {}
    for place in range(1, PLACES + 1):
        base = {}
        if weight_sums[place] > 0:
            base = {uid: value / weight_sums[place]
                    for uid, value in freq[place].items()}

        scores = dict(base)
        for uid, predicted in predicted_rank.items():
            distance = (predicted - place) / KERNEL_SIGMA
            scores[uid] = scores.get(uid, 0.0) + KERNEL_WEIGHT * math.exp(-0.5 * distance * distance)

        total = sum(scores.values())
        if total > 0:
            scores = {uid: value / total for uid, value in scores.items()}
        # Keep insertion order for exact ties, matching the stable ordering of
        # the frequency map used to evaluate the tuned model.
        selected = sorted(scores.items(), key=lambda item: -item[1])[:NAMED_GAMES]
        selected_total = sum(value for _, value in selected)
        model_probs = ({uid: value * NAMED_MASS / selected_total
                        for uid, value in selected} if selected_total else {})

        combined = {}
        for uid, value in model_probs.items():
            combined[uid] = combined.get(uid, 0.0) + (1.0 - PERSISTENCE_BLEND) * value
        for uid, value in baseline[place].items():
            combined[uid] = combined.get(uid, 0.0) + PERSISTENCE_BLEND * value
        probabilities[place] = combined

    # Rank games by expected place from the per-place named probabilities.
    # A game with no named mass receives the same outside-chart estimate used
    # in the tuning backtest.
    expected = {}
    for place, games in probabilities.items():
        for uid, probability in games.items():
            expected[uid] = expected.get(uid, 0.0) + place * probability
    for uid in last_chart:
        expected.setdefault(uid, float(PLACES + 5))

    ordered = sorted(expected, key=lambda uid: (expected[uid], uid))
    top10 = ordered[:PLACES]
    if len(top10) < PLACES:
        # Contract requires ten distinct ids even for an unusually short chart.
        candidate = 1
        used = set(top10)
        while len(top10) < PLACES:
            if candidate not in used:
                top10.append(candidate)
                used.add(candidate)
            candidate += 1

    rows = []
    for place in range(1, PLACES + 1):
        for uid, probability in sorted(probabilities[place].items()):
            if probability > 0.0:
                rows.append({"universe_id": uid, "place": place, "p": probability})
    return {"probabilities": rows, "top10": top10}


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    result = forecast(read_history(os.path.join(input_dir, "history.ndjson")))
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "forecast.json")
    with open(output_path, "w", encoding="utf-8", newline="\n") as output:
        json.dump(result, output, separators=(",", ":"), ensure_ascii=False)
        output.write("\n")


if __name__ == "__main__":
    main()
