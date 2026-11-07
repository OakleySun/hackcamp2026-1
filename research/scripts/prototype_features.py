"""
FridgeSense post-processing prototype on public MOS data.

Purpose: sanity-check the candidate chain (Hampel k=2 -> median-5 -> causal
window features) on real MOS time series before building it in Databricks.
Everything here mirrors the Spark SQL definitions in
research/postprocessing-plan.md (ROWS BETWEEN n PRECEDING frames at 5 s).

Datasets (downloaded by download_data.sh into ./data):
  1. Mendeley n8mc3nspfn "e-nose beef quality (4 classes)", CC BY 4.0.
     ESP32 + 8 MQ sensors, 12-bit ADC counts, 5 s sampling, ~29 h.
     -> real slow "Spoiling" ramp at our exact cadence.
  2. UCI 362 "Gas sensors for home activity monitoring", CC BY 4.0.
     8 Figaro TGS sensors (resistance, kOhm), ~1 Hz, banana/wine inductions
     with ~1 h background before/after. Decimated to 5 s.
     -> "Strong but fine" (long induction) and "Disturbance" (short) shapes.

Run:  .venv/bin/python prototype_features.py
Outputs: out/*.png and out/summary.md
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

DT = 5.0  # seconds per sample, our firmware cadence
N1M = int(60 / DT)  # 12 samples per minute


# ----------------------------------------------------------------------------
# Chain primitives (causal, mirror the SQL window frames)
# ----------------------------------------------------------------------------
def hampel(x: pd.Series, k: int = 2, nsig: float = 3.0, mad_floor: float = 0.0):
    """Centered Hampel filter (window 2k+1). Returns (cleaned, flag).
    In SQL we use a centered ROWS BETWEEN k PRECEDING AND k FOLLOWING frame
    inside the bronze->silver job (fine because we recompute a 60-min lookback).
    mad_floor: integer ADC data in a 5-sample window often has MAD == 0, which
    makes the threshold 0 and flags everything; floor the robust sigma at the
    quantisation step (1 ADC count / baseline) or at sigma_d from clean air."""
    w = 2 * k + 1
    med = x.rolling(w, center=True, min_periods=1).median()
    mad = (x - med).abs().rolling(w, center=True, min_periods=1).median()
    thr = nsig * np.maximum(1.4826 * mad, mad_floor)
    flag = (x - med).abs() > thr
    y = x.where(~flag, med)
    return y, flag


def causal_slope(y: pd.Series, n: int) -> pd.Series:
    """OLS slope over the last n samples, per minute of ratio (regr_slope)."""
    t = np.arange(len(y)) * DT / 60.0  # minutes
    out = np.full(len(y), np.nan)
    yv = y.to_numpy()
    for i in range(n - 1, len(y)):
        ys = yv[i - n + 1 : i + 1]
        ts = t[i - n + 1 : i + 1]
        if np.isnan(ys).any():
            continue
        tc = ts - ts.mean()
        out[i] = (tc * (ys - ys.mean())).sum() / (tc**2).sum()
    return pd.Series(out, index=y.index)


def causal_r2(y: pd.Series, n: int) -> pd.Series:
    t = np.arange(len(y)) * DT / 60.0
    out = np.full(len(y), np.nan)
    yv = y.to_numpy()
    for i in range(n - 1, len(y)):
        ys = yv[i - n + 1 : i + 1]
        ts = t[i - n + 1 : i + 1]
        if np.isnan(ys).any() or ys.std() == 0:
            continue
        out[i] = np.corrcoef(ts, ys)[0, 1] ** 2
    return pd.Series(out, index=y.index)


def features(ratio: pd.Series, mad_floor: float = 0.0) -> pd.DataFrame:
    """Per-sample causal features as defined in the plan."""
    clean, flag = hampel(ratio, k=2, nsig=3.0, mad_floor=mad_floor)
    sm = clean.rolling(5, min_periods=1).median()  # median-5 (25 s)
    f = pd.DataFrame({"ratio": ratio, "hampel_flag": flag, "clean": clean, "sm": sm})
    f["slope_5m"] = causal_slope(sm, 5 * N1M)
    f["slope_15m"] = causal_slope(sm, 15 * N1M)
    f["r2_15m"] = causal_r2(sm, 15 * N1M)
    d = sm.diff()
    # sign balance in (-1, 1): mean of sign(diff) over 10 min. Strict ">0" fraction
    # fails on integer ADC data because most diffs are exactly 0 after smoothing.
    f["pos_diff_frac_10m"] = np.sign(d).rolling(10 * N1M, min_periods=N1M).mean()
    # concavity: slope of first half of last 10 min minus slope of second half
    first = causal_slope(sm.shift(5 * N1M), 5 * N1M)
    f["concavity_10m"] = first - f["slope_5m"]
    # step size: median[t-30s, t] - median[t-60s, t-30s]; persist as max over 10 min
    med_after = sm.rolling(6, min_periods=6).median()
    med_before = sm.shift(6).rolling(6, min_periods=6).median()
    f["step_now"] = med_after - med_before
    f["last_step_size"] = f["step_now"].rolling(10 * N1M, min_periods=1).max()
    return f


def robust_sigma(x: pd.Series) -> tuple[float, float]:
    """sigma_1 from MAD of level, sigma_d from MAD of first differences."""
    s1 = 1.4826 * (x - x.median()).abs().median()
    d = x.diff().dropna()
    sd = 1.4826 * (d - d.median()).abs().median() / np.sqrt(2)
    return float(s1), float(sd)


def window_2m(f: pd.DataFrame) -> pd.DataFrame:
    """2-minute tumbling windows: mean/max/std + last value of rolling features."""
    g = f.groupby(np.arange(len(f)) // (2 * N1M))
    w = g.agg(
        ratio_mean=("sm", "mean"),
        ratio_max=("sm", "max"),
        ratio_std=("sm", "std"),
        slope_5m=("slope_5m", "last"),
        slope_15m=("slope_15m", "last"),
        r2_15m=("r2_15m", "last"),
        pos_diff_frac_10m=("pos_diff_frac_10m", "last"),
        concavity_10m=("concavity_10m", "last"),
        last_step_size=("last_step_size", "last"),
    )
    return w


lines: list[str] = []


def log(s: str = ""):
    print(s)
    lines.append(s)


# ----------------------------------------------------------------------------
# 1. Beef spoilage ramp (Mendeley, 5 s)
# ----------------------------------------------------------------------------
log("# Prototype results\n")
log("## 1. Mendeley beef e-nose (n8mc3nspfn, CC BY 4.0), 5 s sampling\n")
beef = pd.read_csv(os.path.join(DATA, "beef_4classes.csv"))
beef.columns = [c.strip() for c in beef.columns]
mq_cols = [c for c in beef.columns if c.lower().startswith("mq")]
log(f"rows={len(beef)}  minutes={beef['minutes'].min()}..{beef['minutes'].max()}  cols={mq_cols}")
log(f"class counts: {beef['class'].value_counts().sort_index().to_dict()}")
log(f"ADC range per sensor: " + ", ".join(f"{c}:{beef[c].min()}-{beef[c].max()}" for c in mq_cols))

# monotonicity: Spearman rho vs time
rho = {c: beef[c].corr(beef["minutes"], method="spearman") for c in mq_cols}
log("Spearman rho vs time (monotonic rise => good replay channel): "
    + ", ".join(f"{c}:{v:+.2f}" for c, v in sorted(rho.items(), key=lambda kv: -kv[1])))
base30 = {c: beef[c].iloc[: 30 * N1M].median() for c in mq_cols}
log("first-30-min median ADC per sensor: " + ", ".join(f"{c}:{v:.0f}" for c, v in base30.items()))
clipped = [c for c, v in base30.items() if v < 100]
log(f"sensors clipped at/near the ADC floor in 'clean' air (baseline <100 counts, unusable for a ratio): {clipped}")
chan = max((c for c in mq_cols if base30[c] >= 100), key=rho.get)
log(f"-> most monotonic channel with a usable baseline: {chan}")

base = beef[chan].iloc[: 30 * N1M].median()  # first 30 min as baseline
ratio_b = beef[chan] / base
s1, sd = robust_sigma(beef[chan].iloc[: 30 * N1M] / base)
log(f"baseline(first 30 min median)={base:.0f} ADC; sigma_1(level)={s1:.4f}, sigma_d(diff)={sd:.4f} in ratio units "
    f"(= {s1*base:.1f} / {sd*base:.1f} ADC counts). NOTE: sigma_1 is inflated by warm-up drift; sigma_d is the usable noise estimate.")
q = 1.0 / base  # one ADC count in ratio units
fb0 = features(ratio_b)
fb = features(ratio_b, mad_floor=max(q, sd))
log(f"Hampel k=2 flag rate: {fb0['hampel_flag'].mean()*100:.2f}% without MAD floor -> {fb['hampel_flag'].mean()*100:.2f}% with floor max(1 count, sigma_d)={max(q, sd):.4f}")

# slope per class segment
beef["ratio"] = ratio_b
fb["class"] = beef["class"].to_numpy()
fb["minutes"] = beef["minutes"].to_numpy()
log("\nPer-class summary of real spoilage ramp (ratio units):")
log("| class | span (min) | ratio start->end | median slope_15m (ratio/min) | median r2_15m | median pos_diff_frac | median concavity |")
log("|---|---|---|---|---|---|---|")
for c, g in fb.groupby("class"):
    log(f"| {c} | {g['minutes'].min()}-{g['minutes'].max()} | {g['sm'].iloc[0]:.3f}->{g['sm'].iloc[-1]:.3f} | "
        f"{g['slope_15m'].median():+.5f} | {g['r2_15m'].median():.2f} | {g['pos_diff_frac_10m'].median():.2f} | {g['concavity_10m'].median():+.5f} |")

# the steepest 20-min slice (what a "pre-spoiled food" session should look like)
roll20 = ratio_b.rolling(20 * N1M).apply(lambda v: v[-1] - v[0], raw=True)
i_end = int(roll20.idxmax())
seg = fb.iloc[i_end - 20 * N1M : i_end]
log(f"\nSteepest 20-min slice: minutes {seg['minutes'].iloc[0]}-{seg['minutes'].iloc[-1]}, ratio {seg['sm'].iloc[0]:.3f}->{seg['sm'].iloc[-1]:.3f}, "
    f"slope_15m at end={seg['slope_15m'].iloc[-1]:+.5f}/min, r2={seg['r2_15m'].iloc[-1]:.2f}, pos_diff_frac={seg['pos_diff_frac_10m'].iloc[-1]:.2f}")
T_slope_guard = 3 * sd / 15  # total drift over 15 min must exceed 3 sigma_d
real_rate = fb[fb["class"] == 4]["slope_15m"].median()
log(f"REAL spoilage rate (class 4 median slope_15m) = {real_rate:+.5f} ratio/min = {real_rate*60:+.3f} ratio/hour; "
    f"over a 20-min session that is a {real_rate*20:.3f} ratio change = {real_rate*20/sd:.1f} sigma_d.")
log(f"T_slope guard (3*sigma_d over 15 min) = {T_slope_guard:.5f} ratio/min; "
    f"fraction of 'Spoiled'(class 4) samples with slope_15m > guard: "
    f"{(fb[fb['class']==4]['slope_15m'] > T_slope_guard).mean()*100:.0f}%; "
    f"of 'Excellent'(class 1): {(fb[fb['class']==1]['slope_15m'] > T_slope_guard).mean()*100:.0f}%")

# export a replay segment: 20 min real-rate slice rescaled to 0-4095 for the replay script
replay = pd.DataFrame({
    "t_s": np.arange(len(seg)) * DT,
    "ratio": seg["clean"].to_numpy(),
})
replay.to_csv(os.path.join(OUT, "replay_spoiling_20min_ratio.csv"), index=False)

fig, ax = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
ax[0].plot(fb["minutes"] / 60, fb["ratio"], lw=0.4, alpha=0.5, label="raw ratio")
ax[0].plot(fb["minutes"] / 60, fb["sm"], lw=0.8, label="hampel+median5")
for c in sorted(fb["class"].unique()):
    g = fb[fb["class"] == c]
    ax[0].axvspan(g["minutes"].min() / 60, g["minutes"].max() / 60, alpha=0.06, color=f"C{c}")
ax[0].set_ylabel(f"{chan} / baseline"); ax[0].legend(); ax[0].set_title("Beef spoilage, 29 h, 5 s (Mendeley n8mc3nspfn)")
ax[1].plot(fb["minutes"] / 60, fb["slope_15m"], lw=0.6, label="slope_15m (ratio/min)")
ax[1].plot(fb["minutes"] / 60, fb["slope_5m"], lw=0.4, alpha=0.6, label="slope_5m")
ax[1].axhline(T_slope_guard, color="r", ls="--", lw=0.7, label="T_slope guard"); ax[1].legend(); ax[1].set_ylabel("slope")
ax[2].plot(fb["minutes"] / 60, fb["r2_15m"], lw=0.5, label="r2_15m")
ax[2].plot(fb["minutes"] / 60, fb["pos_diff_frac_10m"], lw=0.5, label="pos_diff_frac_10m")
ax[2].legend(); ax[2].set_xlabel("hours"); ax[2].set_ylabel("0..1")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "beef_ramp.png"), dpi=110); plt.close(fig)

# ----------------------------------------------------------------------------
# 2. UCI 362 banana inductions (step / spike shapes), decimated to 5 s
# ----------------------------------------------------------------------------
log("\n## 2. UCI 362 home-activity (banana inductions), decimated to 5 s\n")
meta = pd.read_csv(os.path.join(DATA, "uci362", "HT_Sensor_metadata.dat"), sep=r"\s+")
meta.columns = ["id", "date", "class", "t0", "dt"]
ds = pd.read_csv(os.path.join(DATA, "uci362", "HT_Sensor_dataset.dat"), sep=r"\s+")
ds.columns = ["id", "time", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "Temp", "Humidity"]
log(f"rows={len(ds)}  recordings={ds['id'].nunique()}  classes={meta['class'].value_counts().to_dict()}")
ban = meta[meta["class"] == "banana"].sort_values("dt")
log(f"banana induction durations (h): min={ban['dt'].min():.2f} median={ban['dt'].median():.2f} max={ban['dt'].max():.2f}")
short_ids = ban.head(3)["id"].tolist()
long_ids = ban.tail(3)["id"].tolist()
bg_ids = meta[meta["class"] == "background"]["id"].tolist()[:5]
log(f"short banana ids={short_ids}  long banana ids={long_ids}  background ids used={bg_ids}")

def prep(rec_id: int, sensor: str):
    r = ds[ds["id"] == rec_id].copy()
    # decimate ~1 Hz -> 5 s by median-of-5 (mirrors our firmware burst median)
    r["bin"] = (r["time"] * 3600 // DT).astype(int)
    r = r.groupby("bin").agg(time=("time", "mean"), R=(sensor, "median"), RH=("Humidity", "mean")).reset_index(drop=True)
    pre = r[r["time"] < 0]
    r0 = pre["R"].median()
    r["ratio"] = r0 / r["R"]  # conductance ratio, rises with gas (like our divider voltage)
    return r


# pick the sensor that responds most to banana (dataset order: R1 TGS2611, R2 TGS2612,
# R3 TGS2610, R4 TGS2600, R5 TGS2602, R6 TGS2602, R7 TGS2620, R8 TGS2620)
resp = {}
for s in [f"R{i}" for i in range(1, 9)]:
    pk = []
    for rid in ban["id"]:
        r = prep(rid, s)
        m = meta[meta["id"] == rid].iloc[0]
        on = r[(r["time"] >= 0) & (r["time"] <= m["dt"])]
        pk.append(on["ratio"].max() - 1.0)
    resp[s] = float(np.median(pk))
log("median banana excursion (R0/R - 1) per sensor: " + ", ".join(f"{k}:{v:+.3f}" for k, v in resp.items()))
SENSOR = max(resp, key=resp.get)
log(f"-> using {SENSOR}")

# noise sigma on background recordings
sig = [robust_sigma(prep(i, SENSOR)["ratio"]) for i in bg_ids]
sd_bg = float(np.median([s[1] for s in sig]))
log(f"background recordings: sigma_1(level) median={np.median([s[0] for s in sig]):.4f}, sigma_d(diff) median={sd_bg:.4f} (ratio units, {SENSOR})")
flags0 = [features(prep(i, SENSOR)["ratio"])["hampel_flag"].mean() for i in bg_ids]
flags = [features(prep(i, SENSOR)["ratio"], mad_floor=sd_bg)["hampel_flag"].mean() for i in bg_ids]
log(f"Hampel k=2 flag rate on background: median {np.median(flags0)*100:.2f}% without floor -> {np.median(flags)*100:.2f}% with MAD floor = sigma_d")

log("\n| id | dt (min) | kind | ratio peak | step at onset (last_step_size max) | slope_5m max | slope_15m max | r2_15m at +10 min | concavity at +10 min | recovered to <20% of excursion after (min) |")
log("|---|---|---|---|---|---|---|---|---|---|")
fig, axes = plt.subplots(2, 3, figsize=(15, 7), sharey=False)
for ax, rid in zip(axes.flat, short_ids + long_ids):
    r = prep(rid, SENSOR)
    m = meta[meta["id"] == rid].iloc[0]
    f = features(r["ratio"], mad_floor=sd_bg)
    f["tmin"] = r["time"] * 60
    on = f[(f["tmin"] >= 0) & (f["tmin"] <= m["dt"] * 60)]
    peak = on["sm"].max()
    excursion = peak - 1.0
    after = f[f["tmin"] > m["dt"] * 60]
    rec = after[after["sm"] < 1.0 + 0.2 * excursion]
    rec_min = (rec["tmin"].iloc[0] - m["dt"] * 60) if len(rec) else np.nan
    at10 = f.iloc[(f["tmin"] - 10).abs().idxmin()]
    kind = "short (Disturbance-like)" if rid in short_ids else "long (Strong-but-fine-like)"
    log(f"| {rid} | {m['dt']*60:.0f} | {kind} | {peak:.3f} | {on['last_step_size'].max():+.3f} | {on['slope_5m'].max():+.4f} | {on['slope_15m'].max():+.4f} | "
        f"{at10['r2_15m']:.2f} | {at10['concavity_10m']:+.4f} | {rec_min:.1f} |")
    ax.plot(f["tmin"], f["ratio"], lw=0.4, alpha=0.5)
    ax.plot(f["tmin"], f["sm"], lw=0.9)
    ax.axvspan(0, m["dt"] * 60, color="orange", alpha=0.15)
    ax.set_title(f"id {rid} banana, dt={m['dt']*60:.0f} min"); ax.set_xlabel("min from induction"); ax.set_ylabel("R0/R")
    ax.set_xlim(-20, min(m["dt"] * 60 + 40, 150))
fig.tight_layout(); fig.savefig(os.path.join(OUT, "uci_banana_shapes.png"), dpi=110); plt.close(fig)

# humidity vs sensor on background (confound check)
hum = []
for i in bg_ids:
    r = prep(i, SENSOR)
    if r["RH"].std() > 0.5:
        hum.append(np.corrcoef(r["RH"], r["ratio"])[0, 1])
log(f"\nBackground RH vs {SENSOR} ratio correlation (where RH moved >0.5%): {np.round(hum, 2).tolist()}")

with open(os.path.join(OUT, "summary.md"), "w") as fh:
    fh.write("\n".join(lines) + "\n")
log(f"\nWrote {OUT}/summary.md, beef_ramp.png, uci_banana_shapes.png, replay_spoiling_20min_ratio.csv")
