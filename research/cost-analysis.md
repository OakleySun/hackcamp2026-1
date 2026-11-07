# FridgeSense post-processing: cost analysis

Decision (2026-11-07): **the post-processing chain is a $0 build.** Nothing is bought; optional parts come from the hackathon hardware table or are skipped. `research/postprocessing-plan.md` has been edited to reflect this.

## What was always free
- Databricks Free Edition: Delta tables, Databricks SQL on the 2X-Small serverless warehouse, serverless notebooks/jobs, MLflow, scikit-learn. No paid features are used (no external cloud storage, no Model Serving, no performance-optimized jobs, no larger warehouse).
- Public datasets: Mendeley beef e-nose n8mc3nspfn (CC BY 4.0, verified via the Mendeley API), UCI 362 home-activity (CC BY 4.0), Kaggle/Zenodo fruit e-nose (CC BY 4.0), Kaggle seafood e-nose (CC0).
- Firmware changes (burst median, attenuation setting), all SQL/PySpark, the rule classifier and the model.
- Food for recordings: garlic/onion/cheese and pre-spoiled leftovers we already have.

## What the original draft could have cost
Prices from vendor pages checked 2026-11-07 (USD, before shipping).

| Item | Where it appeared | Approx. price | Status now |
|---|---|---|---|
| DHT22 humidity sensor (or DHT11) | S11 stretch | DHT22 $6.95–10.64 (Seeed, RobotShop, Waveshare); DHT11 $2–5 | only if free at the hardware table; cup-of-water Fresh session is the $0 substitute |
| Spare Grove Air Quality Sensor v1.3 | risk fallback | $6.90 (Seeed) | only if the hardware table has one; otherwise replay recorded data |
| 100 nF capacitor | S0 noise fix | pennies, $3–6 for a pack | skipped; burst median does the job in software |
| Two resistors for a 2:1 divider (5 V option) | S0 / ADC-floor fallback | pennies, $3–6 for a pack | hardware table only; 6 dB attenuation (free firmware change) comes first |
| Zerobus ingest | ingestion path | $0 subscription but needs our own S3/ADLS bucket (cloud account + card) | rejected on technical and cost grounds; SQL Statement Execution API instead |

Totals under the original draft: $0 with hardware-table parts; about $7–10 if only a DHT22 were bought; roughly $15–30 if everything were bought retail.

## Outside this document
Vultr hosting, n8n Cloud and the GoDaddy domain are in the main plan (§4, §6) and were never part of the post-processing budget. Check they are covered by hackathon credits or free tiers.

## Rule going forward
If a step cannot be done with what we already have plus Databricks Free Edition, it is a stretch item and gets dropped before anything is purchased.
