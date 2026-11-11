#!/usr/bin/env python3
"""Deterministic place-by-place forecaster for Roblox Up-and-Coming."""

import json
import math
import os
from datetime import datetime


PLACES = 10
HALF_LIFE_HOURS = 24.0
KERNEL_WEIGHT = 0.6
KERNEL_SIGMA = 4.0
DRIFT_HORIZON = 2.0
NAMED_MASS = 0.45
NAMED_GAMES = 12
PERSISTENCE_BLEND = 0.20


def parse_time(value):
    """Parse an ISO timestamp, treating a missing UTC suffix as UTC."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def snapshot_rows(snapshot):
    """Return rows in chart order with rank as a stable fallback."""
    rows = snapshot.get("up_and_coming") or []
    return sorted(
        rows,
        key=lambda row: (
            int(row.get("rank") or 10**9),
            int(row.get("universe_id") or 0),
        ),
    )


def prepare_history(history):
    """Normalize reads to charts, rank maps, and timestamps."""
    prepared = []
    for snapshot in history:
        rows = snapshot_rows(snapshot)
        chart = []
        rankof = {}
        for index, row in enumerate(rows, 1):
            uid = row.get("universe_id")
            if isinstance(uid, int) and not isinstance(uid, bool) and uid > 0:
                chart.append(uid)
                rankof[uid] = int(row.get("rank") or index)
        if chart:
            prepared.append(
                {
                    "chart": chart,
                    "rankof": rankof,
                    "time": parse_time(snapshot.get("at")),
                }
            )
    return prepared


def snapshot_age_hours(newer, older, fallback):
    """Use actual read spacing, with a deterministic fallback for bad times."""
    if newer is not None and older is not None:
        try:
            hours = (newer - older).total_seconds() / 3600.0
            if hours >= 0.0:
                return hours
        except (TypeError, AttributeError):
            pass
    return fallback


def persistence_forecast(last_chart):
    """Build the kit's 0.5/0.3/0.15 persistence distribution safely."""
    result = {}
    count = len(last_chart)
    for place in range(1, PLACES + 1):
        probabilities = {}
        if place <= count:
            probabilities[last_chart[place - 1]] = 0.5
            if place == 1:
                if count > 1:
                    probabilities[last_chart[1]] = 0.3
            else:
                if place - 2 < count:
                    uid = last_chart[place - 2]
                    probabilities[uid] = probabilities.get(uid, 0.0) + 0.15
                if place < count:
                    uid = last_chart[place]
                    probabilities[uid] = probabilities.get(uid, 0.0) + 0.15
        result[place] = probabilities
    return result


def build_forecast(history):
    """Combine decayed frequencies, drift kernels, and persistence."""
    reads = prepare_history(history)
    if not reads:
        return {"probabilities": [], "top10": []}

    last = reads[-1]
    last_chart = last["chart"]
    end_time = last["time"]
    place_weights = {place: {} for place in range(1, PLACES + 1)}
    place_totals = {place: 0.0 for place in range(1, PLACES + 1)}

    for read_index, read in enumerate(reads):
        fallback_age = float(len(reads) - 1 - read_index)
        age_hours = snapshot_age_hours(end_time, read["time"], fallback_age)
        weight = 0.5 ** (age_hours / HALF_LIFE_HOURS)
        for place in range(1, min(PLACES, len(read["chart"])) + 1):
            uid = read["chart"][place - 1]
            place_weights[place][uid] = place_weights[place].get(uid, 0.0) + weight
            place_totals[place] += weight

    # Average rank movement over the last five read-to-read transitions.
    transition_start = max(0, len(reads) - 5)
    predicted_rank = {}
    for uid in sorted(last["rankof"]):
        movements = []
        for index in range(transition_start, len(reads) - 1):
            earlier = reads[index]["rankof"]
            later = reads[index + 1]["rankof"]
            if uid in earlier and uid in later:
                movements.append(later[uid] - earlier[uid])
        drift = sum(movements) / len(movements) if movements else 0.0
        predicted_rank[uid] = last["rankof"][uid] + drift * DRIFT_HORIZON

    persistence = persistence_forecast(last_chart)
    forecast_by_place = {}

    for place in range(1, PLACES + 1):
        raw = {}
        total = place_totals[place]
        if total > 0.0:
            for uid in sorted(place_weights[place]):
                raw[uid] = place_weights[place][uid] / total
        for uid in sorted(predicted_rank):
            offset = (predicted_rank[uid] - place) / KERNEL_SIGMA
            kernel = math.exp(-0.5 * offset * offset)
            raw[uid] = raw.get(uid, 0.0) + KERNEL_WEIGHT * kernel

        raw_total = sum(raw[uid] for uid in sorted(raw))
        if raw_total > 0.0:
            normalized = {uid: raw[uid] / raw_total for uid in sorted(raw)}
        else:
            normalized = {}

        ordered = sorted(normalized, key=lambda uid: (-normalized[uid], uid))
        selected = ordered[:NAMED_GAMES]
        selected_total = sum(normalized[uid] for uid in selected)
        if selected_total > 0.0:
            named = {
                uid: normalized[uid] * NAMED_MASS / selected_total
                for uid in selected
            }
        else:
            named = {}

        merged = {}
        for uid in sorted(named):
            merged[uid] = merged.get(uid, 0.0) + (1.0 - PERSISTENCE_BLEND) * named[uid]
        for uid in sorted(persistence[place]):
            merged[uid] = merged.get(uid, 0.0) + PERSISTENCE_BLEND * persistence[place][uid]
        forecast_by_place[place] = merged

    # Rank games by their named probability-weighted place, then stable ID.
    expected_rank = {}
    for place in range(1, PLACES + 1):
        for uid in sorted(forecast_by_place[place]):
            expected_rank[uid] = expected_rank.get(uid, 0.0) + place * forecast_by_place[place][uid]
    for uid in sorted(last["rankof"]):
        if uid not in expected_rank:
            expected_rank[uid] = float(PLACES + 5)
    top10 = sorted(expected_rank, key=lambda uid: (expected_rank[uid], uid))[:PLACES]
    if len(top10) < PLACES:
        for uid in last_chart:
            if uid not in top10:
                top10.append(uid)
                if len(top10) == PLACES:
                    break

    rows = []
    for place in range(1, PLACES + 1):
        for uid in sorted(forecast_by_place[place]):
            probability = forecast_by_place[place][uid]
            if probability > 0.0:
                rows.append(
                    {
                        "universe_id": uid,
                        "place": place,
                        "p": probability,
                    }
                )
    return {"probabilities": rows, "top10": top10}


def load_json_lines(path):
    records = []
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                records.append(json.loads(line))
    return records


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    history_path = os.path.join(input_dir, "history.ndjson")
    task_path = os.path.join(input_dir, "task.json")

    history = load_json_lines(history_path)
    places = PLACES
    if os.path.isfile(task_path):
        with open(task_path, "r", encoding="utf-8") as stream:
            task = json.load(stream)
        task_places = task.get("places", PLACES)
        if isinstance(task_places, int) and not isinstance(task_places, bool):
            places = min(PLACES, max(1, task_places))

    document = build_forecast(history)
    if places != PLACES:
        document["probabilities"] = [
            row for row in document["probabilities"] if row["place"] <= places
        ]
        document["top10"] = document["top10"][:places]
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "forecast.json")
    with open(output_path, "w", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        stream.write("")


if __name__ == "__main__":
    main()
