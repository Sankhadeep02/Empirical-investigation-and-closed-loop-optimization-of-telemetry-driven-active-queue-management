# DESiRED Evaluation Results

*Generated automatically from 5 experiment runs.*

> All metrics are duration-weighted integrals (see experiment_plan.md §3).


## 1. Per-Run Raw Summary

| Run ID | Policy | Mean FPS | 30-FPS% | Stall% | Buf(s) | Loss% | Jitter(ms) | INT probes |
|--------|--------|----------|---------|--------|--------|-------|-----------|------------|
| infer_socket_load_4 | RL-DDQN | 25.0 | 58.9 | 6.48 | 21.5 | 0.00 | 113.0 | 627 |
| fixed20k_load_1 | Fixed-20k | 24.9 | 47.8 | 3.71 | 16.3 | 0.15 | 2.3 | 700 |
| fixed20k_load_2 | Fixed-20k | 4.7 | 0.0 | 75.69 | 0.6 | 0.00 | 15.4 | 596 |
| fixed20k_load_3 | Fixed-20k | 4.2 | 0.2 | 78.80 | 0.5 | 0.00 | 5.5 | 554 |
| fixed20k_load_5 | Fixed-20k | 4.3 | 0.1 | 77.84 | 0.5 | 0.00 | 28.7 | 587 |

## 2. Policy Aggregate Statistics (Mean ± SD, 95% CI)

| Policy | N | Mean FPS | 30-FPS% | Stall% | Mean Buf (s) | Loss% | Jitter (ms) |
|--------|---|----------|---------|--------|-------------|-------|-------------|
| **Fixed-20k** | 4 | 9.53 ± 10.28 (95% CI ±16.35) | 12.04 ± 23.86 (95% CI ±37.96) | 59.01 ± 36.89 (95% CI ±58.69) | 4.48 ± 7.89 (95% CI ±12.55) | 0.04 ± 0.07 (95% CI ±0.12) | 12.98 ± 11.90 (95% CI ±18.94) |
| **RL-DDQN** | 1 | 25.02 | 58.88 | 6.48 | 21.52 | 0.00 | 113.00 |

## 3. Key Findings

- **Highest mean FPS:** RL-DDQN (25.02)
- **Best 30-FPS availability:** RL-DDQN (58.88)
- **Highest mean video buffer:** RL-DDQN (21.52 s)
- **Lowest UDP loss:** RL-DDQN (0.00%)
- **Lowest rebuffer ratio:** RL-DDQN (6.48%)

## 4. Controller Dynamics (RL & Rule-Based Runs)

| Run ID | Policy | Actions | ↑ Inc | ↓ Dec | → Hold | Init Delay | Final Delay |
|--------|--------|---------|-------|-------|--------|-----------|------------|
| infer_socket_load_4 | RL-DDQN | 65 | 0 | 65 | 0 | 50000 µs | 20000 µs |

## 5. Figures

| Figure | Description |
|--------|-------------|
| `figs/qoe_comparison.png` | Mean FPS & 30-FPS availability per policy |
| `figs/buffer_dynamics.png` | Mean buffer level & stall rate per policy |
| `figs/network_performance.png` | UDP loss & jitter per policy |
| `figs/target_delay_trajectory.png` | Target delay over time for RL/rule runs |
