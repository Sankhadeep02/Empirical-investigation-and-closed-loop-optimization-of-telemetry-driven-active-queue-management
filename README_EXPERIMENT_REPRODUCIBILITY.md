# DESiRED Experiment Reproducibility Guide

## 1. Overview
This repository contains the complete experimental testbed, evaluation harnesses, raw logs, analysis pipelines, and LaTeX report for the empirical audit and evaluation of **DESiRED (Dynamic, Enhanced, and Smart iRED)**:
- **Baseline Git Commit:** `8f92867f0bbe56610a503cf11b4f93f68ff56302`
- **Environment:** Ubuntu Linux x86_64, Mininet 2.3.0, BMv2 (`simple_switch`), Python 3.12 (`~/src/p4dev-python-venv`), TensorFlow 2.16 (CPU inference).
- **Topology:** 3-hop linear path ($h_1/h_3 \to s_1 \to s_2 \to s_3 \to h_2/h_4$) with P4-16 match-action tables compiled for BMv2 with Thrift RPC pinned to ports 9090, 9091, 9092.

---

## 2. Dataset & Registry Census
Across all testbed executions in Campaign v2, **104 total runs** were logged into `results/campaign_v2/experiment_registry.csv` with zero deleted or overwritten entries:
- **81 VALID runs:** Passed duration ($\ge 695$\,s), $\ge 85\%$ INT telemetry ratio, DASH sampling gap threshold ($\le 8.5$\,s), and graceful process shutdown.
- **23 INVALID/RETRIED runs:** Formally documented with failure causes (transient CPU contention DASH gaps, startup/teardown races). All invalid slots during automated batches were retried with explicit suffix (`_retry1`) and validated.

### Key Data Files
- `results/campaign_v2/experiment_registry.csv`: Master audit log with git commits, seeds, parameters, and validity status.
- `results/campaign_v2/summary_fixed_sweep.csv`: Balanced $3 \times 5$ multi-load sweep (200, 500, 1000 kbps across 20k, 30k, 40k, 50k, 70k) with means, standard deviations, and 95% confidence intervals.
- `results/campaign_v2/summary_control_batch.csv`: Control batch comparing Batch 1 vs Batch 2 at 500 kbps to quantify host machine-state and temporal drift.
- `results/campaign_v2/summary_dynamic_schedule.csv`: Dynamic changing-load schedule ($200 \to 1000 \to 500$\,kbps) partitioning startup transient ($t \le 60$\,s) from steady-state ($t > 60$\,s).
- `results/campaign_v2/statistical_tests.csv`: Welch's $t$-test, Mann--Whitney $U$ test, Cohen's $d$, and Benjamini--Hochberg FDR-adjusted $p$-values.
- `results/campaign_v2/complete_validity_audit.csv`: Complete census of all 104 executions.

---

## 3. How to Re-Run Experiments

### A. Start the Topology
In a dedicated root terminal:
```bash
sudo -n ~/src/p4dev-python-venv/bin/python3 testbed/topology.py
```

### B. Execute a Single Run
```bash
python3 scripts/run_experiment.py \
  --run-id my_eval_run_1 \
  --policy fixed30k \
  --duration 700 \
  --load-kbps 500
```
Supported policies:
- `fixed20k`, `fixed30k`, `fixed40k`, `fixed50k`, `fixed70k`: Static P4 target delay thresholds.
- `rule`: Transparent rule-based heuristic controller.
- `infer`: Base DDQN controller starting from default 50\,ms delay.
- `infer20k`: Base DDQN controller starting directly at the 20\,ms floor.

### C. Run the Dynamic Changing-Load Schedule
```bash
python3 scripts/run_experiment.py \
  --run-id my_dyn_eval_1 \
  --policy infer20k \
  --duration 700 \
  --load-schedule "200:233,1000:233,500:234"
```

### D. Validate Any Run
```bash
python3 scripts/validate_run.py my_eval_run_1 --duration 700
```

---

## 4. Recomputing All Figures and Tables
To recompute every table, figure, and summary CSV directly from raw logs with zero hand-edited numbers:
```bash
python3 scripts/generate_all_paper_artifacts.py
```
Generated artifacts:
- **Vector PDF Figures:** `report/figures/`
  - `fig_qoe_vs_delay_by_load.pdf`
  - `fig_qoe_vs_udp_loss.pdf`
  - `fig_target_delay_trajectories.pdf`
  - `fig_action_distributions.pdf`
  - `fig_dynamic_schedule_timeseries.pdf`
  - `fig_buffer_distributions.pdf`
- **LaTeX Tables:** `report/tables/`
  - `tab_sweep_per_load.tex`
  - `tab_control_batch.tex`
  - `tab_dynamic_changing_load.tex`
  - `tab_run_validity.tex`
  - `tab_statistical_tests.tex`

### Validate LaTeX Document Integrity
```bash
python3 scripts/check_latex.py report/dissertation_report.tex
```
Verifies environment balancing, label/ref matching, citations, and graphics existence for compilation on Overleaf.
