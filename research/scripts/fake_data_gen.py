"""
FridgeSense fake-data generator: emits readings in the bronze format
{"device_id","ts","raw_adc"} for the four label shapes, plus a replay mode that
streams the real 20-min spoilage slice exported by prototype_features.py.

Shape parameters are in RATIO units (raw_adc / baseline_adc) so they transfer
when the real MP503 clean-air baseline is known. Noise defaults come from the
prototype on real MOS data (sigma_d ~ 1-2 ADC counts at 5 s on a 12-bit ADC);
re-measure on the MP503 and pass --sigma-counts.

Usage examples
  .venv/bin/python fake_data_gen.py --shape fresh --minutes 20 > fresh.jsonl
  .venv/bin/python fake_data_gen.py --shape disturbance --post http://localhost:8000/readings --realtime
  .venv/bin/python fake_data_gen.py --shape replay --replay-csv out/replay_spoiling_20min_ratio.csv
"""
from __future__ import annotations

import argparse, json, sys, time
from datetime import datetime, timedelta, timezone

import numpy as np

DT = 5.0


def shape_ratio(kind: str, minutes: float, rng: np.random.Generator, dist_sign: int = -1) -> np.ndarray:
    n = int(minutes * 60 / DT)
    t = np.arange(n) * DT / 60.0  # minutes
    r = np.ones(n)
    if kind == "fresh":
        pass
    elif kind == "disturbance":
        # lid opened at minute 5 for ~20 s: fast excursion, exponential recovery (tau ~ 2 min).
        # Sign is configurable: humid box + dry room air => likely a DIP (sensor follow-up Q2); VOC burst => spike.
        t0, amp, tau = 5.0, 0.15, 2.0
        r += dist_sign * amp * np.where(t >= t0, np.exp(-(t - t0) / tau), 0.0)
        t0 = 11.0
        r += dist_sign * amp * np.where(t >= t0, np.exp(-(t - t0) / tau), 0.0)
    elif kind == "strong":
        # garlic placed at minute 3: first-order approach to a plateau (concave), tau ~ 4 min
        t0, amp, tau = 3.0, 0.40, 4.0
        r += amp * np.where(t >= t0, 1 - np.exp(-(t - t0) / tau), 0.0)
    elif kind == "spoiling":
        # slow near-linear rise over the whole session (diffusion-limited release)
        r += 0.004 * t  # +0.08 over 20 min; real beef median was +0.0017/min, tune via --ramp
    else:
        raise ValueError(kind)
    return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--shape", choices=["fresh", "disturbance", "strong", "spoiling", "replay"], required=True)
    p.add_argument("--minutes", type=float, default=20)
    p.add_argument("--baseline", type=int, default=1400, help="clean-air ADC counts (measure on the MP503)")
    p.add_argument("--sigma-counts", type=float, default=2.0, help="per-sample noise, ADC counts")
    p.add_argument("--glitch-rate", type=float, default=0.005, help="fraction of 1-sample Wi-Fi/ADC glitches")
    p.add_argument("--dist-sign", type=int, default=-1, choices=[-1, 1])
    p.add_argument("--device", default="res-floor-3")
    p.add_argument("--replay-csv", default="out/replay_spoiling_20min_ratio.csv")
    p.add_argument("--post", default=None, help="relay URL; prints JSONL to stdout if omitted")
    p.add_argument("--api-key", default="dev-key")
    p.add_argument("--realtime", action="store_true", help="sleep 5 s between readings")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    rng = np.random.default_rng(a.seed)

    if a.shape == "replay":
        import csv
        with open(a.replay_csv) as fh:
            ratio = np.array([float(row["ratio"]) for row in csv.DictReader(fh)])
    else:
        ratio = shape_ratio(a.shape, a.minutes, rng, a.dist_sign)

    adc = ratio * a.baseline + rng.normal(0, a.sigma_counts, len(ratio))
    glitch = rng.random(len(adc)) < a.glitch_rate
    adc[glitch] += rng.choice([-1, 1], glitch.sum()) * rng.uniform(100, 800, glitch.sum())
    adc = np.clip(np.round(adc), 0, 4095).astype(int)

    t0 = datetime.now(timezone.utc)
    session = None
    if a.post:
        import requests
        session = requests.Session()
    for i, v in enumerate(adc):
        ts = t0 + timedelta(seconds=i * DT)
        rec = {"device_id": a.device, "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "raw_adc": int(v)}
        if session:
            session.post(a.post, json=rec, headers={"X-Device-Key": a.api_key}, timeout=10)
        else:
            sys.stdout.write(json.dumps(rec) + "\n")
        if a.realtime:
            time.sleep(DT)


if __name__ == "__main__":
    main()
