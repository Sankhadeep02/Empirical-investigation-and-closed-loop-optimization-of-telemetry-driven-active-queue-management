# DESiRED Evaluation & Enhancement Testbed: Open-Source Artifacts

This repository provides the complete, reproducible experimental artifacts, simulation harnesses, datasets, neural network weights, and analysis pipelines supporting the dissertation:

> **"Empirical Investigation and Closed-Loop Optimization of Telemetry-Driven Active Queue Management in Programmable Data Planes"**

---

## 1. Directory Structure

```
DESiRED/
├── src/
│   ├── dataplane/
│   │   ├── DESiRED.p4             # The core P4-16 data plane pipeline (BMv2)
│   │   └── DESiRED.json           # Compiled P4 switch bytecode
│   ├── controlplane/              # DRL control plane agent & environment
│   │   ├── agent.py               # DDQN agent implementation
│   │   ├── environment.py         # Control loop state/action environment
│   │   └── receiveMetrics.py      # Telemetry parser
│   └── logs/                      # Raw per-second execution and run logs
├── testbed/                       # Mininet network environment & daemons
│   ├── start_topology_v4.py       # P4 Mininet 3-switch topology launcher
│   ├── topology.py                # Mininet network definition
│   ├── populate_tables.sh         # Switch runtime rules & mirror session 2 setup
│   ├── int_sender.py              # Telemetry probe emitter
│   ├── int_receiver.py            # Telemetry probe parser
│   └── video_simulator.py         # Video buffer simulation model
├── scripts/                       # Experiment harnesses & analysis tooling
│   ├── run_within_run_tcp_test.py # Responsive TCP Cubic within-run test (N=3)
│   ├── run_within_run_mechanism_test.py # UDP within-run step test runner
│   ├── audit_mechanism_validity.py# Validity & physical ceiling audit engine
│   ├── generate_dissertation_tables.py # Script generating all LaTeX tables from CSVs
│   ├── validate_run.py            # Automated run validator
│   └── run_experiment.py          # Single-run execution harness
├── results/                       # Audited experimental datasets
│   ├── campaign_v1/               # Unshaped baseline runs
│   ├── campaign_v2/               # 104-run multi-load sweep & control batch
│   ├── campaign_v3/               # Initial shaped runs (100% buffer tail-drop)
│   └── campaign_v4/               # Validated mechanism study:
│       ├── mechanism_test_valid.csv         # Valid UDP within-run runs
│       ├── mechanism_test_excluded.csv      # Excluded UDP runs audit
│       ├── mechanism_tcp_results.csv        # Responsive TCP within-run runs (N=3)
│       └── mechanism_run_validity_audit.csv # Full validity census
├── report/                        # Written publications & reports
│   ├── dissertation_report.tex    # Master's Dissertation Report (LaTeX source)
│   ├── measurement_study_report.md# Shortened 6-part measurement study
│   ├── tables/                    # LaTeX tables dynamically generated from CSVs
│   └── figures/                   # Vector and PDF figures
└── backups/                       # Compressed archives (clean, no large pcaps)
    └── DESiRED_final_submission_20261013.tar.gz # Clean submission backup
```

---

## 2. Experimental Parameters & Reproducibility Matrix

All experiments share identical network and traffic parameters:
* **Network Topology:** 3-hop linear path ($s_1 - s_2 - s_3$) running P4 Behavioral Model v2 (BMv2).
* **Bottleneck Link:** Located at switch $s_2$ with buffer size 64 packets.
* **Control RPC:** Apache Thrift CLI on ports 9090, 9091, 9092 modifying `MyEgress.targetDelay_reg`.
* **Video Workload:** MPEG-DASH proxy serving Big Buck Bunny encoded at 200--4000 kbps to a DASH.js client (BOLA/Dynamic algorithm).
* **Competing Workload:** iperf3 transmitting 500 kbps constant-bitrate UDP cross-traffic ($h_2 \to h_4$).
* **Telemetry Probes:** 1 probe/sec injected by $h_3$ (UDP proto 253), collecting ingress/egress timestamps and queue depths across hops.
* **Duration:** Exactly 700 seconds per run ($N=27$ runs, 18,900 seconds of execution).
* **Random Seeds:**
  - NumPy: `seed(1)` (audit runs), `seed(42)` (retraining)
  - TensorFlow: `set_seed(1)` (audit runs), `set_seed(42)` (retraining)
  - Python Random: `seed(1)`

---

## 3. Running Data Validation & Metric Analysis

To re-compute all duration-weighted integrals, Student's $t$ 95\% confidence intervals, and generate publication plots from raw logs:

```bash
cd DESiRED
python3 scripts/final_analysis_v2.py
```

To validate telemetry integrity for an individual run:
```bash
python3 scripts/validate_run.py v2_fixed30k_eval_1 --expected-duration 700 --min-probes 595
```

---

## 4. Compiling the LaTeX Dissertation Report

The complete, self-contained report adhering to the M.Tech dissertation template is located in `report/`:

```bash
cd report
pdflatex dissertation_report.tex
pdflatex dissertation_report.tex
```

*(Running twice resolves all table of contents, list of figures, list of tables, and cross-references).*
