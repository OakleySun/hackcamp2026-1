#!/usr/bin/env bash
# Downloads the two public datasets used by prototype_features.py into ./data
# 1. Mendeley n8mc3nspfn (CC BY 4.0) - beef e-nose, ESP32 + MQ sensors, 5 s, ~29 h
# 2. UCI 362 (CC BY 4.0) - gas sensors for home activity monitoring, ~1 Hz
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data
curl -sL -o data/beef_4classes.csv \
  "https://data.mendeley.com/public-files/datasets/n8mc3nspfn/files/8b21e9d0-c805-40bd-814b-9778795c13b2/file_downloaded"
curl -sL -o data/uci362.zip \
  "https://archive.ics.uci.edu/static/public/362/gas+sensors+for+home+activity+monitoring.zip"
unzip -o -q data/uci362.zip -d data/uci362
(cd data/uci362 && unzip -o -q HT_Sensor_dataset.zip)
ls -la data data/uci362
