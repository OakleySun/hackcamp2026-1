# Can the Grove Air Quality Sensor v1.3 (MP503) realistically detect what we claim?

Assessment, 2026-11-07, based on the five research reports and the prototype in `research/scripts/`. Legend: EVIDENCE (sourced), PROTOTYPE (measured on public data), OPINION (inference).

## Short answer
- **Demo in the room-temperature container:** yes for Fresh, Disturbance and "something strong is in here". The weak spot is telling *garlic* from *spoiled food* by signal shape within a 20-minute session.
- **Real cold shared fridge over days:** plausible in principle, unproven with one under-powered MP503. Pitch it as a proof of concept.

## What the sensor is
- Generic SnO2 metal-oxide chemiresistor; datasheet targets alcohol, smoke, iso-butane, formaldehyde; range 10–1000 ppm alcohol; qualitative only; heater specified at 5.0 V +-0.1 V (EVIDENCE: Winsen MP503 manual https://www.winsen-sensor.com/d/files/manual/mp503.pdf).
- Same class as the MQ series. In the beef-spoilage dataset the MQ-3 alcohol sensor, the closest analogue to the MP503, rose about 2x over 29 h in a sealed chamber (ADC 234 -> 926) because spoilage releases ethanol, acetone, aldehydes and sulfides (PROTOTYPE, Mendeley n8mc3nspfn).
- Our unit is weaker than the datasheet case: heater at 3.3 V (Seeed documents this as allowed; sensitivity loss unknown) and no 48 h burn-in (expect hours of drift on first power-up; PROTOTYPE showed a 2 h settling transient on a comparable sensor).

## Label-by-label

| Label | Realistic? | Reasoning |
|---|---|---|
| Fresh (flat near baseline) | Yes | Trivial once warm-up is gated and a baseline is set. Risk: humidity and drift; handled by sigma-scaled thresholds and the warming-up state. |
| Disturbance (lid open) | Yes, high confidence | Any MOS reacts to an air exchange (humidity, temperature, VOC all change). Sign unknown, likely a dip because humid box air is replaced by drier room air (EVIDENCE: higher RH lowers Rs, Figaro TGS2600 table; direction for our module UNVERIFIED). Recovery time unknown; first lid test settles both. |
| Strong but fine (garlic) | Registers: high confidence. Step-then-plateau shape: untested | Cut garlic releases sulfur compounds SnO2 responds to; 1–2 L headspace concentrates them. Whether it plateaus within 10 min depends on vent size (OPINION; test in §5.2 of the plan). |
| Spoiling, 20-min session | Registers: yes. Distinguishable from garlic by shape alone: coin-flip | Pre-spoiled food placed in the box produces a step like garlic. Real spoilage rises at about +0.10 ratio/hour, i.e. ~2.6 noise sigmas over 20 min (PROTOTYPE). The pierced-jar controlled-release variant is our attempt to make a ramp; untested. Fallback: separate by level/persistence or merge to three classes. |
| Spoiling in a real fridge over days | Plausible, low-to-moderate confidence | MOS arrays have tracked meat at 4 C over days (EVIDENCE: sardine e-nose https://www.mdpi.org/sensors/papers/s6101209.pdf; OFET fridge study https://pubs.acs.org/acsodf/article-pdf/8/5/4649/4087634/ao2c06386.pdf). Against us: cold food emits far less VOC, 100–300 L volume vs 1.5 L, constant door openings, compressor humidity cycles, one unselective sensor, no public MOS-in-a-running-fridge data. |

## Caveats to state in the pitch
1. "Before the floor smells it" is a placement claim, not a sensitivity claim. Human noses detect sulfides and amines at ppb; MOS sensors work around ppm (general knowledge, not from our sourced reports). Our edge: the sensor sits inside the closed fridge where concentrations accumulate, and it never habituates.
2. The demo proves that one cheap sensor plus shape-based post-processing separates "nothing", "door opened" and "something strong is in here", and that the pipeline would catch a slow rise. It does not prove early spoilage detection in a real fridge. Prior projects that claimed more without multi-day validation read as unconvincing (EVIDENCE: prior-projects survey in the plan).

## Free ways to improve the odds
- Heater at 5 V via a divider only if resistors are free at the hardware table; the alcohol-wipe smoke test at 3.3 V (<5% full-scale response) tells us if it matters.
- Power the sensor as early as possible, ideally overnight.
- Moderate Strong-but-fine source (one clove, or cheese) and a strongly spoiled sample so a level gap works in our favour if shape does not.
- Record the cup-of-water Fresh session to measure the humidity-only response before judges ask.

## Decision rule
If the first hour of recordings shows garlic and spoiled food with identical shape and level, switch to the three-class fallback (Fresh / Disturbance / Elevated) with Spoiling as a sustained-elevation amber "Watch" rule, and say so honestly.
