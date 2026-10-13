# DESiRED — Final Evaluation Results (Campaign v2)

*27 runs across 6 policies. All metrics duration-weighted. 95% CI using Student's t.*


## 1. Per-Run Metrics

| Run ID | Policy | FPS | 30fps% | Stall% | Buf(s) | Loss% | Jitter(ms) | INT probes |
|--------|--------|-----|--------|--------|--------|-------|-----------|------------|
| `v2_fixed20k_eval_1` | Fixed-20k | 30.0 | 100.0 | 0.00 | 59.5 | 0.00 | 6.8 | 700 |
| `v2_fixed20k_eval_2` | Fixed-20k | 29.8 | 96.9 | 0.02 | 59.2 | 2.60 | 1.2 | 700 |
| `v2_fixed20k_eval_3` | Fixed-20k | 30.0 | 100.0 | 0.00 | 61.7 | 0.00 | 8.0 | 700 |
| `v2_fixed20k_eval_4` | Fixed-20k | 30.0 | 100.0 | 0.00 | 57.3 | 0.00 | 5.7 | 700 |
| `v2_fixed30k_eval_1` | Fixed-30k | 30.0 | 100.0 | 0.00 | 60.3 | 0.00 | 51.8 | 700 |
| `v2_fixed30k_eval_2` | Fixed-30k | 30.0 | 100.0 | 0.00 | 60.0 | 0.00 | 5.3 | 700 |
| `v2_fixed30k_eval_3` | Fixed-30k | 30.0 | 100.0 | 0.00 | 50.1 | 0.00 | 5.7 | 700 |
| `v2_fixed40k_eval_1` | Fixed-40k | 29.9 | 98.8 | 0.00 | 56.3 | 0.00 | 4.7 | 700 |
| `v2_fixed40k_eval_2` | Fixed-40k | 30.0 | 99.6 | 0.00 | 55.0 | 0.80 | 20.2 | 700 |
| `v2_fixed40k_eval_3` | Fixed-40k | 16.7 | 24.5 | 31.18 | 6.1 | 0.00 | 17.8 | 700 |
| `v2_fixed40k_eval_4` | Fixed-40k | 29.8 | 97.9 | 0.24 | 60.7 | 0.00 | 2.4 | 700 |
| `v2_fixed50k_eval_1` | Fixed-50k | 22.2 | 46.4 | 15.01 | 15.5 | 0.00 | 22.3 | 700 |
| `v2_fixed50k_eval_2` | Fixed-50k | 12.2 | 12.1 | 45.79 | 4.7 | 0.00 | 6.1 | 700 |
| `v2_fixed50k_eval_3` | Fixed-50k | 19.2 | 29.5 | 21.69 | 7.8 | 0.00 | 16.5 | 700 |
| `v2_fixed50k_eval_4` | Fixed-50k | 30.0 | 100.0 | 0.00 | 62.4 | 0.91 | 1.5 | 700 |
| `v2_fixed50k_eval_5` | Fixed-50k | 30.0 | 100.0 | 0.00 | 62.1 | 0.00 | 0.7 | 700 |
| `v2_infer_eval_1` | RL-DDQN | 25.8 | 78.9 | 10.39 | 44.4 | 1.40 | 11.5 | 700 |
| `v2_infer_eval_2` | RL-DDQN | 24.4 | 58.5 | 9.88 | 21.3 | 0.00 | 6.5 | 700 |
| `v2_infer_eval_3` | RL-DDQN | 21.6 | 53.1 | 20.14 | 17.7 | 0.17 | 15.5 | 700 |
| `v2_infer_eval_4` | RL-DDQN | 28.9 | 88.1 | 0.99 | 49.8 | 0.73 | 4.3 | 700 |
| `v2_infer_eval_5` | RL-DDQN | 28.0 | 87.2 | 4.61 | 34.8 | 0.48 | 9.6 | 700 |
| `v2_infer_eval_6` | RL-DDQN | 30.0 | 100.0 | 0.00 | 62.7 | 2.80 | 8.3 | 700 |
| `v2_rule_eval_1` | Rule-Based | 23.2 | 65.4 | 16.86 | 40.7 | 4.00 | 4.1 | 700 |
| `v2_rule_eval_2` | Rule-Based | 30.0 | 100.0 | 0.00 | 61.4 | 0.00 | 8.0 | 700 |
| `v2_rule_eval_3` | Rule-Based | 30.0 | 100.0 | 0.00 | 63.0 | 0.00 | 2.4 | 700 |
| `v2_rule_eval_4` | Rule-Based | 30.0 | 100.0 | 0.00 | 62.9 | 15.00 | 1.0 | 700 |
| `v2_rule_eval_5` | Rule-Based | 30.0 | 100.0 | 0.00 | 62.5 | 9.00 | 1.3 | 700 |

## 2. Policy Statistics (Mean ± SD, 95% CI)

| Policy | N | Mean FPS | 30fps% | Stall% | Mean Buf (s) | Loss% | Jitter (ms) | E2E Delay (µs) |
|--------|---|----------|--------|--------|-------------|-------|-------------|----------------|
| **Fixed-20k** | 4 | 29.95 ± 0.11 [CI±0.17] | 99.22 ± 1.57 [CI±2.50] | 0.01 ± 0.01 [CI±0.02] | 59.43 ± 1.79 [CI±2.86] | 0.65 ± 1.30 [CI±2.07] | 5.43 ± 2.95 [CI±4.69] | 0.69 ± 0.12 [CI±0.20] |
| **Fixed-30k** | 3 | 30.00 ± 0.00 [CI±0.00] | 100.00 ± 0.00 [CI±0.00] | 0.00 ± 0.00 [CI±0.00] | 56.82 ± 5.84 [CI±14.50] | 0.00 ± 0.00 [CI±0.00] | 20.93 ± 26.71 [CI±66.37] | 0.55 ± 0.11 [CI±0.27] |
| **Fixed-40k** | 4 | 26.60 ± 6.60 [CI±10.50] | 80.20 ± 37.14 [CI±59.09] | 7.86 ± 15.55 [CI±24.74] | 44.51 ± 25.75 [CI±40.97] | 0.20 ± 0.40 [CI±0.64] | 11.30 ± 9.04 [CI±14.38] | 0.50 ± 0.12 [CI±0.19] |
| **Fixed-50k** | 5 | 22.72 ± 7.58 [CI±9.40] | 57.59 ± 40.57 [CI±50.37] | 16.50 ± 18.92 [CI±23.48] | 30.48 ± 29.25 [CI±36.31] | 0.18 ± 0.41 [CI±0.51] | 9.43 ± 9.57 [CI±11.88] | 0.48 ± 0.18 [CI±0.23] |
| **Rule-Based** | 5 | 28.64 ± 3.03 [CI±3.76] | 93.08 ± 15.48 [CI±19.21] | 3.37 ± 7.54 [CI±9.36] | 58.08 ± 9.76 [CI±12.12] | 5.60 ± 6.43 [CI±7.98] | 3.36 ± 2.90 [CI±3.60] | 0.78 ± 0.51 [CI±0.64] |
| **RL-DDQN** | 6 | 26.47 ± 3.14 [CI±3.29] | 77.66 ± 18.27 [CI±19.18] | 7.67 ± 7.49 [CI±7.86] | 38.46 ± 17.24 [CI±18.10] | 0.93 ± 1.04 [CI±1.09] | 9.29 ± 3.92 [CI±4.12] | 0.70 ± 0.20 [CI±0.21] |

## 3. Key Findings

- **Highest mean FPS:** Fixed-30k — 30.00 ± 0.00 [CI±0.00]
- **Best 30-FPS availability:** Fixed-30k — 100.00 ± 0.00 [CI±0.00]
- **Highest mean video buffer:** Fixed-20k — 59.43 ± 1.79 [CI±2.86] s
- **Lowest stall ratio:** Fixed-30k — 0.00 ± 0.00 [CI±0.00]
- **Lowest UDP packet loss:** Fixed-30k — 0.00 ± 0.00 [CI±0.00]

### RL-DDQN vs. Fixed-50k (same initial delay)
- FPS improvement: **+3.7** fps
- 30-FPS availability gain: **+20.1%**
- Stall ratio reduction: **+8.8%**

### RL-DDQN vs. Fixed-20k (strictest static)
- FPS difference: **-3.5** fps
- 30-FPS availability difference: **-21.6%**

### Rule-Based vs. Fixed-50k
- FPS improvement: **+5.9** fps
- 30-FPS availability gain: **+35.5%**

## 4. Controller Dynamics (RL & Rule Runs)

| Run ID | Policy | Actions | ↑Inc | ↓Dec | →Hold | Initial Delay | Final Delay |
|--------|--------|---------|------|------|-------|-------------|-------------|
| `v2_infer_eval_1` | RL-DDQN | 75 | 0 | 75 | 0 | 50000 µs | 20000 µs |
| `v2_infer_eval_2` | RL-DDQN | 70 | 0 | 70 | 0 | 50000 µs | 20000 µs |
| `v2_infer_eval_3` | RL-DDQN | 60 | 0 | 60 | 0 | 50000 µs | 20000 µs |
| `v2_infer_eval_4` | RL-DDQN | 102 | 0 | 102 | 0 | 50000 µs | 20000 µs |
| `v2_infer_eval_5` | RL-DDQN | 65 | 0 | 65 | 0 | 50000 µs | 20000 µs |
| `v2_infer_eval_6` | RL-DDQN | 67 | 0 | 67 | 0 | 50000 µs | 20000 µs |
| `v2_rule_eval_1` | Rule-Based | 157 | 77 | 0 | 80 | 50000 µs | 70000 µs |
| `v2_rule_eval_2` | Rule-Based | 166 | 131 | 0 | 35 | 50000 µs | 70000 µs |
| `v2_rule_eval_3` | Rule-Based | 171 | 156 | 0 | 15 | 50000 µs | 70000 µs |
| `v2_rule_eval_4` | Rule-Based | 157 | 126 | 0 | 31 | 50000 µs | 70000 µs |
| `v2_rule_eval_5` | Rule-Based | 159 | 130 | 0 | 29 | 50000 µs | 70000 µs |

## 5. Generated Figures

| Filename | Description |
|----------|-------------|
| `figs/v2_qoe_fps.png` | Mean FPS & 30-FPS availability per policy |
| `figs/v2_buffer_stall.png` | Buffer level & stall rate per policy |
| `figs/v2_network.png` | UDP loss & jitter under competing load |
| `figs/v2_delay_trajectory.png` | Controller target-delay over time (RL & Rule) |
| `figs/v2_int_queue.png` | INT queue depth (p95) per switch hop |
