#!/usr/bin/env python3
"""
local_controller/rule_controller.py

Transparent Rule-Based Target-Delay Controller for DESiRED Testbed.
Acts as a principled heuristic baseline against RL and static delay policies.
Monitors live INT queue depth, dequeue delay, and video buffer, then adapts
P4 switch targetDelay_reg dynamically.
"""

import sys
import os
import time
import argparse
import subprocess
import csv
import threading
from io import StringIO
import pandas as pd
import numpy as np
import tail

INT_TYPE = 0
DASH_TYPE = 1
DEFAULT_TARGET_DELAY = 50000
MIN_TARGET_DELAY = 20000
MAX_TARGET_DELAY = 70000
STEP_SIZE = 5000

INCREASE_TARGET_DELAY = 0
DECREASE_TARGET_DELAY = 1
DO_NOTHING = 2

class RuleController:
    def __init__(self, experiment_id, duration=700, initial_delay=DEFAULT_TARGET_DELAY):
        self.experiment_id = experiment_id
        self.duration = duration
        self.current_delay = initial_delay
        self.delay_history = [initial_delay]
        self.action_history = []
        self.fps_history = []
        self.reward_history = [0]
        self.lock = threading.Lock()
        
        self.aggregated_int = []
        self.aggregated_dash = []
        self.running = True

    def set_switch_delay(self, target_delay):
        self.current_delay = target_delay
        for port in [9090, 9091, 9092]:
            cmd = f"echo 'register_write MyEgress.targetDelay_reg 0 {target_delay}' | simple_switch_CLI --thrift-port {port} --thrift-ip 127.0.0.1"
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def decide_action(self, int_window, dash_window):
        """
        int_window: DataFrame with INT columns
        dash_window: DataFrame with DASH columns (timestamp, FPS, bufferLocal, BitrateCalc)
        """
        # Calculate max queue depth across 3 hops
        qdepths = []
        for hop in [1, 2, 3]:
            col_enq = f'enq_qdepth{hop}'
            col_deq = f'deq_qdepth{hop}'
            if col_enq in int_window:
                qdepths.append(int_window[col_enq].max())
            if col_deq in int_window:
                qdepths.append(int_window[col_deq].max())

        max_q = max(qdepths) if qdepths else 0
        mean_buffer = dash_window['bufferLocal'].mean() if not dash_window.empty else 20.0
        fps = dash_window['FPS'].iloc[-1] if not dash_window.empty else 30

        # Heuristic rules:
        # If queue is building up (>15 pkts) or buffer is dropping below 15s with queue > 5:
        # Decrease target delay to trigger AQM early drops, draining the bottleneck.
        if max_q > 15 or (mean_buffer < 15.0 and max_q > 5):
            action = DECREASE_TARGET_DELAY
            new_delay = max(MIN_TARGET_DELAY, self.current_delay - STEP_SIZE)
        # If queue is completely idle (<3 pkts) and buffer is healthy (>25s):
        # Relax target delay towards upper threshold to prevent unnecessary drops.
        elif max_q <= 2 and mean_buffer > 25.0:
            action = INCREASE_TARGET_DELAY
            new_delay = min(MAX_TARGET_DELAY, self.current_delay + STEP_SIZE)
        else:
            action = DO_NOTHING
            new_delay = self.current_delay

        if new_delay != self.current_delay:
            self.set_switch_delay(new_delay)

        self.action_history.append(action)
        self.delay_history.append(self.current_delay)
        self.fps_history.append(fps)
        
        # Simple proxy reward for comparability
        r = 1.0 if fps == 30 and mean_buffer > 20 else (0.5 if fps >= 24 else -1.0)
        self.reward_history.append(r)

        print(f"[RULE_CTRL] max_q={max_q} buf={mean_buffer:.1f}s fps={fps} -> action={action} new_delay={self.current_delay}")

    def save_logs(self):
        os.makedirs("agent_logs", exist_ok=True)
        with open(f'agent_logs/campaign_v2/action_history_{self.experiment_id}.csv', 'w', newline='') as f:
            csv.writer(f).writerows([[a] for a in self.action_history])
        with open(f'agent_logs/campaign_v2/reward_history_{self.experiment_id}.csv', 'w', newline='') as f:
            csv.writer(f).writerows([[r] for r in self.reward_history])
        with open(f'agent_logs/campaign_v2/fps_history_{self.experiment_id}.csv', 'w', newline='') as f:
            csv.writer(f).writerows([[fps] for fps in self.fps_history])
        for sw in [1, 2, 3]:
            with open(f'agent_logs/campaign_v2/sw{sw}_target_delay_history_{self.experiment_id}.csv', 'w', newline='') as f:
                csv.writer(f).writerows([[d] for d in self.delay_history])
        with open(f'agent_logs/campaign_v2/loss_history_{self.experiment_id}.csv', 'w', newline='') as f:
            pass
        with open(f'agent_logs/campaign_v2/q-values_history_{self.experiment_id}.csv', 'w', newline='') as f:
            pass

def main():
    parser = argparse.ArgumentParser(description="Rule-based Target Delay Controller")
    parser.add_argument("number", type=str, help="Run number")
    parser.add_argument("type", type=str, help="Policy type (e.g. rule_load)")
    parser.add_argument("--duration", type=int, default=700)
    parser.add_argument("--initial-delay", type=int, default=DEFAULT_TARGET_DELAY, help="Initial target delay in us")
    args = parser.parse_args()

    experiment_id = f"{args.type}_{args.number}"
    ctrl = RuleController(experiment_id, duration=args.duration, initial_delay=args.initial_delay)
    
    # Initialize switch target delays
    ctrl.set_switch_delay(args.initial_delay)
    print(f"Rule controller started for {experiment_id} with initial delay {args.initial_delay}")

    dash_path = f"/home/p4/DESiRED/src/logs/campaign_v2/dash_{experiment_id}.txt"
    int_path = f"/home/p4/DESiRED/src/logs/campaign_v2/log_INT_{experiment_id}.txt"

    INTnames = ['timestamp','ingress_global_timestamp3','egress_global_timestamp3','enq_timestamp3','enq_qdepth3','deq_timedelta3','deq_qdepth3', 
                'ingress_global_timestamp2','egress_global_timestamp2','enq_timestamp2','enq_qdepth2','deq_timedelta2','deq_qdepth2',
                'ingress_global_timestamp1','egress_global_timestamp1','enq_timestamp1', 'enq_qdepth1','deq_timedelta1','deq_qdepth1']
    DASHnames = ['timestamp','FPS','bufferLocal','BitrateCalc']

    buf_int = []
    buf_dash = []

    def on_dash_line(line):
        parts = line.strip().split(";")
        if len(parts) >= 4:
            try:
                buf_dash.append({
                    'timestamp': int(parts[0]) // 1000,
                    'bufferLocal': float(parts[1]),
                    'FPS': float(parts[2]),
                    'BitrateCalc': float(parts[3])
                })
            except ValueError:
                pass

    def on_int_line(line):
        parts = line.strip().split(",")
        if len(parts) >= 31:
            try:
                # 31 fields from int_receiver_debug
                # CSV layout: receiver timestamp, then three 10-field hops.
                # Per hop: swid, ingress_port, egress_port, egress_spec,
                # ingress_ts, egress_ts, enq_ts, enq_qdepth,
                # deq_timedelta, deq_qdepth.
                row = {
                    'timestamp': int(parts[0]) // 1000,
                    'enq_qdepth3': int(parts[8]),
                    'deq_qdepth3': int(parts[10]),
                    'enq_qdepth2': int(parts[18]),
                    'deq_qdepth2': int(parts[20]),
                    'enq_qdepth1': int(parts[28]),
                    'deq_qdepth1': int(parts[30]),
                }
                buf_int.append(row)
            except (ValueError, IndexError):
                pass

    def start_tail(path, cb):
        t = tail.Tail(path)
        t.register_callback(cb)
        t.follow(s=0.1)

    t_dash = threading.Thread(target=start_tail, args=(dash_path, on_dash_line), daemon=True)
    t_dash.start()

    t_int = threading.Thread(target=start_tail, args=(int_path, on_int_line), daemon=True)
    t_int.start()

    start_time = time.time()
    last_eval = start_time

    while time.time() - start_time < args.duration:
        time.sleep(1.0)
        # Every 4 seconds, evaluate policy
        if time.time() - last_eval >= 4.0:
            last_eval = time.time()
            if len(buf_int) >= 4 and len(buf_dash) >= 4:
                df_int = pd.DataFrame(buf_int[-4:])
                df_dash = pd.DataFrame(buf_dash[-4:])
                ctrl.decide_action(df_int, df_dash)

    ctrl.save_logs()
    print("logs saved")

if __name__ == "__main__":
    main()
