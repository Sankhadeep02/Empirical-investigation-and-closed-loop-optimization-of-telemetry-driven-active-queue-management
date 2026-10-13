# Metrics Definition Specification

This document details the exact formula, logging source, and interpretation for all metrics used in the DESiRED evaluation.

## 1. Video Quality of Experience (QoE) Metrics
*Source: `src/logs/dash_<run_id>.txt`*

| Metric | Formula / Definition | Unit | Target |
| :--- | :--- | :--- | :--- |
| **Duration-Weighted Mean FPS** | $\frac{\sum \text{FPS}_i \cdot \Delta t_i}{\sum \Delta t_i}$ | frames/sec | Maximize ($\to 30$) |
| **Median FPS** | 50th percentile of duration-weighted playback frame rate | frames/sec | Maximize ($\to 30$) |
| **30 FPS Availability ($F_{30}$)** | $\frac{\sum \mathbb{I}(\text{FPS}_i=30) \cdot \Delta t_i}{\sum \Delta t_i}$ | % | Maximize ($\to 100\%$) |
| **Rebuffer / Stall Fraction ($F_0$)** | $\frac{\sum \mathbb{I}(\text{FPS}_i=0) \cdot \Delta t_i}{\sum \Delta t_i}$ | % | Minimize ($\to 0\%$) |
| **Mean Buffer Level** | $\frac{\sum B_i \cdot \Delta t_i}{\sum \Delta t_i}$ | seconds | Maximize ($\ge 20$s) |
| **Low-Buffer Risk ($F_{B<3s}$)** | $\frac{\sum \mathbb{I}(B_i < 3.0) \cdot \Delta t_i}{\sum \Delta t_i}$ | % | Minimize ($\to 0\%$) |
| **Duration-Weighted Mean Bitrate** | $\frac{\sum R_i \cdot \Delta t_i}{\sum \Delta t_i}$ | kbps | Maximize ($\to 1040$) |

## 2. Network Performance Metrics
*Source: `src/logs/iperf_client_<run_id>.log`*

| Metric | Formula / Definition | Unit | Target |
| :--- | :--- | :--- | :--- |
| **Delivered UDP Bitrate** | Receiver reported goodput | kbps | Near offered rate (500 kbps) |
| **Datagram Loss Percentage** | $\frac{\text{Lost Datagrams}}{\text{Total Datagrams}} \times 100\%$ | % | Minimize ($\to 0\%$) |
| **Receiver Jitter** | Mean inter-arrival delay variation | ms | Minimize |

## 3. In-band Telemetry & Control Metrics
*Sources: `src/logs/log_INT_<run_id>.txt` and `local_controller/agent_logs/`*

| Metric | Formula / Definition | Unit | Purpose |
| :--- | :--- | :--- | :--- |
| **Hop 1/2/3 Enqueue Queue Depth** | Telemetry queue depth in BMv2 switch | packets | Bufferbloat tracking |
| **Total Dequeue Timedelta** | Sum of queue delay across 3 hops | $\mu\text{s}$ | Queue latency |
| **Target Delay Trajectory** | P4 register values ($s_1, s_2, s_3$) | $\mu\text{s}$ | Actuation verification |
| **Action Proportions** | % of Increase (0), Decrease (1), Hold (2) | % | Policy diversity |
