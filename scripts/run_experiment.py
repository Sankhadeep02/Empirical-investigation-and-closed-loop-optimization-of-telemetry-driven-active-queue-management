#!/usr/bin/env python3
"""
scripts/run_experiment.py

Automated orchestrator for running DESiRED testbed experiments.
Handles pre-flight checks, switch register configuration, synchronized
process launch, live telemetry monitoring, graceful teardown, validation,
and registry recording.
"""

import sys
import os
import time
import argparse
import subprocess
import signal
from pathlib import Path
import csv

REPO_ROOT = Path("/home/p4/DESiRED")
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
AGENT_LOG_DIR = REPO_ROOT / "local_controller/agent_logs"
REGISTRY_FILE = REPO_ROOT / "results/campaign_v2/experiment_registry.csv"

THRIFT_PORTS = [9090, 9091, 9092]

def run_cmd(cmd, check=True):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {cmd}\nStderr: {res.stderr}")
    return res

def set_switch_registers(target_delay, queue_rate=0, queue_depth=0):
    print(f"[*] Setting switch targetDelay_reg to {target_delay} on switches s1, s2, s3...")
    for port in THRIFT_PORTS:
        cmd = f"echo 'register_write MyEgress.targetDelay_reg 0 {target_delay}' | simple_switch_CLI --thrift-port {port} --thrift-ip 127.0.0.1"
        run_cmd(cmd)
    
    if queue_rate > 0:
        print(f"[*] Setting bottleneck queue rate {queue_rate} pps on s2 port 2...")
        cmd = f"echo 'set_queue_rate {queue_rate} 2' | simple_switch_CLI --thrift-port 9091 --thrift-ip 127.0.0.1"
        run_cmd(cmd)
    if queue_depth > 0:
        print(f"[*] Setting bottleneck queue depth {queue_depth} pkts on s2 port 2...")
        cmd = f"echo 'set_queue_depth {queue_depth} 2' | simple_switch_CLI --thrift-port 9091 --thrift-ip 127.0.0.1"
        run_cmd(cmd)
    
    # Read back and verify
    for port in THRIFT_PORTS:
        cmd = f"echo 'register_read MyEgress.targetDelay_reg 0' | simple_switch_CLI --thrift-port {port} --thrift-ip 127.0.0.1"
        res = run_cmd(cmd)
        if f"= {target_delay}" not in res.stdout:
            raise RuntimeError(f"Switch on port {port} readback mismatch! Output: {res.stdout}")
    print(f"[+] All switch registers verified at {target_delay} us.")

def ensure_iperf_server():
    res = subprocess.run("mx h4 ss -lntup", shell=True, capture_output=True, text=True)
    if ":5201" not in res.stdout:
        print("[*] Starting iperf3 server in h4...")
        subprocess.run("mx h4 iperf3 -s -D", shell=True, check=True)
        time.sleep(1)
        res = subprocess.run("mx h4 ss -lntup", shell=True, capture_output=True, text=True)
        if ":5201" not in res.stdout:
            raise RuntimeError("Failed to start iperf3 server in h4 namespace.")
    print("[+] iperf3 server active in h4 namespace.")

def cleanup_processes():
    targets = ["int_sender.py", "int_receiver_debug.py", "video_simulator.py", "receiveMetrics.py", "rule_controller.py"]
    for t in targets:
        subprocess.run(f"pkill -f {t}", shell=True, stderr=subprocess.DEVNULL)
    # Stop any active iperf clients
    subprocess.run("pkill -f 'iperf3 -c'", shell=True, stderr=subprocess.DEVNULL)
    time.sleep(1)

def record_registry(
    run_id,
    policy,
    initial_delay,
    load_kbps,
    duration,
    controller_enabled,
    model_file,
    status,
    notes,
):
    """Record one campaign-v2 experiment using a fixed, explicit schema."""
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)

    video_destination = "10.0.0.4"
    video_target_ms = "60.0"
    ping_timeout_s = "0.5"

    git_commit = "unknown"
    try:
        git_commit = subprocess.check_output(
            "git rev-parse --short HEAD",
            shell=True,
            cwd=REPO_ROOT,
            text=True,
        ).strip()
    except Exception:
        pass

    fieldnames = [
        "run_id",
        "policy",
        "initial_delay",
        "load_kbps",
        "duration_s",
        "video_destination",
        "video_target_ms",
        "ping_timeout_s",
        "controller_enabled",
        "model_file",
        "code_commit",
        "status",
        "notes",
    ]

    rows = []
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "r", newline="") as registry:
            reader = csv.DictReader(registry)
            for row in reader:
                if row.get("run_id") != run_id:
                    rows.append({key: row.get(key, "") for key in fieldnames})

    rows.append(
        {
            "run_id": run_id,
            "policy": policy,
            "initial_delay": str(initial_delay),
            "load_kbps": str(load_kbps),
            "duration_s": str(duration),
            "video_destination": video_destination,
            "video_target_ms": video_target_ms,
            "ping_timeout_s": ping_timeout_s,
            "controller_enabled": "yes" if controller_enabled else "no",
            "model_file": model_file,
            "code_commit": git_commit,
            "status": status,
            "notes": notes,
        }
    )

    # Write atomically via temp file
    tmp_registry = REGISTRY_FILE.with_suffix(".csv.tmp")
    with open(tmp_registry, "w", newline="") as registry:
        writer = csv.DictWriter(registry, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_registry, REGISTRY_FILE)

    print(f"[+] Registry updated for {run_id} (Status: {status})")

def main():
    parser = argparse.ArgumentParser(description="DESiRED Experiment Runner")
    parser.add_argument("--run-id", required=True, help="Unique run identifier (e.g. fixed50k_load_1)")
    parser.add_argument("--policy", required=True, choices=["fixed20k", "fixed50k", "fixed30k", "fixed40k", "fixed70k", "infer", "infer20k", "rule", "infer9"], help="Control policy")
    parser.add_argument("--duration", type=int, default=700, help="Run duration in seconds")
    parser.add_argument("--load-kbps", "--load", dest="load_kbps", type=int, default=500, help="Background UDP load in kbps")
    parser.add_argument("--load-schedule", default=None, help="Dynamic UDP load schedule, e.g. '200:233,1000:233,500:234' (kbps:duration)")
    parser.add_argument("--iperf-host", default="h2", choices=["h2", "h3"], help="Host running iperf3 client")
    parser.add_argument("--queue-rate", type=int, default=0, help="Egress queue rate in pps on s2 port 2 (0 = unconstrained)")
    parser.add_argument("--queue-depth", type=int, default=0, help="Egress queue depth in packets on s2 port 2 (0 = unconstrained)")
    parser.add_argument("--video-target-ms", type=float, default=60.0, help="Video simulator latency deadline in ms")
    parser.add_argument("--seed", type=int, default=1, help="Random seed for reproducibility")
    parser.add_argument("--skip-validation", action="store_true", help="Skip post-run validation")
    args = parser.parse_args()

    run_id = args.run_id
    policy = args.policy
    duration = args.duration
    load_kbps = args.load_kbps

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Determine initial delay and controller configuration
    if policy == "fixed20k":
        initial_delay = 20000
        controller_enabled = False
        model_file = "N/A"
    elif policy == "fixed50k":
        initial_delay = 50000
        controller_enabled = False
        model_file = "N/A"
    elif policy == "fixed30k":
        initial_delay = 30000
        controller_enabled = False
        model_file = "N/A"
    elif policy == "fixed40k":
        initial_delay = 40000
        controller_enabled = False
        model_file = "N/A"
    elif policy == "fixed70k":
        initial_delay = 70000
        controller_enabled = False
        model_file = "N/A"
    elif policy in ("infer", "infer20k"):
        initial_delay = 20000 if policy == "infer20k" else 50000
        controller_enabled = True
        model_file = "train_socket_load_1.h5"
    elif policy == "infer9":
        initial_delay = 50000
        controller_enabled = True
        model_file = "online_network_retrained_balanced.h5"
    elif policy == "rule":
        initial_delay = 50000
        controller_enabled = True
        model_file = "heuristic_threshold"
    else:
        raise ValueError(f"Unknown policy: {policy}")

    print(f"\n==================================================")
    print(f" Starting Experiment: {run_id}")
    print(f" Policy: {policy} | Target Delay: {initial_delay} us | Duration: {duration}s | Load: {load_kbps} kbps")
    print(f"==================================================\n")

    cleanup_processes()
    ensure_iperf_server()
    set_switch_registers(initial_delay, queue_rate=args.queue_rate, queue_depth=args.queue_depth)
    time.sleep(5.0)  # Let network settle after register writes

    # Remove any existing log files for this run_id to prevent collision
    for pattern in [f"*{run_id}*"]:
        for p in LOG_DIR.glob(pattern):
            p.unlink()
        for p in AGENT_LOG_DIR.glob(pattern):
            p.unlink()

    int_log = LOG_DIR / f"log_INT_{run_id}.txt"
    dash_log = LOG_DIR / f"dash_{run_id}.txt"
    receiver_log = LOG_DIR / f"receiver_{run_id}.log"
    sender_log = LOG_DIR / f"sender_{run_id}.log"
    video_log = LOG_DIR / f"video_{run_id}.log"
    iperf_log = LOG_DIR / f"iperf_client_{run_id}.log"
    controller_log = LOG_DIR / f"controller_{run_id}.log"

    # Create controller input files before controller threads start tailing them.
    # The receiver/video writers will append their first records later.
    int_log.touch()
    dash_log.touch()

    # 1. Start INT Receiver on h4
    recv_cmd = f"mx h4 python3 /home/p4/DESiRED/testbed/int_receiver_debug.py --iface h4-eth0 --out {int_log} > {receiver_log} 2>&1"
    p_recv = subprocess.Popen(recv_cmd, shell=True)
    time.sleep(1.0)
    print(f"[+] INT Receiver started (PID {p_recv.pid})")

    # 2. Start Controller (if applicable)
    p_ctrl = None
    if policy in ("infer", "infer20k"):
        # Parse run number and type for receiveMetrics.py
        # run_id e.g. infer_socket_load_5 -> number='5', type='infer_socket_load'
        parts = run_id.rsplit("_", 1)
        c_type, c_num = parts[0], parts[1]
        controller_duration = duration + 20
        ctrl_cmd = f"python3 receiveMetrics.py {c_num} {c_type} --duration {controller_duration} --initial-delay {initial_delay} > {controller_log} 2>&1"
        p_ctrl = subprocess.Popen(ctrl_cmd, shell=True, cwd=REPO_ROOT / "local_controller")
        print(f"[+] RL Inference Controller started (PID {p_ctrl.pid}) [Initial Delay: {initial_delay} us]")
    elif policy == "infer9":
        parts = run_id.rsplit("_", 1)
        c_type, c_num = parts[0], parts[1]
        controller_duration = duration + 20
        ctrl_cmd = f"python3 receiveMetrics.py {c_num} {c_type} --duration {controller_duration} --state-dim 9 --model-path agent_models_fixed/online_network_retrained_balanced.h5 --initial-delay {initial_delay} > {controller_log} 2>&1"
        p_ctrl = subprocess.Popen(ctrl_cmd, shell=True, cwd=REPO_ROOT / "local_controller")
        print(f"[+] Retrained 9-Feature RL Controller started (PID {p_ctrl.pid})")
    elif policy == "rule":
        parts = run_id.rsplit("_", 1)
        c_type, c_num = parts[0], parts[1]
        controller_duration = duration + 20
        ctrl_cmd = f"python3 rule_controller.py {c_num} {c_type} --duration {controller_duration} --initial-delay {initial_delay} > {controller_log} 2>&1"
        p_ctrl = subprocess.Popen(ctrl_cmd, shell=True, cwd=REPO_ROOT / "local_controller")
        print(f"[+] Rule-Based Controller started (PID {p_ctrl.pid}) [Initial Delay: {initial_delay} us]")

    # Ensure controller has fully loaded neural network weights and initialized listeners
    if p_ctrl is not None:
        if policy in ("infer", "infer20k", "infer9"):
            print("[*] Synchronizing: waiting for controller to load neural network and start telemetry threads...")
            for _ in range(120):
                if controller_log.exists():
                    txt = controller_log.read_text(errors='ignore')
                    if "freezing the q-network layers weights" in txt:
                        print("[+] Controller neural network initialized and listeners active.")
                        time.sleep(2.0)
                        break
                time.sleep(1.0)
            else:
                print("[WARNING] Controller initialization wait timed out; proceeding anyway.")
        elif policy == "rule":
            time.sleep(1.0)

    # 3. Start Video Simulator on h1.
    # This is the application QoE requirement, held constant across policies.
    video_target_delay_ms = args.video_target_ms
    video_ping_timeout_s = 0.5
    video_cmd = (
        f"mx h1 python3 /home/p4/DESiRED/testbed/video_simulator.py "
        f"--dst 10.0.0.4 --duration {duration} "
        f"--target-delay-ms {video_target_delay_ms} "
        f"--ping-timeout-s {video_ping_timeout_s} "
        f"--out {dash_log} > {video_log} 2>&1"
    )
    p_video = subprocess.Popen(video_cmd, shell=True)
    print(f"[+] Video Simulator started (PID {p_video.pid})")

    # 4. Start iperf client and INT sender
    if args.iperf_host == "h3":
        if args.load_schedule:
            segments = []
            for part in args.load_schedule.split(","):
                rate, seg_dur = part.strip().split(":")
                segments.append(f"iperf3 -c 10.0.0.4 -u -b {rate}k -t {seg_dur} -i 1 -l 1470")
            iperf_inner = " ; ".join(segments)
            iperf_cmd = f"mx h3 bash -c \"{iperf_inner}\" > {iperf_log} 2>&1"
            print(f"[+] Dynamic load schedule configured on h3: {args.load_schedule}")
        else:
            iperf_cmd = f"mx h3 iperf3 -c 10.0.0.4 -u -b {load_kbps}k -t {duration} -i 1 -l 1470 > {iperf_log} 2>&1"
        p_iperf = subprocess.Popen(iperf_cmd, shell=True)
        print(f"[+] iperf3 UDP Client started on h3 (PID {p_iperf.pid})")

        # Start INT Sender on h1 so probes traverse all switches s1 -> s2 -> s3
        sender_cmd = f"mx h1 python3 /home/p4/DESiRED/testbed/int_sender.py --src 10.0.0.1 --dst 10.0.0.4 --dst-mac 00:00:0a:00:00:04 --iface h1-eth0 --count {duration} --interval 1.0 > {sender_log} 2>&1"
        p_sender = subprocess.Popen(sender_cmd, shell=True)
        print(f"[+] INT Sender started on h1 (PID {p_sender.pid})")
    else:
        if args.load_schedule:
            segments = []
            for part in args.load_schedule.split(","):
                rate, seg_dur = part.strip().split(":")
                segments.append(f"iperf3 -c 10.0.0.4 -u -b {rate}k -t {seg_dur} -i 1")
            iperf_inner = " ; ".join(segments)
            iperf_cmd = f"mx h2 bash -c \"{iperf_inner}\" > {iperf_log} 2>&1"
            print(f"[+] Dynamic load schedule configured: {args.load_schedule}")
        else:
            iperf_cmd = f"mx h2 iperf3 -c 10.0.0.4 -u -b {load_kbps}k -t {duration} -i 1 > {iperf_log} 2>&1"
        p_iperf = subprocess.Popen(iperf_cmd, shell=True)
        print(f"[+] iperf3 UDP Client started on h2 (PID {p_iperf.pid})")

        # Start INT Sender on h3
        sender_cmd = f"mx h3 python3 /home/p4/DESiRED/testbed/int_sender.py --src 10.0.0.3 --dst 10.0.0.4 --dst-mac 00:00:0a:00:00:04 --iface h3-eth0 --count {duration} --interval 1.0 > {sender_log} 2>&1"
        p_sender = subprocess.Popen(sender_cmd, shell=True)
        print(f"[+] INT Sender started on h3 (PID {p_sender.pid})")

    # Monitor loop
    start_time = time.time()
    print(f"\n[*] Experiment running for {duration} seconds... Monitoring progress:")
    
    last_print = start_time
    while time.time() - start_time < (duration + 30):
        time.sleep(5.0)
        elapsed = int(time.time() - start_time)
        if time.time() - last_print >= 30.0:
            last_print = time.time()
            int_cnt = sum(1 for _ in open(int_log)) if int_log.exists() else 0
            dash_cnt = sum(1 for _ in open(dash_log)) if dash_log.exists() else 0
            print(f"  [t={elapsed}s / {duration}s] INT probes logged: {int_cnt} | DASH rows: {dash_cnt} | iperf active: {p_iperf.poll() is None}")

        if p_sender.poll() is not None and elapsed >= duration:
            break

    print(f"\n[*] Nominal duration reached. Allowing sources to finish and logs to flush...")
    for proc in (p_sender, p_video, p_iperf):
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            pass

    # Controllers start before traffic sources and run for duration + 20 seconds.
    # Wait for their normal save phase before generic cleanup can terminate them.
    if p_ctrl is not None:
        print("[*] Waiting for controller to save logs...")
        try:
            p_ctrl.wait(timeout=150)
        except subprocess.TimeoutExpired:
            print("[WARNING] Controller did not exit in time; cleanup will terminate it.")

    time.sleep(2.0)

    # Teardown
    cleanup_processes()
    print(f"[+] Processes cleanly terminated.")

    # Validation
    status = "UNKNOWN"
    notes = ""
    if not args.skip_validation:
        val_cmd = f"python3 scripts/validate_run.py {run_id} --duration {duration}"
        res = subprocess.run(val_cmd, shell=True, capture_output=True, text=True, cwd=REPO_ROOT)
        print(f"\n--- Validation Output ---")
        print(res.stdout.strip())
        if res.stderr.strip():
            print(f"Validation Stderr: {res.stderr.strip()}")
        print(f"-------------------------\n")
        
        for line in res.stdout.splitlines():
            if line.startswith("STATUS:"):
                status = line.split(":", 1)[1].strip()
            elif line.strip().startswith("- Duration:"):
                notes = line.strip().lstrip("- ")

        if status == "VALID":
            print(f"[SUCCESS] Run {run_id} is VALID!")
        else:
            print(f"[WARNING] Run {run_id} validation status: {status}")
    else:
        status = "COMPLETE_UNVALIDATED"

    reg_load = f"dyn_{args.load_schedule}" if args.load_schedule else load_kbps
    record_registry(run_id, policy, initial_delay, reg_load, duration, controller_enabled, model_file, status, notes)
    print(f"[+] Experiment {run_id} finished.\n")

if __name__ == "__main__":
    main()
