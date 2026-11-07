# 5a. Post-processing chain (drop-in for `fridgesense-plan.md` §5a)

Research synthesis, 2026-11-07. Five parallel research reports (sensor/ADC, public datasets, signal processing, prior projects, Databricks Free Edition) plus one follow-up round each, and a prototype run on two public MOS datasets (`research/scripts/prototype_features.py`, results in `research/scripts/out/summary.md`).

Legend used throughout: **EVIDENCE** = sourced; **PROTOTYPE** = measured by our script on public data; **OPINION** = our inference; **UNVERIFIED** = could not confirm, test listed. No parameter below is invented: every number is either sourced, measured, or marked as a starting point with the test that fixes it.

## 0. TL;DR: what changes vs the draft plan

**Cost constraint: $0.** Everything below runs on Databricks Free Edition with no paid features (no external cloud storage, no paid warehouse size, no Model Serving), uses only CC BY 4.0 / CC0 public data, and needs no hardware beyond the sensor and ESP32 we already have. Any part listed as optional (capacitor, resistors, humidity sensor, spare sensor) is to be taken from the hackathon hardware table for free or skipped; nothing is to be bought.

1. **Zerobus is almost certainly unusable on Free Edition** (needs an external managed location + service-principal OAuth that Free Edition lacks; community reports of `401` and error `4024 Unsupported table kind`). Make the SQL Statement Execution API the primary path, not the fallback. EVIDENCE: https://learn.microsoft.com/en-us/azure/databricks/ingestion/zerobus-limits ("writing to default storage is not supported"); the `401` report is Databricks Community thread 161228 (exact URL UNVERIFIED, search the community for "Zerobus Free Edition"). Keep the 30-min Zerobus timebox from §4 only if someone is curious.
2. **`slope_30m` is replaced by `slope_5m` + `slope_15m` (+ `r2_15m`, `concavity_10m`)**, sized to 15–20 min sessions. The real spoilage rate in the only public 5-s MOS spoilage dataset is ~+0.10 ratio/hour (PROTOTYPE), i.e. ~2.6 noise sigmas over 20 min. A 20-minute "slow steady rise" is at the edge of detectability; the recording protocol (§5) is changed so Spoiling sessions produce a measurable rise.
3. **Minimal cleaning chain**: ESP32 burst **median** (not mean) → fixed clean-air baseline ratio → **Hampel k=2, 3σ with a MAD floor** → **5-sample median** → causal window features in pure Spark SQL. No EMA, no Savitzky–Golay, no auto-baseline, no CUSUM in the MVP.
4. **Disturbance (lid open) will probably be a DIP, not a spike.** Humid box air replaced by drier room air raises Rs and lowers the output voltage (EVIDENCE for MOS humidity response; direction for our module UNVERIFIED). All excursion features are two-sided (`abs`).
5. **Rule-based classifier first**, thresholds in units of the clean-air noise sigma measured on our own sensor, ML model second via MLflow with leave-one-session-out CV.
6. **Demo**: run the prediction loop as an interactive notebook `while True` loop during judging (serverless job start can take minutes), with the scheduled job as the "production" story.

## 1. The chain, as ordered steps

| # | Step | Runs where | MVP / stretch | Build time |
|---|---|---|---|---|
| S0 | Burst median on ESP32 | ESP32 firmware | MVP | 10 min |
| S1 | Dedupe + 60-min lookback read | bronze→silver job | MVP | 15 min |
| S2 | Baseline ratio | bronze→silver job | MVP | 20 min (incl. `baselines` table) |
| S3 | Warm-up / no-baseline gate | prediction job | MVP | 10 min |
| S4 | Hampel (k=2, 3σ, MAD floor) + median-5 | bronze→silver job (SQL) | MVP | 30 min |
| S5 | Window features (2-min) | bronze→silver job (SQL) | MVP | 60 min |
| S6 | Rule classifier with hysteresis | prediction job | MVP | 45 min |
| S7 | ML model (LR + shallow tree/RF), MLflow | training notebook + prediction job | MVP (after recordings) | 90 min |
| S8 | Alert on transition + cooldown | prediction job | MVP | 20 min |
| S9 | Long-horizon trend (hours) for real fridges | prediction job | Stretch | 30 min |
| S10 | CUSUM event timestamps, Theil–Sen slope | pandas UDF | Stretch | 60 min |
| S11 | Humidity co-logging (DHT11/22) | ESP32 | Stretch, only if a DHT is free at the hardware table | 30 min |

### S0. Burst median on the ESP32 (keep the JSON schema)
- **What**: every 5 s take 10–16 `analogRead()` samples spread over ~50–100 ms and send the **median** (or the trimmed mean of the middle 6–8) in the existing `raw_adc` field. Schema stays `{"device_id","ts","raw_adc"}`.
- **Why / which failure it fixes**: Wi-Fi TX bursts cause step-like outliers of up to ~1000 counts on ADC1; Espressif's own guidance is outlier rejection, not averaging. EVIDENCE: https://github.com/espressif/esp-idf/issues/8266, https://github.com/espressif/developer-portal/discussions/544, https://docs.espressif.com/projects/esp-faq/en/latest/software-framework/peripherals/adc.html. A mean of 10 lets one 800-count glitch move the reading by 80 counts, which is several noise sigmas (PROTOTYPE: per-sample noise on a comparable 12-bit MOS channel is ~2 counts).
- **Parameters**: GPIO 34/35/36/39 (input-only ADC1 pins), 11 dB attenuation (150–3100 mV usable range, EVIDENCE: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html), 100 nF capacitor on the signal pin only if one is free at the hardware table (Espressif recommendation, same FAQ); the burst median does the same job in software, so do not buy one.
- **ADC floor check (important)**: at 11 dB the ESP32 cannot read below ~150 mV. In the public beef dataset three of eight MQ channels sat at **0 ADC in clean air** and were useless for a ratio (PROTOTYPE). Test on day one: if the MP503 clean-air baseline at 3.3 V is below ~250 counts, switch to 6 dB attenuation (150–1750 mV), which is a one-line firmware change and costs nothing. Only if that is still not enough, power the sensor at 5 V through a 2:1 divider made from two equal resistors from the hardware table. OPINION on the thresholds; the mechanism is EVIDENCE.
- **Power**: stay at 3.3 V as planned. Seeed's own ESP32 tutorial says "connect the sensor's VCC to 3.3V" (EVIDENCE: https://wiki.seeedstudio.com/Grove-Air_Quality_Sensor_v1.3/). The MP503 heater is specified at 5.0 V ±0.1 V (EVIDENCE: https://www.winsen-sensor.com/d/files/manual/mp503.pdf), so 3.3 V means a cooler element and lower sensitivity; we only classify shape, so amplitude loss is acceptable. If powered at 5 V the output can exceed 3.3 V and damage the ADC (module has no documented regulator; UNVERIFIED from the schematic text). Deciding test: at 3.3 V after 30 min warm-up, wave an alcohol wipe near the vent; if the response is under ~5% of full scale, move to 5 V + divider.
- Optional: also send `analogReadMilliVolts()` as `mv` (eFuse-calibrated; chip Vref varies 1000–1200 mV, EVIDENCE: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/adc/adc_calibration.html). Not needed for a single device; skip unless we have two boards.

### S1. Dedupe and lookback read
- **What**: each job run reads `bronze_readings` for `ts >= now() - 60 min`, dedupes on `(device_id, ts)` keeping the latest `ingest_ts`, and recomputes all windows in that span, then `MERGE`s into `silver_features` on `(device_id, window_end)`.
- **Fixes**: late/out-of-order readings from the ESP32 reconnect buffer and relay retries. No streaming watermarks needed. EVIDENCE for the pattern: Delta MERGE docs https://docs.databricks.com/aws/en/delta/merge. OPINION: 720 rows/device/hour is trivial for a 2X-Small warehouse.

### S2. Baseline ratio
- **What**: `ratio = raw_adc / baseline_adc` using the latest row in `baselines` for the device. Details in §3.
- **Fixes**: multiplicative drift and board-to-board/temperature offsets. EVIDENCE: relative (`Rs/R0`) and fractional baseline manipulation compensate multiplicative drift and temperature in MOS e-noses: Gutiérrez-Osuna 2002 https://psi.engr.tamu.edu/wp-content/uploads/2018/01/gutierrezosuna2002sj.pdf; MDPI feature-extraction review https://www.mdpi.com/1424-8220/15/11/27804; Figaro: "sensitivity in air shows temperature dependency, but sensitivity in gas is relatively unaffected" https://www.unitronic.de/wp-content/uploads/2026/09/12779_DB_TGS2600.pdf.

### S3. Warm-up / no-baseline gate
- **What**: the prediction job writes `status = 'warming_up'` when there is no baseline for the device, or when the baseline is younger than `WARMUP_MIN` minutes after first reading, or when `abs(slope_15m)` on the latest window exceeds the ramp threshold *and* `ratio_mean` is within the clean-air band (i.e. the signal is still settling).
- **Fixes**: false "Spoiling" on power-up drift. EVIDENCE: MOS output at power-on is low until the heater reaches temperature, producing startup false alarms https://www.onetransistor.eu/2023/01/mq-sensors-temperature-humidity.html. PROTOTYPE: in the beef dataset the MQ-136 channel drifted from ratio 1.97 to 0.5 over the first ~2 h of a run (sensor not burned in).
- **Parameters**: `WARMUP_MIN` = 30 (starting point). Seeed says ~2 min heat-up for qualitative use; datasheets say ≥48 h for spec-grade stability; makers report 3–5 min per power-on *after* a 48-h burn-in (EVIDENCE: https://jenslabs.wordpress.com/2013/03/18/measured-sensor-characteristics-mq-3-and-tgs822/). Test: plot the first hour of our sensor; the warm-up ends when `slope_15m` stays within the Fresh band for 10 min. **Power the sensor overnight before demo day** if at all possible.

### S4. Denoising: Hampel then 5-sample median
- **What** (per device, on `ratio`, in SQL): flag a sample if `abs(ratio - med5) > 3 * GREATEST(1.4826 * mad5, sigma_floor)` where `med5`/`mad5` are the median and MAD over a centered 5-sample window (k=2); replace flagged samples with `med5`. Then take a 5-sample trailing median. Centered frames are fine because the job recomputes a 60-min lookback.
- **Why Hampel, why k=2**: median/Hampel preserve step edges exactly; moving average and Savitzky–Golay smear them, and our labels *are* edges and plateaus. EVIDENCE: https://www.mathworks.com/help/signal/ug/signal-smoothing.html, https://www.mathworks.com/help/signal/ref/hampel.html. With k=2 only 1–2-sample glitches are removed; any excursion longer than ~4 samples (20 s) survives intact. MOS onset is seconds to tens of seconds and recovery minutes (EVIDENCE: jenslabs link above; Winsen ZP01-MP503 module spec response ≤20 s, recovery ≤60 s https://www.winsen-sensor.com/d/files/zp01-mp503-4-grades-air-quality-module-v1_5-terminal-type.pdf), so a real lid event is never shorter than that.
- **MAD floor (PROTOTYPE, important)**: on integer ADC data a 5-sample MAD is often exactly 0, which makes the threshold 0 and flags ~10–13% of clean samples. Flooring the robust sigma at `max(1/baseline_adc, sigma_d)` dropped the clean-air flag rate to 2.3% (beef, 5 s) and 0.05% (UCI background, decimated to 5 s). `sigma_d` is defined in §4.
- **Test**: on a recording with 10 min clean air + 5 lid events, require <1% flags in clean air and 0% inside events. If events get clipped, raise nsigma to 4 before changing k.
- Build time 30 min. Pure SQL (`median()` works as a window function; EVIDENCE: https://docs.databricks.com/aws/en/sql/language-manual/functions/median).

### S5. Window features
Defined in §2. Pure SQL, 60 min to write and test on fake data.

### S6. Rule classifier with hysteresis
Defined in §4. Replaces the draft's "ratio > 1.5 = red" dummy rule and remains the fallback if the model underperforms.

### S7. ML model
Logistic regression (L2, standardized features) and a shallow decision tree / small random forest, leave-one-session-out CV, both logged to MLflow, best registered as `workspace.fridgesense.spoilage_model` with alias `@champion`. See §4.

### S8. Alerts on transition with cooldown
Insert into `alerts` only when the new status is red and the previous `gold_fridge_status` row was not red, and no red alert in the last 30 min (starting point). Run the alert insert **before** the gold MERGE so the previous status is still readable. SQL in §2.4.

### S9 (stretch). Long-horizon trend for real fridges
Real spoilage moves ~0.1 ratio/hour (PROTOTYPE on beef) and in a cold, larger fridge will be slower. Add `slope_6h` computed from per-10-minute medians in the prediction job (`regr_slope` over 36 points). Not needed for the demo; it is the honest answer to "how would this work in a real fridge". Also note the real curve is a staircase of jumps and plateaus rather than a smooth ramp (PROTOTYPE, see `out/beef_ramp.png`): the jumps in that dataset coincide with the authors opening the chamber to sample the meat, which is literally our Disturbance class inside a Spoiling trend.

### S10 (stretch). CUSUM event timestamps, Theil–Sen slope
CUSUM with k=0.5σ, h=4–5σ, reset after each alarm (EVIDENCE: NIST handbook https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc3131.htm; false-alarm caveat https://tatopenn-cell.github.io/Dense-Evolution-Discovery/river_drift_detector_contribution/). Theil–Sen for slopes has a 29% breakdown point vs 0% for OLS (EVIDENCE: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html). Both need a pandas UDF (`applyInPandas`); the SQL chain on Hampel-cleaned data gets most of the benefit for free.

### S11 (stretch, free parts only). Humidity co-logging
Humidity is the most-cited confounder for MOS food sensing (EVIDENCE: https://pmc.ncbi.nlm.nih.gov/articles/PMC9101743/, Figaro table cited above, ACS OFET fridge study that ran a 3-day water blank https://pubs.acs.org/acsodf/article-pdf/8/5/4649/4087634/ao2c06386.pdf). **Do this only if a DHT11/DHT22 (or any T/RH breakout) is available for free from the hackathon hardware table; do not buy one.** It would add `rh` and `temp_c` to the JSON; we would not use it in the model tonight but it pre-empts the judges' question and is required for any real-fridge follow-up. Without it, the zero-cost substitute is the "cup of water" Fresh session in §5.3, which measures the humidity-only response with no extra hardware.

## 2. Feature definitions (`silver_features`)

### 2.1 Resolving `slope_30m`
Sessions are 15–20 min, so a 30-min window never fills inside a session and would be computed on a moving mix of sessions. PROTOTYPE on the beef dataset: median `slope_15m` during the Spoiled phase is +0.0017 ratio/min (+0.10/hour); over 20 min that is +0.034 ratio ≈ 2.6 `sigma_d`. A 15-min OLS slope separated Spoiled from Excellent samples only weakly (41% vs 21% above a 3σ guard). Conclusion: **within a 20-min session, a real-rate spoilage ramp is barely detectable with one sensor**. We therefore (a) replace `slope_30m` with `slope_5m` and `slope_15m` so the windows fit, (b) make Spoiling sessions produce a stronger, controlled rise (§5.3), and (c) keep a long-horizon slope as the production feature (S9). OPINION, grounded in PROTOTYPE.

### 2.2 Final columns

| Column | Definition (per device, per 2-min tumbling window, on the cleaned ratio `sm`) | Separates |
|---|---|---|
| `window_end` | `window(ts,'2 minutes').end` | — |
| `n_samples` | count of readings in the window (expect 24; <12 → feature row flagged `low_coverage`) | data quality |
| `baseline_adc`, `baseline_set_at` | baseline used for the ratio | traceability |
| `ratio_mean` | `avg(sm)` | Fresh vs everything elevated |
| `ratio_max` | `max(sm)` | spike detection |
| `ratio_min` | `min(sm)` | **dip** detection (lid open likely dips) |
| `ratio_var` | `var_samp(sm)` (kept from the draft; `stddev` is sqrt of it) | spike/step inside the window vs plateau |
| `slope_5m` | `regr_slope(sm, unix_min)` over the last 60 samples | recent trend |
| `slope_15m` | `regr_slope(sm, unix_min)` over the last 180 samples, NULL if `<60` samples | sustained trend (Spoiling) |
| `r2_15m` | `regr_r2(sm, unix_min)` over the same frame | steady ramp vs noise/plateau |
| `concavity_10m` | slope over samples [t−10 min, t−5 min] minus slope over [t−5 min, t] | step approaching a plateau (>0) vs linear ramp (≈0) |
| `last_step_size` | `max` over the last 10 min of (`median(sm)` over [t−30 s, t] − `median(sm)` over [t−60 s, t−30 s]); also the signed min for dips | Strong-but-fine step vs Disturbance dip |
| `mins_since_spike` | minutes since the last sample with `abs(sm − 1) > T_spike`; NULL if none in the lookback | Disturbance vs Fresh; door just opened vs real change |
| `recovered` | latest `sm` within `1 ± 2·sigma_1` of the pre-event level (median of the 60 s before the spike) | Disturbance (recovers) vs Strong-but-fine (does not) |

Dropped: a "fraction of positive first differences" feature. PROTOTYPE: on 12-bit quantized, median-smoothed data most first differences are exactly zero, so the feature sits near 0 in every class. `r2_15m` and `concavity_10m` carry the same intent and worked on the public data.

### 2.3 SQL sketch (bronze → silver)

```sql
-- Verified on docs: window(), median() as window fn, regr_slope/regr_r2, RANGE BETWEEN INTERVAL.
-- UNVERIFIED on the Free Edition warehouse itself: test this cell first. Numeric fallback:
--   ORDER BY unix_s RANGE BETWEEN 600 PRECEDING AND CURRENT ROW
WITH latest_baseline AS (
  SELECT device_id, max_by(baseline_adc, set_at) AS baseline_adc, max(set_at) AS baseline_set_at
  FROM workspace.fridgesense.baselines GROUP BY device_id
),
raw AS (
  SELECT r.device_id, r.ts, r.raw_adc, r.ingest_ts
  FROM workspace.fridgesense.bronze_readings r
  WHERE r.ts >= current_timestamp() - INTERVAL 60 MINUTES
  QUALIFY row_number() OVER (PARTITION BY r.device_id, r.ts ORDER BY r.ingest_ts DESC) = 1
),
rated AS (
  SELECT r.*, b.baseline_adc, b.baseline_set_at,
         r.raw_adc / b.baseline_adc AS ratio,
         unix_timestamp(r.ts) / 60.0 AS unix_min
  FROM raw r JOIN latest_baseline b USING (device_id)
),
h1 AS (  -- Hampel k=2: centered 5-sample median and MAD
  SELECT *, median(ratio) OVER w5 AS med5 FROM rated
  WINDOW w5 AS (PARTITION BY device_id ORDER BY ts ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING)
),
h2 AS (
  SELECT *, median(abs(ratio - med5)) OVER w5 AS mad5 FROM h1
  WINDOW w5 AS (PARTITION BY device_id ORDER BY ts ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING)
),
clean AS (
  SELECT *, CASE WHEN abs(ratio - med5) > 3 * GREATEST(1.4826 * mad5, :sigma_floor)
                 THEN med5 ELSE ratio END AS ratio_h
  FROM h2
),
smooth AS (
  SELECT *, median(ratio_h) OVER (PARTITION BY device_id ORDER BY ts ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS sm
  FROM clean
),
per_sample AS (
  SELECT *,
    regr_slope(sm, unix_min) OVER w5m  AS slope_5m,
    CASE WHEN count(*) OVER w15m >= 60 THEN regr_slope(sm, unix_min) OVER w15m END AS slope_15m,
    regr_r2(sm, unix_min)    OVER w15m AS r2_15m,
    regr_slope(sm, unix_min) OVER wfirst - regr_slope(sm, unix_min) OVER w5m AS concavity_10m,
    median(sm) OVER wa - median(sm) OVER wb AS step_now,
    max(CASE WHEN abs(sm - 1) > :t_spike THEN ts END) OVER wall AS last_spike_ts
  FROM smooth
  WINDOW
    w5m    AS (PARTITION BY device_id ORDER BY ts ROWS BETWEEN 59  PRECEDING AND CURRENT ROW),
    w15m   AS (PARTITION BY device_id ORDER BY ts ROWS BETWEEN 179 PRECEDING AND CURRENT ROW),
    wfirst AS (PARTITION BY device_id ORDER BY ts ROWS BETWEEN 119 PRECEDING AND 60 PRECEDING),
    wa     AS (PARTITION BY device_id ORDER BY ts ROWS BETWEEN 5  PRECEDING AND CURRENT ROW),
    wb     AS (PARTITION BY device_id ORDER BY ts ROWS BETWEEN 11 PRECEDING AND 6 PRECEDING),
    wall   AS (PARTITION BY device_id ORDER BY ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
features AS (
  SELECT device_id,
         window(ts, '2 minutes').end            AS window_end,
         count(*)                               AS n_samples,
         max(baseline_adc)                      AS baseline_adc,
         max(baseline_set_at)                   AS baseline_set_at,
         avg(sm) AS ratio_mean, max(sm) AS ratio_max, min(sm) AS ratio_min, var_samp(sm) AS ratio_var,
         max_by(slope_5m, ts) AS slope_5m, max_by(slope_15m, ts) AS slope_15m,
         max_by(r2_15m, ts) AS r2_15m, max_by(concavity_10m, ts) AS concavity_10m,
         max(step_now) AS last_step_size, min(step_now) AS last_dip_size,
         (unix_timestamp(max(ts)) - unix_timestamp(max(last_spike_ts))) / 60.0 AS mins_since_spike
  FROM per_sample
  GROUP BY device_id, window(ts, '2 minutes')
)
MERGE INTO workspace.fridgesense.silver_features t
USING features s ON t.device_id = s.device_id AND t.window_end = s.window_end
WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *;
```

Notes: `last_step_size` here is the max over the 2-min window; the "max over last 10 min" variant from §2.2 is `max(step_now) OVER (ROWS BETWEEN 119 PRECEDING AND CURRENT ROW)` in `per_sample`. `recovered` is simplest in the prediction job in pandas (compare the latest `sm` with the pre-spike median); doing it in pure SQL needs `last_value(... IGNORE NULLS)` carry-forward, which is supported on Spark 3.2+ (UNVERIFIED on the warehouse). `regr_*` and `median` window support: EVIDENCE https://docs.databricks.com/aws/en/sql/language-manual/functions/regr_slope, https://docs.databricks.com/aws/en/sql/language-manual/functions/regr_r2, https://docs.databricks.com/aws/en/sql/language-manual/functions/median. Aggregate window functions may not use `FILTER`, hence the `CASE WHEN` form (EVIDENCE: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-window-functions).

### 2.4 Alert SQL (run before the gold MERGE)

```sql
INSERT INTO workspace.fridgesense.alerts
SELECT s.device_id, 'red', current_timestamp()
FROM new_scores s
LEFT JOIN workspace.fridgesense.gold_fridge_status g ON g.device_id = s.device_id
LEFT JOIN (SELECT device_id, max(alert_ts) AS last_red FROM workspace.fridgesense.alerts
           WHERE status = 'red' GROUP BY device_id) a ON a.device_id = s.device_id
WHERE s.status = 'red' AND coalesce(g.status, '') <> 'red'
  AND (a.last_red IS NULL OR a.last_red < current_timestamp() - INTERVAL 30 MINUTES);
```

## 3. Baseline strategy

**Set**: `baseline_adc` = median of `raw_adc` over the 5 min of clean air that end at `set_at`, only after the warm-up gate (S3) is satisfied. Store as an **append-only row** in `baselines(device_id, baseline_adc, set_at)` with an added `reason` column (`'warmup'`, `'session_start'`, `'cleanout'`, `'manual'`); consumers take `max_by(baseline_adc, set_at)`. History is free and demo-able with `DESCRIBE HISTORY workspace.fridgesense.baselines` and `VERSION AS OF`.

**Reset without a website** (pick one, 10 min each):
1. A parameterised SQL cell / notebook widget: `INSERT INTO baselines SELECT :device, median(raw_adc), current_timestamp(), 'cleanout' FROM bronze_readings WHERE device_id = :device AND ts > current_timestamp() - INTERVAL 5 MINUTES`. Judges can watch it run.
2. `POST /baseline` on the FastAPI relay (device API key) issuing the same statement via the SQL Statement API. Same code path as readings, so no new credentials.
3. An n8n webhook that calls the SQL Statement API (nice for the n8n prize: "RA replies DONE to the cleanout email → baseline reset").
We recommend 2 for the pipeline and 1 for the demo stage.

**Between container sessions**: open the lid, air the container 5–10 min (fan or wave it), check that `ratio_mean` of the last 2-min window is within `1 ± 3·sigma_1`. If yes, start the next session with the same baseline. If not (VOC carry-over or drift), insert a `'session_start'` baseline from the last 3 clean minutes before writing the `label_sessions` row. This mirrors the "purge → baseline → insert sample → record" protocol used in e-nose chambers (EVIDENCE: https://github.com/hevrosy/neuromorphic-enose-fpga; purge/reference states in https://github.com/iAnmolAgarwal/smart-e-nose).

**Drift and warm-up**: the baseline is fixed, never auto-adapted. Auto-baselines (Seeed `slope()` running average, SGP30/CCS811 "best value in the last 24 h") redefine slowly polluted air as clean and hide exactly the slow rise we want (EVIDENCE: https://github.com/Seeed-Studio/Grove_Air_quality_Sensor/blob/master/Air_Quality_Sensor.cpp, https://learn.adafruit.com/adafruit-sgp30-gas-tvoc-eco2-mox-sensor/arduino-code.md). Residual drift between cleanouts is tolerated: it is slow (days) compared to the features' windows, and in production `slope_6h` (S9) plus a cleanout reset every few weeks handles it. A very slow adaptive blend (e.g. 10%/day) is a production option, not for tonight.

**Cold fridge transfer**: clean-air Rs rises as temperature falls (EVIDENCE: Figaro TGS2600 table, Rs/Ro ≈1.0 at 20 °C/65% RH vs ~1.2–1.4 at lower temperature), so a fridge baseline will sit at a different absolute level than the room-temperature container. Because every feature is in ratio or ratio-per-minute units and thresholds are in units of in-situ noise sigma, the chain transfers; the baseline simply has to be taken **in the fridge** after warm-up. Compressor-cycle humidity wobble is an unmeasured risk (nothing public found); the 15-min windows and the recovery test should treat it as slow noise, but this is UNVERIFIED and should be said plainly if asked.

## 4. Classification approach

### 4.1 Noise calibration from one clean-air recording
From the first 10 clean minutes after warm-up, compute on the cleaned ratio:
- `sigma_d` = `1.4826 · MAD(sm[i] − sm[i−1]) / √2` (drift-robust per-sample noise). PROTOTYPE values for scale: 0.013 ratio (2.1 counts on a 161-count baseline) for the beef MQ-136 channel; on a higher baseline the ratio sigma will be smaller.
- `sigma_1` = `1.4826 · MAD(sm)`; inflated by any residual drift, use the smaller of the two for thresholds.

### 4.2 Starting thresholds (heuristics, not citations; tune with the tests listed)
| Threshold | Starting value | Rationale | Fix-it test |
|---|---|---|---|
| `T_spike` | `5·sigma_1` on `abs(sm − 1)` | the expected max of 24 noise samples is ≈2.5σ; 5σ leaves margin, consistent with CUSUM h=4–5σ practice | lid-open recording: every event must exceed it; clean air never |
| `T_step` | `2.5·sigma_1` on `last_step_size` | two 6-sample medians differ by ≈0.58σ under noise; 4× that | garlic recording: step must exceed it within 1 min of placing |
| `T_ramp` | `slope_15m · 15 > 3·sigma_1` (total rise over the window beats noise) and `r2_15m > 0.7` | OLS slope SE ≈ σ/58 per min for 180 points over 15 min | Spoiling session must satisfy it in ≥60% of windows after minute 5; Fresh never |
| `T_recover` | within `1 ± 2·sigma_1` of pre-event level inside 5 min | MOS recovery after small exposures is tens of seconds to a few minutes; after large exposures 10–30 min (EVIDENCE: jenslabs) | measure recovery time of 5 lid events; set `T_recover` to the 90th percentile |
| `T_strong` | `ratio_mean > 1 + T_step` sustained 5 min with `concavity_10m > 0` | step approaching a plateau | garlic session plateau level |

### 4.3 Decision list (prediction job, applied to the latest window with hysteresis)
```
if no baseline or warming up                                   -> warming_up (grey)
elif abs excursion < T_spike and abs(slope_15m) small          -> Fresh (green)
elif mins_since_spike <= 5 and recovered                        -> Disturbance (green, "door opened")
elif mins_since_spike <= 5 and not recovered                    -> Pending (keep previous colour; decide next window)
elif last_step_size > T_step and concavity_10m > 0 and plateau  -> Strong but fine (green, "strong food")
elif slope_15m ramp test passes (T_ramp)                        -> Spoiling (red if sustained 2 windows, else amber "Watch")
elif ratio_mean elevated and no recovery for > 15 min           -> Watch (amber)
else                                                            -> previous status
```
Hysteresis: a status only flips after two consecutive windows agree; red requires two consecutive Spoiling windows. This is the standard threshold-with-hysteresis gate and the single most robust online detector for a demo (OPINION, supported by the CUSUM false-alarm caveat above).

### 4.4 How the chain makes the four labels separable
- **Fresh vs the rest**: `ratio_max`/`ratio_min` within `1 ± T_spike` and no trend. The baseline ratio and the sigma-scaled thresholds make this independent of absolute level, temperature and board.
- **Disturbance vs Strong but fine**: both start with an edge, but Disturbance **recovers** (`recovered` true within 5 min, `mins_since_spike` small) and is likely **negative** (dip) in a humid box, while Strong-but-fine **holds a plateau** (`concavity_10m > 0`, `ratio_var` small after the step, no recovery). PROTOTYPE on UCI banana inductions: long inductions show a concave step to a plateau over 20–30 min (id 57: 1.0 → 1.38) and short ones recover; one short induction showed a large *negative* excursion when the room was aired (id 48, R0/R fell to 0.4), which is the lid-open signature we expect.
- **Strong but fine vs Spoiling**: this is the hard pair with one sensor and 20-min sessions. Shape helps only if the Spoiling session really rises steadily (`r2_15m` high, `concavity_10m ≈ 0`, `slope_15m` positive) while the garlic plateaus. If both plateau, the separation falls back to **level and persistence** (`ratio_mean`, no recovery over 15 min) which is weaker and food-dependent. §5.3 changes the protocol so the Spoiling recording has a real ramp; be honest in the pitch that production uses hours-long slopes (S9).
- **Where ML plugs in**: the model consumes the same `silver_features` row (plus `label_sessions` join). Logistic regression (C≈0.5, standardized) and a depth-2–3 tree, evaluated with `LeaveOneGroupOut` by session so adjacent windows of the same session never straddle train/test (EVIDENCE: https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data). With ~8 sessions ≈ 60–80 windows, report sessions-per-class, pooled confusion matrix and feature importances in MLflow. If the rules beat the model under LOSO, keep the rules as `@champion` and show the comparison: the Databricks story (features → MLflow → scheduled scoring → alias-based deploy) is intact either way.

## 5. Data plan

### 5.1 Public datasets and their use
| Dataset | Licence (verified) | What it is | Use |
|---|---|---|---|
| Mendeley n8mc3nspfn, beef e-nose 4 classes https://data.mendeley.com/datasets/n8mc3nspfn | **CC BY 4.0** (verified via the Mendeley API on 2026-11-07) | ESP32 + 8 MQ sensors, 12-bit ADC counts, **5 s**, 20,815 rows, 29 h, sealed chamber, TVC + 4 labels, DHT11 T/RH | replay curve for the demo (real-rate 20-min slice exported to `research/scripts/out/replay_spoiling_20min_ratio.csv`), noise sigma scale, backlog "hours until spoiled" regression. Gotchas (PROTOTYPE): 3 channels pinned at 0 ADC; first 2–4 h are warm-up drift; gaps were linearly interpolated by the authors (straight segments where `r2_15m` = 1.0); the curve is a staircase, not a line. Credit: S. Surjith, Alex Raj S M, College of Engineering Trivandrum. |
| UCI 362, gas sensors for home activity monitoring https://archive.ics.uci.edu/dataset/362 | CC BY 4.0 (UCI default) | 8 Figaro TGS, ~1 Hz, 919k rows, 100 recordings, banana/wine inductions 7 min–2 h with ~1 h background before/after, SHT75 T/RH | step and spike **shape templates** (fake-data generator), clean-air noise from the 31 background recordings, humidity-confound check. Gotcha: irregular timestamps; we decimate to 5 s by median-of-5. |
| Kaggle/Zenodo food-freshness e-nose (Mahdian) https://doi.org/10.5281/zenodo.17285312 | CC BY 4.0 | 9 MQ sensors, ~10 fruits/vegetables, day-indexed files over ~5 days | optional augmentation / second replay source. Cadence inconsistently documented (UNVERIFIED), inspect first. |
| Kaggle seafood e-nose (ESF) https://www.kaggle.com/datasets/rafimahfuz/e-nose-based-fish-freshness-evaluation | CC0 | 7 MQ, 1 Hz, ~20 h, TVC-derived labels | backlog regression only; labels are simulator-derived. |
| UCI 322 dynamic gas mixtures https://archive.ics.uci.edu/dataset/322, UCI 224 drift https://archive.ics.uci.edu/dataset/224 | research use | 100 Hz step responses / 36-month drift feature vectors | not needed tonight. |

No public dataset records an MP503 or Grove Air Quality sensor, a lid-open disturbance in a small box, or a fridge at 4 °C. Our own sessions are the only shape-accurate data for the four classes.

### 5.2 Container protocol
Parameters below are OPINION unless marked; the literature gives protocols (purge → baseline → insert → stabilise → record) but not vent sizes for a 1–2 L box.
- **Container**: rigid 1.5–2 L food container with a flat lid. Sensor through the lid, element facing in, sealed with tape/hot glue, not touching food or walls (condensation warning, EVIDENCE: Danfoss gas-detection guidance against condensation locations). Keep the Grove PCB outside the box if possible so only the sensor can is inside; the heater (≤300 mW, EVIDENCE: MP503 manual) then warms the box less.
- **Vents**: start with **two ~3 mm holes** on opposite sides of the lid. This is a starting point, not a sourced value. Test: with cut garlic inside, the signal should reach a plateau within ~10 min (emission ≈ vent loss). If it keeps rising at 15 min, enlarge or add a hole; if garlic barely registers, cover one hole. The same test tells us whether "Strong but fine" is a step-plateau in our box (the concavity feature depends on it).
- **Food**: ~20–50 g samples on a small dish; the published sealed-jar protocols use 10–60 g (EVIDENCE: https://ift.onlinelibrary.wiley.com/doi/10.1111/1750-3841.15878, rancidity study 60 g). Wet food will push RH toward saturation within minutes in 1–2 L (OPINION from water activity ≈0.99); keep sessions ≤20 min and air out between.
- **Disturbance**: lift the lid fully for 10–15 s every 2 min, then close. Log each lift time in Serial/notes (we need them for the Hampel and `T_recover` tests). Expect a dip (dry room air) or a spike (VOC burst) — record which, and keep the sign in `fake_data_gen.py --dist-sign`.
- **Airing out**: lid off 5–10 min, wave or fan; confirm `ratio_mean` within `1 ± 3·sigma_1` before the next session (§3).
- **Avoid**: alcohol wipes, hand sanitizer, markers, breath near the vents during Fresh sessions (all are MOS stimulants). Never seal a strong VOC source in the box for long: Seeed warns that long exposure to heavily polluted air permanently weakens sensitivity (EVIDENCE: Seeed wiki), and the Winsen module manual says "do not put in high concentration organic gas for long time".

### 5.3 Recording protocol changes
Total ≈ 2.5 h including warm-up; start the warm-up while the relay is being built so recordings finish by ~10:30 pm.
1. **Warm-up** 45–60 min powered, lid closed, empty (overnight if possible). Record it: it is also our empty-container control (heater self-warming transient; the ACS fridge study ran a water blank for exactly this reason).
2. **Clean-air baseline** (5 min) → `baselines` row, `sigma_1`, `sigma_d`.
3. **Fresh** 20 min, empty closed box. Optionally a second Fresh with a neutral wet item (a cup of water) to see the humidity-only response: if that alone trips `T_step`, humidity is a confound we must mention and S11 becomes a priority.
4. **Disturbance** 15 min, lid lifts every 2 min as above.
5. **Strong but fine** 15–20 min: cut garlic or onion. Use a *moderate* source (a clove, not a crushed bulb) so it does not out-stink the spoiled sample; cheese is a second option.
6. Air out 10 min, verify baseline.
7. **Spoiling** 20+ min, **run last** (sensitivity-loss caution). Two variants:
   - **A (controlled ramp)**: pre-spoiled food (left out 24–48 h: meat juice, old banana, milk) placed in a small jar with a pierced lid *inside* the container, so VOCs leak out at a roughly constant rate and the headspace rises steadily over 15–20 min instead of stepping. OPINION, untested; the test is whether `r2_15m > 0.7` and `concavity_10m ≈ 0` for most windows. If it still steps, use variant B and accept level-based separation.
   - **B (natural)**: pre-spoiled food placed directly; expect a fast step to a high plateau, maybe near saturation.
   Record both if time allows; label both `Spoiling`.
8. **Controlled VOC source (hand sanitizer)**: useful for the sensitivity smoke test (S0) and for a quick "the sensor is alive" moment, **not** for training labels. 0.05 mL ethanol fully evaporated in 1.5 L is ~14,000 ppm, 14× the MP503's 1000 ppm upper range (calculation in the prior-projects follow-up; MP503 range EVIDENCE: Winsen manual). Even 1 µL gives ~280 ppm. Use a wipe waved near a vent, never a drop inside the box.

Write `label_sessions(device_id, label, start_ts, end_ts)` as you go; start_ts = after the lid is closed and the item is in. Drop the first 1 min of each session from training (edge of the step).

### 5.4 Fake-data and replay scripts
Already prototyped in `research/scripts/fake_data_gen.py` (bronze JSON lines or POST to the relay; `--realtime` for 5 s cadence):
- `fresh`: baseline + Gaussian noise (`--sigma-counts`, default 2 from PROTOTYPE) + rare 1-sample glitches of 100–800 counts (`--glitch-rate`, to exercise Hampel).
- `disturbance`: two excursions of ±0.15 ratio with 2-min exponential recovery, sign selectable (default dip).
- `strong`: first-order step of +0.40 toward a plateau, τ = 4 min (concave).
- `spoiling`: linear +0.004 ratio/min (about 2× the real beef rate so the demo pipeline shows it in 20 min; the flag says so).
- `replay`: streams the real-rate 20-min beef slice (minutes 674–694 of the dataset, ratio 1.03 → 2.42, `r2_15m` 0.88) rescaled to a chosen baseline. For the demo this is the honest "real spoilage, real rate" curve; it also shows a step-like jump, which is what real spoilage looks like at this resolution.
All shape amplitudes are placeholders until our own sessions exist; the script takes `--baseline` so it can be re-pointed at the measured MP503 baseline. The replay script for the demo should read our own recorded Spoiling session from `bronze_readings` (export to CSV at feature freeze) and re-POST it with fresh timestamps and `device_id = 'demo-replay'`.

## 6. Demo optimisation
- **Live**: lid open → "Disturbance, still Fresh" (works within a window or two; the dip/spike recovers in minutes). Garlic in → "Strong but fine, still Fresh" (step appears within ~1 min; plateau classification needs 5–10 min, so put the garlic in before the pitch starts and show the status flip in the chart history, or show the step live and the classification from a session recorded an hour earlier).
- **Replay**: Spoiling via the replay script at real rate from our own session (preferred) or the beef slice. Say plainly: "real spoilage takes hours to days; this is a recording, at real speed". Every surveyed project that tried to show spoilage live failed to (EVIDENCE: prior-projects report; the Adafruit milk experiment needed 5 days https://learn.adafruit.com/digital-nose-gas-sensor-milk-freshness-checker/experiment.md).
- **Raw vs processed side by side**: one notebook cell with `display()` of raw `ratio`, cleaned `sm`, and the status band; re-run inside the `while True` loop every 60–90 s. Dashboards cache for 24 h unless scheduled (EVIDENCE: https://docs.databricks.com/aws/en/dashboards/caching), so the notebook is the reliable live visual.
- **For hardware judges**: the Serial plot, the burst-median explanation (Wi-Fi ADC glitches), the 3.3 V decision, the empty-box control recording, the humidity caveat and what a DHT would add.
- **For Databricks judges**: bronze/silver/gold Delta tables, `DESCRIBE HISTORY baselines` time travel, `MERGE` idempotent recompute (late IoT data), `regr_slope`/`median` window functions, MLflow run comparison with LOSO CV, `@champion` alias swap without touching the job, scheduled job + the honest reason we run a loop on stage (serverless start latency, EVIDENCE: https://docs.databricks.com/aws/en/jobs/diagnose-job-performance).
- **Pitch framing that is novel vs prior art**: every hobby predecessor used a threshold on the raw value and had no answer to garlic; shape-based labels with a fixed cleanout baseline are our differentiator (EVIDENCE: prior-projects survey, e.g. https://www.hackster.io/eat-in-time/eat-in-time-87fd7a threshold at 100).

## 7. What we are NOT doing, and why
- **Auto-adapting / rolling-minimum baseline** (Seeed `slope()`, SGP30/CCS811 style): erases slow rises, the one thing we need to see.
- **Moving average, Savitzky–Golay**: smear the edges that define Disturbance and Strong-but-fine.
- **EMA**: needs recursive state (pandas UDF or recursive CTE); after Hampel + median it adds lag and nothing else.
- **CUSUM / Page–Hinkley / PELT online**: false alarms over long horizons without resets, parameters must be fit to replayed data, need a stateful loop. PELT is fine offline to sanity-check session labels; stretch.
- **Exponential curve fitting** of transients: fragile on ~100 noisy samples.
- **Theil–Sen slopes**: good, but a pandas UDF for a marginal gain over OLS on Hampel-cleaned data.
- **Time-compressed replay** of the 29-h curve as if it were live: slopes become ~400× too steep and the classifier trained on 20-min sessions would be lying; if we show the full arc, show it as a chart, not as a stream through the classifier.
- **Structured Streaming / watermarks**: the 60-min recompute + MERGE handles late data for free; streaming is the production upgrade line.
- **Zerobus**: see §0. Making it work would require our own cloud storage bucket (S3/ADLS/GCS) as a managed location, which costs money and breaks the $0 constraint.
- **Databricks Model Serving endpoints, performance-optimized jobs, larger warehouses**: not available or not free on Free Edition; the plan uses only the free 2X-Small serverless warehouse, serverless notebooks/jobs and MLflow.
- **Buying any hardware** (humidity sensor, capacitor, resistors, spare sensor): optional parts come from the hackathon hardware table for free or are skipped; the chain is designed to work with the sensor and ESP32 we already have.
- **Gradient boosting, SVM-RBF, kNN**: overfit at ~60–80 windows.
- **Temperature/humidity compensation models**: no sensor for it tonight; S11 is the hook.

## 8. Risks and fallbacks (post-processing specific)
| Risk | Signal | Fallback |
|---|---|---|
| MP503 baseline below the ESP32 ADC floor (~150 mV) or response too small at 3.3 V | clean-air counts < ~250 or alcohol-wipe response < 5% FS | 6 dB attenuation (free, firmware); then 5 V + 2:1 divider from free hardware-table resistors |
| Garlic and spoiled food both step-and-plateau | Strong vs Spoiling confusion in LOSO | merge to 3 classes (Fresh / Disturbance / Elevated) for the model; keep Spoiling as the amber "Watch" rule on sustained elevation; tell judges production uses `slope_6h` |
| Humidity alone trips `T_step` (water-cup Fresh test) | | state it; raise `T_step`; prioritise S11 |
| Lid-open signature is not a clean dip or spike | recovery takes >5 min | widen `T_recover` to the measured 90th percentile; rely on `mins_since_spike` + hysteresis |
| Warm-up drift contaminates Fresh | `slope_15m` nonzero in Fresh windows | longer warm-up; warming_up gate; retake baseline |
| Sensor desensitised by the Spoiling session | lower response in later tests | Spoiling last; spare sensor only if the hardware table has one; otherwise replay |
| `median()`/`RANGE INTERVAL` quirk on the warehouse | SQL error | `percentile_approx`; numeric `RANGE` on `unix_s`; or compute in `applyInPandas` |
| Serverless job starts minutes late during judging | | interactive `while True` loop (2.5-h serverless notebook timeout, EVIDENCE: https://docs.databricks.com/aws/en/compute/serverless/notebooks) |
| Free Edition daily quota exhausted | "Daily limit reached" | run the 2-min job only while recording/demoing; `max_concurrent_runs = 1`; do not upgrade to a paid plan — the fallback is the local model copy in the relay (§10 of the main plan) and the Serial plot |
| Hampel flags too many points | >2% flags in clean air | raise `sigma_floor`/nsigma to 4 |

## 9. Build order (fits §7 timeline) and open questions

**By 4 pm**: fake-data generator (done: `research/scripts/fake_data_gen.py`), Databricks signup, create tables incl. `baselines.reason`, confirm `median() OVER`, `regr_slope`, `RANGE BETWEEN INTERVAL` in one SQL cell. Hardware: wire at 3.3 V, GPIO34, 11 dB, burst median; read clean-air counts; run the alcohol-wipe smoke test; power the sensor and leave it on.
**By 7 pm**: relay → SQL Statement API → bronze with fake data (all four shapes). Silver SQL (§2.3) running on fake data; dummy rule classifier (§4.3 with placeholder sigmas) writing gold + alerts. Start the real sensor warm-up and the empty-box control recording in the container.
**By 10:30 pm**: clean-air baseline + sigmas; sessions in the order of §5.3; `label_sessions` filled; thresholds set from the recordings (tests in §4.2); re-run the fixed-threshold classifier on the recorded sessions and check the four shapes by eye in `display()`.
**By 1 am**: training notebook (LOSO, LR + tree, MLflow), register `@champion`, prediction job loads it; export our Spoiling session for the replay script.
**By 4 am**: alert transition SQL + n8n; the `while True` demo cell; side-by-side raw/processed chart; rehearse lid → garlic → replay.
Feature freeze: write the honest caveats (one sensor, room-temperature container, N sessions, replay) into the pitch.

**Open questions for the team**
1. Measured MP503 clean-air counts at 3.3 V on our ESP32, and the alcohol-wipe response (decides S0 power/attenuation).
2. Sign and recovery time of the lid-open event in our box (decides `T_recover` and the fake-data `--dist-sign`).
3. Does garlic plateau within 10 min with two 3 mm vents? (decides vent size and whether `concavity_10m` separates Strong from Spoiling.)
4. Does the pierced-jar Spoiling variant produce a steady ramp (`r2_15m > 0.7`)? If not, we accept level-based separation and say so.
5. Does a cup of water alone move the signal past `T_step`? (humidity confound severity; S11 priority.)
6. Which baseline-reset trigger do we ship (relay `POST /baseline` vs n8n webhook)?
7. Can the sensor be powered overnight before judging?
8. Confirm on the Free Edition warehouse: `median() OVER`, `RANGE BETWEEN INTERVAL`, `last_value(... IGNORE NULLS)`, job start latency, whether `performance optimized` is exposed (UNVERIFIED items from the Databricks report).

## Appendix A. Prototype results used above
From `research/scripts/out/summary.md` (reproduce with `download_data.sh` then `prototype_features.py`):
- Beef (Mendeley, 5 s): most monotonic channels MQ-135/MQ-138 (Spearman ρ ≈ +0.89) were pinned at 0 ADC in clean air; MQ-136 (baseline 161 counts) used instead. `sigma_d` = 2.1 counts (0.013 ratio). Hampel k=2 flag rate 9.8% without MAD floor → 2.3% with floor. Spoiled-phase median `slope_15m` = +0.0017 ratio/min (+0.10/h); steepest 20-min slice minutes 674–694, ratio 1.03 → 2.42, `r2_15m` 0.88. Warm-up: ratio 1.97 → ~0.5 over the first ~2 h.
- UCI 362 (decimated to 5 s): TGS2620 (R7) most banana-responsive (median excursion +0.10). Background noise after decimation ≈ 0 (`sigma_d` < 1e-4 ratio); Hampel flag rate 13% → 0.05% with the floor. Long inductions: concave step to plateau over 20–30 min (id 57: 1.0 → 1.38, `r2_15m` 0.64 at +10 min); short inductions recover; id 48 showed a large negative excursion (0.4) when the room was aired, i.e. a dip-type disturbance. RH–signal correlation on background recordings ranged −0.68 to +0.85, i.e. humidity moves this sensor type in either direction depending on conditions.

## Appendix B. Source index
Sensor: Winsen MP503 manual https://www.winsen-sensor.com/d/files/manual/mp503.pdf; Winsen ZP01-MP503 module manual https://www.winsen-sensor.com/d/files/zp01-mp503-4-grades-air-quality-module-v1_5-terminal-type.pdf; Seeed wiki https://wiki.seeedstudio.com/Grove-Air_Quality_Sensor_v1.3/; Seeed library https://github.com/Seeed-Studio/Grove_Air_quality_Sensor; Figaro TGS2600 tech info https://www.unitronic.de/wp-content/uploads/2026/09/12779_DB_TGS2600.pdf; MQ-135 datasheet https://www.electronicoscaldas.com/datasheet/MQ-135_Hanwei.pdf; MOS T/RH drift study https://pmc.ncbi.nlm.nih.gov/articles/PMC9101743/; jenslabs MQ-3/TGS822 recovery https://jenslabs.wordpress.com/2013/03/18/measured-sensor-characteristics-mq-3-and-tgs822/; OneTransistor startup false alarms https://www.onetransistor.eu/2023/01/mq-sensors-temperature-humidity.html.
ESP32 ADC: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html; https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/adc/adc_calibration.html; https://docs.espressif.com/projects/esp-faq/en/latest/software-framework/peripherals/adc.html; https://github.com/espressif/esp-idf/issues/8266; https://developer.espressif.com/blog/2025/08/adc-performance/.
Signal processing: https://www.mathworks.com/help/signal/ug/signal-smoothing.html; https://www.mathworks.com/help/signal/ref/hampel.html; https://blogs.sas.com/content/iml/2021/06/01/hampel-filter-robust-outliers.html; https://psi.engr.tamu.edu/wp-content/uploads/2018/01/gutierrezosuna2002sj.pdf; https://www.mdpi.com/1424-8220/15/11/27804; https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc3131.htm; https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html; https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data; auto-baseline behaviour https://learn.adafruit.com/adafruit-sgp30-gas-tvoc-eco2-mox-sensor/arduino-code.md, https://dfimg.dfrobot.com/nobody/wiki/ab83d61ed52c66c2dd4067eed25b0c35.pdf.
Prior projects: https://hackaday.com/2018/05/31/internet-of-smells-giving-a-machine-the-job-of-sniffing-out-spoiled-food/; https://github.com/benkw26/FoodFresh-Public; https://github.com/phpinto/fridgehound; https://www.hackster.io/eat-in-time/eat-in-time-87fd7a; https://github.com/iAnmolAgarwal/smart-e-nose; https://devpost.com/software/waste-not-wrd715; https://learn.adafruit.com/digital-nose-gas-sensor-milk-freshness-checker/experiment.md; https://pubs.acs.org/acsodf/article-pdf/8/5/4649/4087634/ao2c06386.pdf; https://ift.onlinelibrary.wiley.com/doi/10.1111/1750-3841.15878; https://www.mdpi.com/2673-4591/56/1/256; https://github.com/hevrosy/neuromorphic-enose-fpga; https://digitalcommons.usf.edu/etd/9188; https://www.mdpi.com/2227-9040/8/3/73.
Datasets: https://data.mendeley.com/datasets/n8mc3nspfn (CC BY 4.0 confirmed via https://data.mendeley.com/public-api/datasets/n8mc3nspfn?version=1); https://archive.ics.uci.edu/dataset/362; https://doi.org/10.5281/zenodo.17285312; https://www.kaggle.com/datasets/rafimahfuz/e-nose-based-fish-freshness-evaluation.
Databricks: https://docs.databricks.com/aws/en/sql/language-manual/functions/window; .../functions/regr_slope; .../functions/regr_r2; .../functions/median; https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-window-functions; https://docs.databricks.com/aws/en/delta/merge; https://docs.databricks.com/aws/en/getting-started/free-edition-limitations; https://docs.databricks.com/aws/en/jobs/diagnose-job-performance; https://docs.databricks.com/aws/en/compute/serverless/notebooks; https://docs.databricks.com/aws/en/dashboards/caching; https://docs.databricks.com/api/statement-execution; https://kb.databricks.com/dbsql/query-timeout-due-to-inactivity; https://learn.microsoft.com/en-us/azure/databricks/ingestion/zerobus-limits; Databricks Community threads 161228 (Zerobus 401 on Free Edition) and 140189 ("Daily limit reached"), URLs UNVERIFIED; https://learn.microsoft.com/azure/databricks/machine-learning/manage-model-lifecycle.
