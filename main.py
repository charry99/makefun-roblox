#!/usr/bin/env python3
"""Deterministic place-wise forecast for Roblox Up-and-Coming."""
import json
import math
import os
from datetime import datetime


PLACES_DEFAULT = 10
HALF_LIFE_HOURS = 24.0
KERNEL_WEIGHT = 0.6
KERNEL_SIGMA = 4.0
DRIFT_HORIZON = 2.0
PERSISTENCE_BLEND = 0.20
NAMED_GAMES = 12
NAMED_MASS = 0.45


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def ordered_rows(snapshot):
    rows = snapshot.get("up_and_coming") or snapshot.get("chart") or []
    valid = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        uid = row.get("universe_id")
        rank = row.get("rank")
        if isinstance(uid, int) and isinstance(rank, int) and uid > 0 and rank > 0:
            valid.append((rank, uid))
    valid.sort(key=lambda item: (item[0], item[1]))
    return valid


def read_history(input_dir):
    path = os.path.join(input_dir, "history.ndjson")
    snapshots = []
    with open(path, "r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            snapshot = json.loads(line)
            rows = ordered_rows(snapshot)
            if not rows:
                continue
            ranks = {uid: rank for rank, uid in rows}
            snapshots.append({
                "at": parse_time(snapshot.get("at")),
                "rows": rows,
                "ranks": ranks,
                "chart": [uid for _, uid in rows],
            })
    return snapshots


def persistence_distribution(last_chart, place):
    """Starter baseline, with missing neighbors omitted on short charts."""
    dist = {}
    if not last_chart:
        return dist
    if place == 1:
        dist[last_chart[0]] = 0.5
        if len(last_chart) > 1:
            dist[last_chart[1]] = 0.3
    elif place <= len(last_chart):
        dist[last_chart[place - 1]] = 0.5
        dist[last_chart[place - 2]] = 0.15
        if place < len(last_chart):
            dist[last_chart[place]] = 0.15
    return dist


def forecast(snapshots, places):
    if not snapshots:
        return {"probabilities": [], "top10": []}

    latest = snapshots[-1]
    last_chart = latest["chart"]
    place_count = max(0, min(int(places), 10))
    times = [snapshot["at"] for snapshot in snapshots]
    end_time = next((value for value in reversed(times) if value is not None), None)

    weighted_freq = {place: {} for place in range(1, place_count + 1)}
    frequency_totals = {place: 0.0 for place in range(1, place_count + 1)}
    for snapshot in snapshots:
        at = snapshot["at"]
        if end_time is not None and at is not None:
            age_hours = max(0.0, (end_time - at).total_seconds() / 3600.0)
        else:
            age_hours = float(len(snapshots) - 1 - snapshots.index(snapshot))
        weight = 0.5 ** (age_hours / HALF_LIFE_HOURS)
        for place in range(1, min(place_count, len(snapshot["chart"])) + 1):
            uid = snapshot["chart"][place - 1]
            bucket = weighted_freq[place]
            bucket[uid] = bucket.get(uid, 0.0) + weight
            frequency_totals[place] += weight

    predicted_rank = {}
    for uid, rank in sorted(latest["ranks"].items()):
        drifts = []
        start = max(0, len(snapshots) - 5)
        for index in range(start, len(snapshots) - 1):
            earlier = snapshots[index]["ranks"].get(uid)
            later = snapshots[index + 1]["ranks"].get(uid)
            if earlier is not None and later is not None:
                drifts.append(later - earlier)
        drift = sum(drifts) / len(drifts) if drifts else 0.0
        predicted_rank[uid] = rank + DRIFT_HORIZON * drift

    distributions = {}
    for place in range(1, place_count + 1):
        raw = {}
        total_frequency = frequency_totals[place]
        if total_frequency > 0.0:
            for uid in sorted(weighted_freq[place]):
                raw[uid] = weighted_freq[place][uid] / total_frequency

        for uid in sorted(predicted_rank):
            distance = (predicted_rank[uid] - place) / KERNEL_SIGMA
            kernel = math.exp(-0.5 * distance * distance)
            raw[uid] = raw.get(uid, 0.0) + KERNEL_WEIGHT * kernel

        raw_total = sum(raw.values())
        if raw_total > 0.0:
            normalized = {uid: value / raw_total for uid, value in raw.items()}
            ranked = sorted(normalized.items(), key=lambda item: (-item[1], item[0]))
            selected = ranked[:NAMED_GAMES]
            selected_total = sum(value for _, value in selected)
            model_dist = {
                uid: NAMED_MASS * value / selected_total
                for uid, value in selected
            } if selected_total > 0.0 else {}
        else:
            model_dist = {}

        baseline = persistence_distribution(last_chart, place)
        combined = {}
        for uid, probability in model_dist.items():
            combined[uid] = combined.get(uid, 0.0) + (1.0 - PERSISTENCE_BLEND) * probability
        for uid, probability in baseline.items():
            combined[uid] = combined.get(uid, 0.0) + PERSISTENCE_BLEND * probability
        distributions[place] = combined

    rows = []
    for place in range(1, place_count + 1):
        for uid, probability in sorted(distributions[place].items()):
            if probability > 0.0:
                rows.append({
                    "universe_id": uid,
                    "place": place,
                    "p": probability,
                })

    # Rank candidates by named expected place; unseen mass is represented by
    # a conservative outside-top-ten rank for games in the latest chart.
    expected_rank = {uid: 15.0 for uid in last_chart}
    for place in range(1, place_count + 1):
        for uid, probability in distributions[place].items():
            expected_rank[uid] = expected_rank.get(uid, 15.0) + place * probability

    all_ids = sorted({uid for snapshot in snapshots for uid in snapshot["chart"]})
    for uid in all_ids:
        expected_rank.setdefault(uid, 20.0)
    top10 = sorted(all_ids, key=lambda uid: (expected_rank[uid], uid))[:10]

    # The competition schema requires ten distinct ids, including for a
    # deliberately tiny synthetic history.
    next_id = 1
    while len(top10) < 10:
        while next_id in expected_rank:
            next_id += 1
        top10.append(next_id)
        expected_rank[next_id] = 100.0 + next_id

    return {"probabilities": rows, "top10": top10}


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    task_path = os.path.join(input_dir, "task.json")
    try:
        with open(task_path, "r", encoding="utf-8") as source:
            task = json.load(source)
    except FileNotFoundError:
        task = {}
    places = task.get("places", PLACES_DEFAULT)
    snapshots = read_history(input_dir)
    result = forecast(snapshots, places)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, task.get("output", "forecast.json"))
    with open(output_path, "w", encoding="utf-8", newline="\n") as target:
        json.dump(result, target, ensure_ascii=False, separators=(",", ":"))
        target.write("\n")


if __name__ == "__main__":
    main()
