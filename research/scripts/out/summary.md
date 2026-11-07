# Prototype results

## 1. Mendeley beef e-nose (n8mc3nspfn, CC BY 4.0), 5 s sampling

rows=20815  minutes=1..1735  cols=['Mq-2', 'Mq-3', 'Mq-4', 'Mq-5', 'Mq-135', 'Mq-136', 'Mq-137', 'Mq-138']
class counts: {1: 2940, 2: 2268, 3: 2292, 4: 13315}
ADC range per sensor: Mq-2:435-1702, Mq-3:234-926, Mq-4:0-129, Mq-5:1086-2347, Mq-135:0-547, Mq-136:59-551, Mq-137:359-922, Mq-138:0-223
Spearman rho vs time (monotonic rise => good replay channel): Mq-135:+0.89, Mq-138:+0.88, Mq-136:+0.88, Mq-4:+0.83, Mq-3:+0.61, Mq-137:+0.59, Mq-5:+0.46, Mq-2:-0.12
first-30-min median ADC per sensor: Mq-2:937, Mq-3:458, Mq-4:31, Mq-5:1766, Mq-135:0, Mq-136:161, Mq-137:562, Mq-138:15
sensors clipped at/near the ADC floor in 'clean' air (baseline <100 counts, unusable for a ratio): ['Mq-4', 'Mq-135', 'Mq-138']
-> most monotonic channel with a usable baseline: Mq-136
baseline(first 30 min median)=161 ADC; sigma_1(level)=0.2578, sigma_d(diff)=0.0130 in ratio units (= 41.5 / 2.1 ADC counts). NOTE: sigma_1 is inflated by warm-up drift; sigma_d is the usable noise estimate.
Hampel k=2 flag rate: 9.79% without MAD floor -> 2.29% with floor max(1 count, sigma_d)=0.0130

Per-class summary of real spoilage ramp (ratio units):
| class | span (min) | ratio start->end | median slope_15m (ratio/min) | median r2_15m | median pos_diff_frac | median concavity |
|---|---|---|---|---|---|---|
| 1 | 1-245 | 1.969->0.783 | -0.00050 | 0.55 | -0.01 | -0.00039 |
| 2 | 246-434 | 0.783->1.062 | +0.00133 | 0.13 | 0.01 | -0.00006 |
| 3 | 435-625 | 1.124->1.043 | +0.00094 | 0.40 | 0.03 | -0.00008 |
| 4 | 626-1735 | 0.963->3.217 | +0.00168 | 0.43 | 0.01 | +0.00000 |

Steepest 20-min slice: minutes 674-694, ratio 1.025->2.422, slope_15m at end=+0.05153/min, r2=0.88, pos_diff_frac=0.10
REAL spoilage rate (class 4 median slope_15m) = +0.00168 ratio/min = +0.101 ratio/hour; over a 20-min session that is a 0.034 ratio change = 2.6 sigma_d.
T_slope guard (3*sigma_d over 15 min) = 0.00260 ratio/min; fraction of 'Spoiled'(class 4) samples with slope_15m > guard: 41%; of 'Excellent'(class 1): 21%

## 2. UCI 362 home-activity (banana inductions), decimated to 5 s

rows=928991  recordings=99  classes={'wine': 36, 'banana': 33, 'background': 31}
banana induction durations (h): min=0.12 median=0.58 max=1.69
short banana ids=[33, 48, 22]  long banana ids=[0, 57, 39]  background ids used=[69, 70, 71, 72, 73]
median banana excursion (R0/R - 1) per sensor: R1:+0.021, R2:+0.018, R3:+0.059, R4:+0.023, R5:+0.063, R6:+0.030, R7:+0.101, R8:+0.062
-> using R7
background recordings: sigma_1(level) median=0.0328, sigma_d(diff) median=0.0000 (ratio units, R7)
Hampel k=2 flag rate on background: median 12.95% without floor -> 0.05% with MAD floor = sigma_d

| id | dt (min) | kind | ratio peak | step at onset (last_step_size max) | slope_5m max | slope_15m max | r2_15m at +10 min | concavity at +10 min | recovered to <20% of excursion after (min) |
|---|---|---|---|---|---|---|---|---|---|
| 33 | 7 | short (Disturbance-like) | 0.969 | +0.025 | +0.0094 | +0.0024 | 0.84 | +0.0067 | 0.0 |
| 48 | 17 | short (Disturbance-like) | 1.725 | +0.199 | +0.1392 | +0.0679 | 0.36 | -0.1157 | 10.1 |
| 22 | 17 | short (Disturbance-like) | 1.089 | +0.015 | +0.0100 | +0.0031 | 0.46 | -0.0088 | nan |
| 0 | 98 | long (Strong-but-fine-like) | 1.811 | +0.617 | +0.2154 | +0.0764 | 0.78 | +0.0534 | nan |
| 57 | 101 | long (Strong-but-fine-like) | 1.381 | +0.029 | +0.0249 | +0.0143 | 0.64 | -0.0151 | nan |
| 39 | 101 | long (Strong-but-fine-like) | 1.071 | +0.053 | +0.0370 | +0.0107 | 0.04 | -0.0207 | 2.6 |

Background RH vs R7 ratio correlation (where RH moved >0.5%): [-0.58, 0.13, 0.85, -0.68]
