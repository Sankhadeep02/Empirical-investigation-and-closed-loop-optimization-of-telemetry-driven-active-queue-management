#!/usr/bin/env python3
"""
Video-QoS simulator for the DESiRED Mininet testbed.

It samples h1-to-destination RTT once per scheduled second, maintains a
simple playback-buffer model, and writes:
timestamp_ms;buffer_seconds;fps;bitrate_kbps

A Python-level timeout prevents an individual ping from blocking the QoE
sampling loop for multiple seconds. A record is written even when ping times
out, representing degraded connectivity rather than missing instrumentation.
"""
import argparse
import subprocess
import time

TIERS = [
    (10.0, 30, 1040),
    (3.0, 24, 490),
    (0.0, 18, 140),
]

BUFFER_MAX = 64.0
BUFFER_DRAIN_RATE = 1.0
BUFFER_FILL_RATE = 1.5


def choose_tier(buffer_level):
    for min_buffer, fps, bitrate in TIERS:
        if buffer_level > min_buffer:
            return fps, bitrate
    return 0, 0


def measure_delay_once(dst_ip, timeout_s):
    """
    Return ping RTT in milliseconds, or None on timeout/loss/parse failure.
    The subprocess timeout is independent of ping's own timeout option.
    """
    ping_wait_s = max(1, int(timeout_s + 0.999))

    try:
        result = subprocess.run(
            ["ping", "-n", "-c", "1", "-W", str(ping_wait_s), dst_ip],
            capture_output=True,
            text=True,
            timeout=timeout_s + 0.25,
        )
    except subprocess.TimeoutExpired:
        return None

    if result.returncode != 0 or "time=" not in result.stdout:
        return None

    try:
        return float(result.stdout.split("time=", 1)[1].split()[0])
    except (IndexError, ValueError):
        return None


def update_buffer(buffer_level, delay_ms, target_delay_ms):
    if delay_ms is None:
        return max(0.0, buffer_level - 2.0 * BUFFER_DRAIN_RATE)

    if delay_ms <= target_delay_ms:
        return min(BUFFER_MAX, buffer_level + BUFFER_FILL_RATE)

    excess_ratio = delay_ms / target_delay_ms
    return max(0.0, buffer_level - BUFFER_DRAIN_RATE * excess_ratio)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dst", required=True)
    parser.add_argument("--target-delay-ms", type=float, required=True)
    parser.add_argument("--ping-timeout-s", type=float, default=0.5)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.target_delay_ms <= 0:
        raise SystemExit("--target-delay-ms must be positive")
    if args.ping_timeout_s <= 0:
        raise SystemExit("--ping-timeout-s must be positive")

    buffer_level = 20.0
    start = time.monotonic()
    next_tick = start

    with open(args.out, "a", buffering=1) as out_file:
        for sample_index in range(args.duration):
            next_tick = start + sample_index
            remaining = next_tick - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)

            delay_ms = measure_delay_once(args.dst, args.ping_timeout_s)
            buffer_level = update_buffer(
                buffer_level, delay_ms, args.target_delay_ms
            )
            fps, bitrate = choose_tier(buffer_level)
            timestamp_ms = int(time.time() * 1000)

            out_file.write(
                f"{timestamp_ms};{buffer_level:.2f};{fps};{bitrate}\n"
            )

            shown_delay = "None" if delay_ms is None else f"{delay_ms:.3f}"
            elapsed_s = time.monotonic() - start
            print(
                f"[t={elapsed_s:.2f}s] delay={shown_delay}ms "
                f"buffer={buffer_level:.2f}s fps={fps} "
                f"bitrate={bitrate}kbps"
            )


if __name__ == "__main__":
    main()
