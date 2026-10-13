# Experiment Plan & Evaluation Protocol for DESiRED Testbed

## 1. Executive Summary & Research Goal
The DESiRED (Dynamic, Enhanced, and Smart iRED) testbed investigates whether In-band Network Telemetry (INT)-informed closed-loop target-delay adaptation improves Video Quality of Experience (QoE) and network utilization compared to static target-delay Active Queue Management (AQM) configurations under competing traffic loads.

This evaluation protocol defines the hypothesis, baselines, metrics, experimental controls, and statistical requirements necessary to support peer-reviewed, reproducible research publications.

## 2. Hypothesis & Core Research Questions
1. **Q1 (Static Baseline Trade-off):** Does a lower static target delay (e.g., 20 ms) reduce queue bufferbloat and network delay at the expense of video rebuffer risk, or does it achieve higher video QoE?
2. **Q2 (Pretrained RL Controller Behavior):** Does the pretrained DDQN agent demonstrate adaptive control in response to network state changes, or does it converge to a static delay regime? What role does telemetry feature normalization play in policy behavior?
3. **Q3 (Comparative Performance):** How does dynamic target-delay control (RL and rule-based heuristic) compare against static policies (Fixed 20k, Fixed 30k, Fixed 50k) across QoE, throughput, packet loss, and queue occupancy?

## 3. Evaluation Metrics & Mathematical Definitions

All time-series metrics are computed using **duration-weighted integrals** (elapsed time between timestamps) rather than raw sample row indices, ensuring robustness against simulator sampling jitter.

### 3.1 Video QoE Metrics
For a run with $N$ DASH telemetry entries $(t_i, \text{FPS}_i, B_i, R_i)$ spanning total duration $T = t_N - t_1$:
Let $\Delta t_i = t_{i+1} - t_i$.

1. **Duration-Weighted Mean FPS ($\overline{\text{FPS}}$):**
   $$\overline{\text{FPS}} = \frac{1}{T} \sum_{i=1}^{N-1} \text{FPS}_i \cdot \Delta t_i$$
2. **Median FPS:** 50th percentile of duration-weighted playback frame rate.
3. **High-Quality Availability ($F_{30}$):** Fraction of elapsed session time at 30 FPS:
   $$F_{30} = \frac{1}{T} \sum_{i=1}^{N-1} \mathbb{I}(\text{FPS}_i = 30) \cdot \Delta t_i$$
4. **Stall / Rebuffer Fraction ($F_{0}$):** Fraction of elapsed session time in rebuffer state ($\text{FPS} = 0$):
   $$F_{0} = \frac{1}{T} \sum_{i=1}^{N-1} \mathbb{I}(\text{FPS}_i = 0) \cdot \Delta t_i$$
5. **Mean Video Buffer ($\overline{B}$):**
   $$\overline{B} = \frac{1}{T} \sum_{i=1}^{N-1} B_i \cdot \Delta t_i$$
6. **Low-Buffer Risk Fraction ($F_{B < 3\text{s}}$):** Fraction of elapsed session time where buffer $B < 3.0$ seconds (near stall).
7. **Duration-Weighted Mean Bitrate ($\overline{R}$):**
   $$\overline{R} = \frac{1}{T} \sum_{i=1}^{N-1} R_i \cdot \Delta t_i \quad (\text{kbps})$$

### 3.2 Network Performance Metrics
From the iperf3 UDP receiver report at host `h4`:
1. **Delivered Bitrate ($R_{\text{iperf}}$):** Mean received UDP throughput in kbits/sec.
2. **Datagram Loss Percentage ($L_{\text{UDP}}$):**
   $$L_{\text{UDP}} = \frac{\text{Lost Datagrams}}{\text{Total Sent Datagrams}} \times 100\%$$
3. **Receiver Jitter ($J$):** Mean delay variation reported by receiver (ms).

### 3.3 In-Band Network Telemetry (INT) Metrics
Extracted per-hop from 32-byte INT headers:
1. **Per-Hop Queue Occupancy:** Median and 95th percentile dequeue and enqueue queue depths ($q_1, q_2, q_3$).
2. **Per-Hop Dequeue Timedelta:** Queue latency per switch hop ($\mu\text{s}$).
3. **End-to-End Hop Delay:** Total transit latency across $s_1 \to s_2 \to s_3$.

### 3.4 Controller Dynamics & Policy Integrity
1. **Action Distribution:** Proportion of actions selected ($a \in \{0: \text{Increase}, 1: \text{Decrease}, 2: \text{Hold}\}$).
2. **Target Delay Trajectory:** Initial, final, and time-weighted average target delay ($\mu\text{s}$) across switches $s_1, s_2, s_3$.
3. **Convergence Time:** Elapsed seconds to reach steady-state target delay.
4. **Telemetry Integrity:** Ratio of received INT probes to expected probes ($\ge 85\%$), DASH duration ($\ge 670$s), and max sampling gap ($\le 8.5$s).

## 4. Experimental Matrix & Conditions

All runs share identical physical and emulated network parameters:
- **Topology:** 3 BMv2 switches ($s_1 - s_2 - s_3$) with pinned Thrift ports (9090, 9091, 9092).
- **Traffic Path:**
  - Video stream (DASH proxy): $h_1 \to h_2$
  - INT probes: $h_3 \to h_4$ (1 probe/s, Scapy proto 253)
  - Competing UDP load: $h_2 \to h_4$ at 500 kbps (iperf3)
- **Duration:** 700 seconds per run.
- **Replications:** 5 independent runs per condition.

| Condition | Policy Description | Initial Target Delay ($\mu\text{s}$) | Controller Status | Target Replications |
| :--- | :--- | :--- | :--- | :--- |
| **Fixed-20k** | Static strict AQM | 20,000 | Disabled | 5 runs (`fixed20k_load_1`..`5`) |
| **Fixed-50k** | Static loose AQM | 50,000 | Disabled | 5 runs (`fixed50k_load_1`..`5`) |
| **Fixed-30k** | Static intermediate AQM | 30,000 | Disabled | 5 runs (`fixed30k_load_1`..`5`) |
| **RL-Inference** | Pretrained DDQN agent | 50,000 | Enabled | 5 runs (`infer_socket_load_4`..`8`) |
| **Rule-Based** | Threshold heuristic | 50,000 | Enabled | 5 runs (`rule_load_1`..`5`) |

## 5. Statistical Rigor
For all metrics, we report:
$$\text{Mean} \pm \text{Standard Deviation}, \quad 95\% \text{ Confidence Interval} = \overline{x} \pm t_{n-1, 0.975} \frac{s}{\sqrt{n}}$$
For $n = 5$ repetitions, $t_{4, 0.975} \approx 2.776$.
No cherry-picked runs are used. All aggregated runs must pass `scripts/validate_run.py`.
