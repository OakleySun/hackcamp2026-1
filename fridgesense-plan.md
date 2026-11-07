# FridgeSense: HackCamp 2026 Build Plan

A single air quality sensor in each shared UBC residence fridge streams readings into Databricks, an ML model spots food going bad, and RAs see which fridges need a cleanout on a website they log into.

---

## 1. Overview

**Problem:** Shared floor fridges in UBC residences fill up with forgotten food. It rots, the whole floor complains, and RAs end up policing it with sniff tests and cleanout notices.

**Users**
- **RAs:** need to know which fridge needs a cleanout before it becomes a crisis
- **Residents:** want a clean fridge and fair warning before their food is thrown out

**One-line pitch:** A ~$10 sensor and an ML model that spots rotting food in shared dorm fridges, so RAs act before the floor smells it.

**Target prizes**

| Prize | What we need |
| --- | --- |
| Overall / Beginner Overall | Automatic |
| Best Hardware | Opt in, working sensor in the demo |
| Community Impact | Opt in, impact statement on Devpost |
| Best Use of Databricks | Opt in, Databricks used for ingest, ML, prediction and retraining |
| Best use of n8n | Opt in, n8n sends RA alerts |
| Best Use of Vultr | Opt in, relay and website hosted on Vultr |
| Best Use of Auth0 | Opt in, RA login |
| Best Domain Name (GoDaddy) | Register a clever domain |

---

## 2. Architecture

```
Grove Air Quality Sensor v1.3
        |
      ESP32  --(HTTPS over Wi-Fi, phone hotspot)-->  Relay on Vultr (FastAPI)
                                                          |
                                                    Zerobus Ingest
                                                          v
   +------------------------- Databricks -------------------------------+
   |  bronze_readings -> silver_features -> prediction job -> gold_fridge_status |
   |                                             ^                      |
   |  label_sessions + ra_feedback -> training (MLflow) -> registered model |
   +--------------------------------------------------------------------+
                                                          |
                         RA website (Auth0 login)  <--  relay GET /status
                         n8n alerts (text/email to RA)  <--  alerts table
                                  |
                RA feedback ("rotten" / "false alarm") -> ra_feedback
```

Open question: which board is the sensor on? **ESP32** sends over Wi-Fi from anywhere (this plan assumes ESP32). An **Arduino Uno** has no Wi-Fi, so readings would go over USB to a laptop script that forwards them to the relay.

---

## 3. Hardware

**Sensor:** Grove Air Quality Sensor v1.3 (Winsen MP503 chip). It reacts to many gases (CO, alcohol, acetone, formaldehyde and others) but gives a qualitative reading, not a concentration.

**What it outputs:** one raw analog value. On the ESP32 that is 0 to 4095 (12-bit ADC); higher means more of the gases it detects. No units, no temperature, no gas identity.

**Wiring (ESP32)**
- Red: 3.3V (the sensor supports 3.3V and 5V; 3.3V keeps the output safe for the ESP32, no voltage divider needed)
- Black: GND
- Yellow: signal, to an **ADC1 pin (GPIO 32 to 39)**. ADC2 pins stop working when Wi-Fi is on.
- White: not connected

**Sensor quirks to handle**
- Seeed's library keeps updating its own baseline, so the sensor slowly treats any air as "normal." That would hide slow spoilage. **Do not use the library's `slope()`; read raw values with `analogRead()`.**
- Needs relatively clean air at start-up. Warm up for 10 to 15 minutes before recording.
- Long exposure to heavily polluted air reduces its sensitivity.

**ESP32 firmware tasks**
- [ ] Connect to Wi-Fi (phone hotspot; eduroam and ubcvisitor will not work)
- [ ] Sync time with NTP on boot
- [ ] Every 5 seconds: take 10 quick reads, average them, send one reading
- [ ] HTTPS POST JSON to the relay with a device API key header
- [ ] Buffer readings in memory if Wi-Fi drops, resend on reconnect
- [ ] Print every reading to Serial for debugging

**Reading format**

```json
{"device_id": "res-floor-3", "ts": "2026-11-07T15:20:05Z", "raw_adc": 1384}
```

**Other parts:** power bank + USB cable for the judging table, a small box or cooler as the demo "fridge" (use the same box for training data and the demo).

---

## 4. Relay and ingestion (Vultr)

A small always-on FastAPI server on Vultr receives readings and pushes them into Databricks, so the system works from anywhere, not only from a laptop.

**Endpoints**
- `POST /readings`: checks the device API key, forwards to Databricks
- `GET /status`: latest status per fridge from `gold_fridge_status` (used by the website)
- `POST /feedback`: saves RA answers to `ra_feedback`
- `GET /health`: server check

**Into Databricks:** Zerobus Ingest REST insert into `bronze_readings`. The relay holds the Databricks OAuth credentials (service principal); the ESP32 never sees them.

**Fallback if Zerobus is not available on Free Edition:** the relay writes batches of readings with the Databricks SQL Statement Execution API through the free SQL warehouse.

- [ ] Sign up for Databricks Free Edition; check Zerobus availability (timebox 30 min)
- [ ] Vultr server running the FastAPI relay with HTTPS
- [ ] Fake-data script that POSTs realistic readings (build first, unblocks everyone)
- [ ] Relay forwards to Zerobus, or to the SQL API fallback

---

## 5. Databricks layer

Everything lives in one schema, e.g. `workspace.fridgesense`.

| Table | Columns | Written by |
| --- | --- | --- |
| `bronze_readings` | device_id, ts, raw_adc, ingest_ts | Zerobus via relay |
| `baselines` | device_id, baseline_adc, set_at | After warm-up and after each cleanout |
| `silver_features` | device_id, window_end, ratio_mean, ratio_max, ratio_var, slope_30m, mins_since_spike, last_step_size | Feature job |
| `label_sessions` | device_id, label, start_ts, end_ts | Filled in while recording training data |
| `gold_fridge_status` | device_id, status, confidence, last_updated | Prediction job |
| `alerts` | device_id, status, alert_ts | Prediction job (read by n8n) |
| `ra_feedback` | device_id, alert_ts, ra_says_rotten | Website via relay |
| `fridges` | device_id, building, floor, ra_email | Set up once by hand |

### Step 1: Bronze
Raw readings exactly as received. Nothing cleaned or changed.

### Step 2: Baselines (our fix for sensor drift)
Record the average reading in clean air after warm-up. Every later reading becomes:

```
ratio = raw_adc / baseline_adc     (1.0 = like clean air, 1.4 = 40% worse)
```

Re-set the baseline only after a fridge cleanout, a natural real-world reset point ("RA confirms cleanout, new baseline").

### Step 3: Silver features (per fridge, per window)
- 2-minute window: average ratio, max ratio, variance (catches spikes)
- 30-minute rolling slope of the ratio (catches slow spoilage); `regr_slope()` in Databricks SQL does this
- Minutes since the last spike (separates "door just opened" from real change)
- Size of the most recent step up (strong food added)

### Step 4: Labels
With only the air quality sensor, the model reads everything from the shape of one signal:

| Label | Signal shape | RA sees |
| --- | --- | --- |
| Fresh | Flat, close to baseline | Fresh |
| Disturbance (door opened) | Quick spike, back to baseline within minutes | Fresh |
| Strong but fine (garlic, kimchi) | Sudden step up, then flat | Fresh |
| Spoiling | Slow, steady rise over 30+ minutes | Watch / Going bad |

No temperature sensor means no "fridge failing" detection; say so if asked.

**Recording protocol** (same sensor, same box as the demo, after warm-up; write down start and end times into `label_sessions`):
1. Empty closed box, 20 min: Fresh
2. Open and close the lid every 1 to 2 min, 15 min: Disturbance
3. Fresh garlic, onion or cheese, 15 min each: Strong but fine
4. Something already going bad (old banana peel, food left out, warm milk), 20+ min: Spoiling

### Step 5: Training notebook (MLflow)
- [ ] Join `silver_features` to `label_sessions`
- [ ] Train Random Forest, gradient boosting and logistic regression (scikit-learn)
- [ ] MLflow tracks accuracy, confusion matrix, feature importance for each
- [ ] Register the best as `workspace.fridgesense.spoilage_model`
- [ ] Save a local copy for the backup demo

### Step 6: Public dataset notebook ("hours until spoiled")
Use the published e-nose beef spoilage dataset (ESP32 + MQ-series sensors, readings every 5 s for ~29 hours, labeled Excellent / Good / Acceptable / Spoiled with microbial counts): https://data.mendeley.com/datasets/n8mc3nspfn (check the licence; credit the authors).
- Convert to ratio-to-baseline so it is as sensor-independent as possible
- Train a regression model predicting hours until "Spoiled"
- Be clear in the pitch: different sensor (MQ vs our MP503) and meat at room temperature, so this proves the pipeline and the idea, not production accuracy

### Step 7: Prediction job (every 1 to 2 minutes)
One notebook job: read the last hour of bronze, compute features, load the registered model, write `gold_fridge_status`, and add a row to `alerts` when a fridge turns red. More reliable at a hackathon than a full streaming pipeline; mention streaming as the production upgrade.

### Step 8: Feedback and retraining
RAs tap "Yes, it was rotten" or "False alarm." Answers land in `ra_feedback`; a scheduled job retrains, and MLflow shows accuracy across model versions.

**Optional showcase:** serve the model on a Databricks Model Serving endpoint as well.

**Free Edition limits:** one active pipeline per type, one small SQL warehouse, a few serving endpoints, no GPU. This design fits.

**Build order inside Databricks**
1. Bronze table with fake data flowing in
2. Baselines + silver features, tested on fake data
3. Prediction job with a dummy rule (ratio > 1.5 = red) so the website works end to end
4. Record labeled data, train, swap the dummy rule for the real model

---

## 6. RA website

RAs log in with Auth0 and see only their building's fridges as Fresh, Watch or Going bad. The server reads Databricks through the relay, so no credentials reach the browser.

**Pages**
- Login (Auth0)
- Fridge list: status colour, confidence, last updated, "sensor offline" if no reading for 2 min
- Fridge detail: sensor ratio chart over time, recent alerts, "Was this right?" buttons
- Public demo page (no login): live status of the demo fridge for judges' phones

**Alerts (n8n):** when a fridge turns Going bad, n8n texts or emails its RA with a ready-to-post cleanout notice.

**Stretch:** translate the cleanout notice into residents' languages with Databricks AI Functions (`ai_query`).

- [ ] Figma wireframes (needed for design prizes)
- [ ] Website shell with Auth0 login and dummy statuses
- [ ] Connect to `GET /status`
- [ ] Detail chart and feedback buttons
- [ ] n8n workflow for RA alerts
- [ ] Register the domain (GoDaddy Registry)

---

## 7. Team roles and build order

| Role | Owns |
| --- | --- |
| Hardware | ESP32 + sensor, firmware, labeled data recording |
| Data / ML | Databricks tables, features, training, prediction job, feedback loop |
| Backend | Vultr relay, Zerobus / SQL API, Auth0, n8n |
| Frontend / design / pitch | Figma, website, RA interviews, Devpost, pitch |

**Timeline (Saturday afternoon to Sunday morning)**
1. **By 4pm:** fake-data script, Databricks signup + Zerobus check, Vultr server, Figma wireframes, interviews started
2. **By 7pm:** relay to Databricks end to end with fake data; website login with dummy statuses
3. **By 10pm:** real sensor data flowing; labeled recordings done
4. **By 1am:** model trained and registered; prediction job writing gold; website shows real statuses
5. **By 4am:** n8n alerts, feedback buttons, public dataset model, polish
6. **Feature freeze:** Devpost, slides, rehearse the demo 3 times, sleep

Open question: judging time (check Discord) and whether we are in the beginner stream.

---

## 8. Demo, pitch and Q&A

**Live demo (under 90 seconds)**
1. Hand a judge a phone with the public demo page open
2. Open the box lid: page updates, classified "Disturbance," still Fresh
3. Put fresh garlic in: classified "Strong but fine," still Fresh (not a false alarm)
4. Replay recorded spoilage data (real spoilage takes days): status turns Going bad, RA phone buzzes
5. Show Databricks: MLflow model comparison, "hours until spoiled" prediction

**4-minute pitch** (rubric: Problem Research, Technical Implementation, Design, Innovation, Pitch)

| Time | Content |
| --- | --- |
| 0:00 to 0:40 | The problem, opened with a real quote from a res student or RA |
| 0:40 to 2:10 | Live demo |
| 2:10 to 3:10 | How it works: one sensor, drift fix, Databricks pipeline, ML model |
| 3:10 to 3:40 | Design and accessibility: Figma, simple 3-colour status |
| 3:40 to 4:00 | Impact: every shared fridge in UBC residences, ~$10 sensor each |

**Q&A prep**
- **Is this surveillance?** It monitors the fridge, not people: no cameras, no names.
- **Smelly but fine food?** The model reads signal shape over time; shown live with garlic.
- **Cheap sensors drift.** Yes, that is why we lock a baseline at each cleanout and detect slow change ourselves instead of using the sensor library's auto-baseline.
- **Accuracy?** Give the real MLflow test accuracy and say it is a small proof-of-concept dataset.
- **Why Databricks?** One fridge is one sensor; every residence fridge streaming all year is a real dataset. Databricks handles ingest, training, prediction and retraining in one place.
- **Why no temperature?** One sensor keeps cost minimal; adding a temperature sensor would enable fridge-failure alerts.
- **Wi-Fi drops?** The ESP32 buffers and resends; the dashboard flags offline sensors.

---

## 9. Problem research and Devpost

**Ask 5+ res students (and any RAs) at the venue**
1. How often does your shared fridge get gross? Who deals with it?
2. Have you had food thrown out, or found something rotten?
3. (RAs) How much time do fridge complaints and cleanouts take?
4. Would an alert before it smells change what you do?

Write down exact quotes, names (with permission) and residence.

**Devpost checklist**
- [ ] Problem statement and solution description
- [ ] Impact statement (Community Impact)
- [ ] Figma link (design prizes)
- [ ] How we used Databricks, Vultr, Auth0, n8n (a short paragraph each)
- [ ] Credit the public e-nose dataset
- [ ] Photos of the hardware, screenshot of the dashboard
- [ ] Opt into every prize we qualify for (check for a cap on opt-ins)
- [ ] Domain name listed

---

## 10. Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Zerobus not available on Free Edition | SQL Statement Execution API into the same table |
| Databricks slow at judging | Local model copy in the relay; website reads from the relay |
| Sensor drift or noisy data | Fixed baseline, averaged reads, replay script of recorded data |
| Sensor breaks | Replay recorded readings; spare sensor from the hardware table |
| Venue Wi-Fi blocks the ESP32 | Phone hotspot (plan A anyway) |
| Not enough labeled data | Fewer classes (Fresh vs Spoiling); be honest about dataset size |
| Running out of time | Cut stretch goals first: translation, model serving, retraining |
| Battery dies | Laptop charger, power bank for the ESP32 |
