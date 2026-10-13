# Empirical Measurement and Mechanism Study of In-Network AQM Delay Control in P4

## 1. Motivation and System Design

Programmable data planes enable in-network Active Queue Management (AQM) where switches monitor queuing latency in real time and drop or mark packets based on a programmable target delay register (`targetDelay_reg`). Earlier experimental campaigns (v1–v3) evaluated Deep Reinforcement Learning (RL) and rule-based controllers designed to dynamically adapt this target delay to optimize video Quality of Experience (QoE).

However, those evaluations produced an unresolved puzzle: fixed target delays (e.g., 20 ms vs. 30 ms vs. 50 ms) showed indistinguishable video QoE across stationary workloads, and RL controllers frequently collapsed into near-identical static configurations. 

This study investigates the root cause of that finding. Through systematic instrumentation, we show that:
1. The physical dataplane control loop in earlier campaigns was completely open: egress mirroring sessions required to trigger the packet drop pipeline were never configured in the software switch runtime.
2. Once the drop path is enabled, target delay controls AQM drop probability reversibly and reliably, but its ability to control queue delay depends fundamentally on traffic responsiveness: under non-responsive UDP cross-traffic, target delay changes loss rates without reducing queue delay; whereas under responsive TCP traffic, target delay directly controls both physical queue delay and loss rates.
3. No claim is made that an adaptive controller improves video QoE over an optimal fixed delay. Instead, this study establishes the necessary dataplane and transport prerequisites under which adaptive delay control can function.

---

## 2. Testbed & Configuration Evolution Across Campaigns

All experiments were executed on a virtualized Mininet testbed comprising three P4 software switches (`simple_switch` / BMv2) running the `src/dataplane/DESiRED.p4` pipeline with In-band Network Telemetry (INT) headers (32 bytes per hop) and Linux network namespaces (`h1` through `h4`).

Table \ref{tab:campaign_evolution} summarizes the configuration evolution across the four campaigns:

| Campaign | Link Rate Limit | Queue Depth | Mirror Session 2 | Telemetry / Probing | Traffic Type | Status \& Role in Paper |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **v1 (Baseline)** | None (Unshaped) | 64 pkts | Unconfigured (`SESSION_NOT_FOUND`) | Video receiver logs only | 1 Hz ICMP pings + unpaced UDP | **Open-Loop Control:** Uncongested links, zero AQM drops. |
| **v2 (Sweep)** | None (Unshaped) | 64 pkts | Unconfigured (`SESSION_NOT_FOUND`) | Host ping + receiver logs | 1 Hz ICMP pings + unpaced UDP | **Open-Loop Control:** Host contention created ping spikes, but switch queues remained empty. |
| **v3 (Overload)** | 200 pps (Shaped) | 32 pkts | Unconfigured (`SESSION_NOT_FOUND`) | INT probes (1 Hz) | 1 Hz ICMP pings + unpaced UDP | **Open-Loop / Tail-Drop Only:** Link congested, but all drops were buffer tail-drops. |
| **v4 (Mechanism)** | 200 pps (Shaped) | 32 pkts | **Configured (`mirroring_add 2 2`)** | INT probes (1 Hz) + Switch HW Counters | Unpaced UDP \& TCP Cubic | **Closed-Loop Dataplane:** First verified engagement of P4 clone-and-drop pipeline. |

---

## 3. Dataplane Defect Discovery & Verification of the Fix

### 3.1 The Missing Mirror Session Defect
In `src/dataplane/DESiRED.p4`, the AQM drop mechanism relies on a two-stage clone-and-recirculate pipeline:
1. In `MyEgress`, if queuing delay exceeds `targetDelay_reg`, the switch calls:
   ```p4
   clone_preserving_field_list(CloneType.E2E, 2, 0);
   ```
2. The cloned packet recirculates to `MyIngress`, where it is matched on `BMV2_V1MODEL_INSTANCE_TYPE_RECIRC`, writes `flagtoDrop_reg[port] = 1`, and drops itself via `drop_recirc()`.
3. The subsequent regular packet entering `MyIngress` reads `flagtoDrop_reg == 1` and is dropped via `drop_regular()`.

In Campaigns v1–v3, runtime mirror session `2` was never configured in BMv2 (`SESSION_NOT_FOUND`). Consequently, no cloned packets were ever generated, the recirculated drop action never executed, `flagtoDrop_reg` remained 0, and the AQM never dropped a single packet. Every dropped packet recorded prior to Campaign v4 was a queue buffer overflow tail-drop.

### 3.2 Dataplane Fix & Leak Verification Under Congestion
Adding `mirroring_add 2 2` to `testbed/populate_tables.sh` activates the mirroring engine. To verify that clones do not leak to downstream hosts, we ran overloaded UDP cross-traffic ($1800\text{ kbps}$) with target delay set to 20 ms, capturing all packets on $h_4\text{-eth0}$ with `tcpdump` and analyzing packet streams with `tshark`:
- **Switch 2 Port 2 Forwarded:** 1,346 pkts
- **Switch 2 RED AQM Drops:** 160 pkts
- **Switch 2 Clones Generated:** 773 pkts
- **Switch 2 Recirculated Packets:** 757 pkts
- **Switch 2 Recirculated Drops:** 757 pkts (100% dropped internally by `drop_recirc`)
- **Packets Captured at $h_4$:** 819 pkts
- **Duplicate Packets at $h_4$:** 0
- **Leaked Clones at $h_4$:** 0

All clones are completely contained within the switch pipeline.

### 3.3 Bottleneck Capacity & Delay Ceiling Calibration
Under BMv2, configuring `set_queue_rate 200 2` yields an effective empirical saturation service rate of:
$$\mu = 153.29\text{ pkts/sec} \quad (1.803\text{ Mbps})$$
due to user-space thread scheduling overhead. For a maximum queue depth of 32 packets, the true physical buffer drain ceiling is:
$$D_{\max} = \frac{32\text{ pkts}}{153.29\text{ pps}} = \mathbf{208.75\text{ ms}}$$
This empirical measurement directly explains why queue delay EWMA reaches 190–213 ms under saturation: the queue buffer drains in 209 ms. Telemetry readings above 210 ms are inconsistent with the measured ceiling and represent host scheduling latency or delayed probe artifacts rather than physical queue residence.

---

## 4. Mechanism Validation Results

We conducted within-run mechanism tests using a fixed three-segment schedule:
- **Warmup (0–30s):** Target = 20k $\mu$s
- **Segment A (30–70s, 40s duration):** Target = 20k $\mu$s
- **Segment B (72–112s, 40s duration):** Target = 70k $\mu$s
- **Segment C (114–154s, 40s duration):** Target = 20k $\mu$s (reversibility check)

### 4.1 Non-Responsive UDP Traffic

A total of 9 formal runs ($N=3$ repeats across 3 loads: 1150 kbps, 1320 kbps, 1485 kbps) were executed.

#### Validity Audit & Exclusion Analysis
The pre-registered acceptance criterion required segment traffic totals ($T = \text{fwd} + \text{drp}$) to match within $\le 5\%$ ($\text{dev}_B \le 5\%$, $\text{dev}_C \le 5\%$) with median delay $\le 210\text{ ms}$.
- **Strict 5% Rule (Pre-Registered):** Only 1 run (`mech_1150k_rep1`) passed all criteria ($\text{dev}_B = 0.8\%, \text{dev}_C = 3.8\%$).
- **Relaxed 10% Rule (Post-Hoc):** When relaxing the balance threshold to 10% post hoc after inspecting the data, three additional runs passed: `mech_1150k_rep2` ($\text{dev}_B = 8.6\%, \text{dev}_C = 0.1\%$), `mech_1150k_rep3` ($\text{dev}_B = 5.9\%, \text{dev}_C = 4.2\%$), and `mech_1320k_rep2` ($\text{dev}_B = 9.7\%, \text{dev}_C = 8.6\%$).
- **Excluded Runs (5 runs):**
  - `mech_1320k_rep1`: Excluded due to process collision starving Segment C (47 pkts, 98.9% imbalance).
  - `mech_1320k_rep3`: Excluded due to telemetry artifact ($912.2\text{ ms} > 210\text{ ms}$) and severe imbalance ($\text{dev}_B = 88.1\%$).
  - `mech_1485k_rep1-3`: All three runs at 1485 kbps were excluded due to severe segment imbalance ($\text{dev}_B = 12.2\%\text{--}38.4\%$).

#### High-Load Tail-Drop Congestion Audit
Investigation of iperf logs for `mech_1485k_rep1` revealed that the apparent "imbalance" at high load was caused by **queue tail-drops, not a test runner defect**:
- In `mech_1485k_rep1`, iperf sent 37,884 packets and the receiver recorded 7,690 lost packets (20.3% loss).
- Switch 2 recorded only 1,019 AQM drops across all segments.
- The remaining **6,671 lost packets (86.7% of all losses)** were queue tail-drops that overflowed switch buffers prior to egress AQM processing. Note that this tail-drop calculation was explicitly checked on `mech_1485k_rep1` only (reps 2 and 3 were not evaluated for tail-drop decomposition). Consequently, the valid UDP mechanism data cover strictly the low (1150 kbps) and medium (1320 kbps) load regimes where tail-drops do not dominate.

#### Drop Control vs. Delay (Valid UDP Runs, $N=4$ total; 1 strict, 3 relaxed)

| Run ID | Load (kbps) | Balance Rule | Seg A Drops (20k) | Seg B Drops (70k) | Seg C Drops (20k) | Drop Change $\Delta(B - A)$ | Seg A Delay | Seg B Delay | Seg C Delay |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **mech_1150k_rep1** | 1150 | Strict 5% | 182 | 11 | 215 | **-171 (-94.0%)** | 9.23 ms | 7.97 ms | 7.86 ms |
| **mech_1150k_rep3** | 1150 | Relaxed 10% | 221 | 21 | 208 | **-200 (-90.5%)** | 9.42 ms | 7.47 ms | 8.74 ms |
| **mech_1320k_rep2** | 1320 | Relaxed 10% | 366 | 67 | 577 | **-299 (-81.7%)** | 17.86 ms | 10.01 ms | 37.01 ms |
| **mech_1150k_rep2** | 1150 | Relaxed 10% | 39 | 52 | 68 | +13 (+33.3%) | 0.64 ms | 1.75 ms | 1.35 ms |

**UDP Findings:**
1. **Drop Counts Follow Target:** In three of the four valid runs, relaxing target delay from 20k to 70k reduced AQM drops by **81.7% to 94.0%**. Returning to 20k in Segment C rebounded drops by $8.6\times\text{ to }19.5\times$.
2. **Low-Load Exception:** In `mech_1150k_rep2`, queue delay remained near empty (0.6–1.8 ms) and drops were low ($39 \to 52 \to 68$), demonstrating that the AQM drop path was barely engaged under light traffic.
3. **Queue Delay Shows No Effect in Expected Direction:** Rather than decreasing at tighter target delay, queue delay showed no systematic reduction in the expected direction: at 1150k, delays remained flat (7.5–9.4 ms); at 1320k, delay was lower at 70k (10.0 ms vs. 17.9 ms). Furthermore, delay reversibility did not hold: in `mech_1320k_rep2`, Segment C's delay (37.0 ms) did not return to Segment A's level (17.9 ms). Under non-responsive UDP, packet arrivals never throttle, so tighter target delay creates loss without lowering queue residence time.

---

### 4.2 Responsive TCP Traffic ($N=3$ repeats at single load)

To evaluate whether source backoff allows target delay to control queue delay, we evaluated a responsive TCP Cubic flow under the identical within-run protocol ($N=3$ repeats).

#### Complete TCP Results Table

| Rep | Seg A (20k) Q-Delay | Seg B (70k) Q-Delay | Seg C (20k) Q-Delay | Delay Delta $\Delta(B - A)$ | Seg A AQM Drops | Seg B AQM Drops | Seg C AQM Drops | Drop Delta $\Delta(B - A)$ |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **1** | 10.08 ms (IQR 14.1) | 28.44 ms (IQR 30.8) | 8.32 ms (IQR 14.7) | **+18.36 ms** | 266 | 94 | 233 | **-172 (-64.7%)** |
| **2** | 7.98 ms (IQR 13.4) | 28.17 ms (IQR 43.7) | 6.47 ms (IQR 10.2) | **+20.18 ms** | 204 | 100 | 252 | **-104 (-51.0%)** |
| **3** | 8.94 ms (IQR 17.7) | 29.43 ms (IQR 40.0) | 8.97 ms (IQR 12.6) | **+20.49 ms** | 274 | 105 | 221 | **-169 (-61.7%)** |

#### Packet-Rate Bottleneck & TCP Offloading Characterization
The TCP flow achieved an average throughput of 9.6 Mbps at 20k and 13.3 Mbps at 70k, which exceeds the 1.8 Mbps bitrate observed during the 153 pps UDP saturation test. 
- Dividing the transferred bytes by the forwarded packet count reveals an average packet size of **8,800 to 9,600 bytes** ($\approx 9\text{ KB}$).
- Inspection via `ethtool -k` confirmed that TCP Segmentation Offload (`tcp-segmentation-offload: on`) is active on the Linux veth interfaces.
- The switch queue enforces a **packet-rate bottleneck** (200 pps), not a byte-rate bottleneck. BMv2 forwarded 127–140 packets/sec at 20k and 179–183 packets/sec at 70k, closely adhering to the calibrated packet-rate ceiling. 
- Consequently, TCP bitrates are not directly comparable to the 1470-byte UDP capacity, though the queue delay and drop dynamics remain fully valid because queue occupancy is bounded in packets (32 packets).

#### The Complete TCP Trade-Off Curve (Latency vs. Throughput & Loss)

| Metric | Segment A (Target = 20k) | Segment B (Target = 70k) | Segment C (Target = 20k) | Delta $\Delta(B - A)$ | Relative Shift |
|---|:---:|:---:|:---:|:---:|:---:|
| **Queue Delay (Median)** | **9.00 ms** | **28.68 ms** | **7.92 ms** | **+19.68 ms** | **+218.7%** |
| **AQM Drops (Count)** | **248.0 pkts** | **99.7 pkts** | **235.3 pkts** | **-148.3 pkts** | **-59.8%** |
| **TCP Retransmissions** | **250.7 pkts** | **98.0 pkts** | **234.3 pkts** | **-152.7 pkts** | **-60.9%** |
| **Congestion Window (CWND)** | **55.4 KB** | **132.0 KB** | **55.4 KB** | **+76.6 KB** | **+138.3%** |
| **TCP Goodput** | **9.60 Mbps** | **13.32 Mbps** | **9.39 Mbps** | **+3.72 Mbps** | **+38.8%** |

**TCP Findings:**
1. **Target Delay Controls Queue Delay Reversibly:** In all 3 repeats ($N=3$), relaxing the target from 20k to 70k increased queue delay by $+18.4\text{ to }+20.5\text{ ms}$ (mean $+19.68\text{ ms}$, zero sign flips). Returning to 20k in Segment C restored queue delay immediately to 6.5–9.0 ms.
2. **Empirical CWND Scaling:** Socket telemetry confirms that tighter target delay (20k) signals loss, throttling median CWND to 55.4 KB and holding the queue drained. Relaxing target delay (70k) reduces retransmissions by 61%, allowing CWND to expand to 132 KB, filling the queue.
3. **The Trade-Off Cost:** Holding target delay at 20k reduces queuing delay by $\approx 68\%$, but incurs a **38.8% goodput penalty** and a **$2.5\times$ increase in retransmissions**.

---

## 5. Re-Evaluating the Earlier RL Negative Results

These findings explain why earlier RL controllers (Campaigns v1–v3) failed to demonstrate an advantage over fixed target delays:
1. **The Physical Loop Was Open:** Because mirror session 2 was unconfigured, no controller action ever triggered packet drops. The RL agent was adjusting a register that had zero physical impact on switch queuing or packet forwarding.
2. **Non-Responsive Cross-Traffic:** In Campaigns v1–v3, the background cross-traffic was unpaced UDP (`iperf3 -u`), and video performance was sampled via a 1 Hz ICMP ping simulator (`video_simulator.py`). As demonstrated in Section 4.1, adapting target delay under non-responsive UDP alters loss rates without controlling queue delay, nullifying the mechanism required to improve application QoE.

---

## 6. Limitations

1. **Software Switch Runtime:** All evaluations run on BMv2 `simple_switch`. User-space processing introduces an effective rate limit of $\mu \approx 140\text{--}153\text{ pps}$ with $\approx 9\%$ inter-run service-rate variation.
2. **Packet-Rate vs. Byte-Rate Bottleneck:** Host TCP Segmentation Offload (TSO) aggregates frames to $\approx 9\text{ KB}$, meaning TCP bitrates reflect packet-rate scaling rather than standard MTU bitrates.
3. **Telemetry Artifacts:** INT probes occasionally experience delayed scheduling or timestamp quantization artifacts (e.g., $912\text{ ms}$ probe in `mech_1320k_rep3`), requiring physical plausibility filtering against the 210 ms ceiling.
4. **Small Sample Size:** Sample size is limited to 4 valid UDP runs (3 under the post-hoc relaxed rule), 3 TCP runs, and one load level for TCP.
5. **No Claim of Video QoE Improvement:** This study demonstrates dataplane mechanism control under responsive TCP. We do not claim that RL or adaptive target delay improves DASH video QoE over an optimal fixed delay.

---

## 7. Future Work

1. **Responsive Video Streaming Evaluation (Phase 3):** Evaluate adaptive controllers against calibrated fixed delays (20k vs. 30k vs. 70k) with real adaptive bitrate (ABR) video streaming over responsive HTTP/TCP flows.
2. **Multi-Flow & Mixed Traffic Regimes:** Characterize the AQM trade-off curve under concurrent competing flows (TCP Cubic + TCP BBR + paced UDP).
3. **Hardware P4 Target Deployment:** Port and benchmark the validated mirror-and-drop pipeline on hardware switches (e.g., Intel Tofino) to eliminate software-switch rate scaling and telemetry jitter.
