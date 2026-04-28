# G8-RealTimeSystemsProj2

02225 DRTS Mini-Project 2: TSN Credit-Based Shaper Analysis & Simulation.
This project implements an analytical tool and a Discrete-Event Simulator
(DES) that compute Worst-Case Response Times (WCRT) for TSN streams, and
compares Credit-Based Shaper (CBS, IEEE 802.1Qav) against Strict Priority
(SP) shaping.

## Project layout

```
.
├── tsn/                       Core package
│   ├── analytical.py          Cao et al. (2016) CBS WCRT computation
│   ├── sp_analytical.py       Strict-Priority WCRT via classical RTA
│   ├── simulator.py           Discrete-event simulator (CBS / SP)
│   ├── slope.py               idleSlope policies (equal-split, proportional)
│   ├── hyperperiod.py         LCM-of-periods helper
│   ├── pessimism.py           Gap analysis (analytical vs simulated)
│   └── io.py                  JSON loader
├── run_demo.py                CLI: analytical WCRT for one test case
├── run_simulations.py         CLI: simulate one test case + chart
├── run_multi_case.py          CLI: drive all test_cases/case_*/, aggregate
├── test_cases/
│   ├── generate_cases.py      Reproducible synthesis of low/med/high cases
│   ├── case_low/  case_med/  case_high/   {topology,streams,routes}.json
└── test-case-1-{topology,streams,routes}.json   Original assignment input
```

## Prerequisites

```
pip install matplotlib numpy
```

The analytical tool only uses the standard library; `matplotlib`/`numpy`
are needed for the comparison charts.

## How to run

### 1. Analytical WCRT (single case)

```
python3 run_demo.py                        # uses test-case-1-*.json at root
python3 run_demo.py --case test_cases/case_med
```

Stream 0 of the original test case must equal **603.2 µs** (regression).

### 2. CBS vs SP simulation (single case)

```
python3 run_simulations.py --no-show       # original test case
python3 run_simulations.py --case test_cases/case_med --policy proportional
```

Simulation duration is set to **2 × hyperperiod** (LCM of stream periods),
which deterministically covers every release-phase alignment for periodic
streams released synchronously at t=0. The duration and hyperperiod are
printed at the top of every run.

Flags:
- `--policy {equal,proportional}` — idleSlope policy (default: equal)
- `--factor N` — simulate `N × hyperperiod` instead of 2
- `--plot path.png` — chart output (`""` to disable)
- `--no-show` — don't open a window

### 3. Multi-case sweep

```
python3 test_cases/generate_cases.py       # (re)generate the three cases
python3 run_multi_case.py                  # run analytical+sim on each
```

`run_multi_case.py` produces a side-by-side table of analytical bounds
under both equal-split and proportional idleSlope policies, prints a
pessimism gap table per case (tight / moderate / loose buckets), and
exits non-zero if any analytical bound is violated.

## Slope policies

`tsn/slope.py` defines `SlopeConfig`, the per-PCP idleSlope (as a
fraction of link bandwidth). Cao's `alpha = sendSlope / idleSlope =
(1 − idle) / idle` is computed from the configured idleSlope, so
analytical SPI and HPI now adapt automatically when slopes change.

- **`equal_split()`** — idle = 0.5 for every CBS class (the
  assignment's default; matches the original 603.2 µs for stream 0).
- **`proportional_idle_slope(streams, routes, topology)`** — per
  output port, allocate the CBS bandwidth budget (95% by default) in
  proportion to per-class offered utilisation. Tightens the bound for
  the heavier class; loosens it for the lighter class. On `case_med`
  this reduces every CBS stream's analytical WCRT by 17–21%.

## Strict-Priority RTA (analytical SP)

`tsn/sp_analytical.py` computes a classical non-preemptive fixed-priority
response-time bound per output port:

    R_i^{n+1} = C_i + B_i + Σ_{j ≠ i, prio(j) ≥ prio(i)} ⌈R_i^n / T_j⌉ · C_j

with B_i = max C_k over lower-priority streams on the same link, and
end-to-end WCRT = sum across hops. Unlike Cao's CBS analysis, SP RTA
yields a finite bound for BE (PCP 0) too — which is exactly the
asymmetry the project highlights: CBS can't bound BE analytically, but
behaviourally protects BE through the credit mechanism, while SP can
bound BE analytically but in practice lets BE drift up under heavy AVB
load. The multi-case driver shows both bounds side-by-side and verifies
each against its corresponding simulation.

## Sources of pessimism

`tsn/pessimism.py` reports per-stream gap = analytical − simulated, and
classifies streams as tight (<5%), moderate (<20%), or loose. The
analytical model over-approximates because it assumes:

1. **Critical-instant release.** All same-priority streams release
   simultaneously with the target; real systems have phase offsets
   that the bound cannot exploit.
2. **Independent per-hop interference.** The end-to-end WCRT is a sum
   of worst-case per-hop delays, but a stream that queues behind us at
   hop 1 cannot also block us at hop 2.
3. **Maximum-credit assumption.** HPI assumes the higher class enters
   our window with maximum accumulated credit, which only holds if it
   has been blocked for its full LPI immediately before our arrival.

The `run_multi_case.py` summary table makes the gap explicit per case.

## Soundness invariant

For every stream of an AVB class, **analytical WCRT ≥ simulated
maximum response time**. The multi-case driver enforces this and
returns a non-zero exit status if any stream violates it.
