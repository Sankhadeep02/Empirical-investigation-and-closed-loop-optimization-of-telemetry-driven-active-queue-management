#!/usr/bin/env python3
"""
INT Probe Sender for the DESiRED testbed.

Sends custom protocol-253 probes at deadline-based intervals so transient
scheduler delays do not accumulate into permanent timing drift.
"""
import argparse
import time

from scapy.all import Ether, IP, Raw, conf, get_if_hwaddr, sendp

IP_PROTO_INT = 253


def build_probe(src_ip, dst_ip, dst_mac, iface):
    node_count_bytes = (0).to_bytes(2, byteorder="big")
    return (
        Ether(src=get_if_hwaddr(iface), dst=dst_mac)
        / IP(src=src_ip, dst=dst_ip, proto=IP_PROTO_INT)
        / Raw(load=node_count_bytes)
    )


def main():
    parser = argparse.ArgumentParser(description="DESiRED INT probe sender")
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--dst-mac", required=True)
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    if args.count <= 0:
        raise SystemExit("--count must be positive")
    if args.interval <= 0:
        raise SystemExit("--interval must be positive")

    sock = conf.L2socket(iface=args.iface)
    start = time.monotonic()

    try:
        for index in range(args.count):
            deadline = start + index * args.interval
            wait_s = deadline - time.monotonic()
            if wait_s > 0:
                time.sleep(wait_s)

            pkt = build_probe(args.src, args.dst, args.dst_mac, args.iface)
            send_started = time.time()
            sendp(pkt, socket=sock, verbose=False)
            send_finished = time.time()

            lateness_ms = max(0.0, (time.monotonic() - deadline) * 1000)
            print(
                f"[{index + 1}/{args.count}] sent INT probe "
                f"{args.src} -> {args.dst} "
                f"started={send_started:.3f} finished={send_finished:.3f} "
                f"sendp_ms={(send_finished - send_started) * 1000:.1f} "
                f"lateness_ms={lateness_ms:.1f}",
                flush=True,
            )
    finally:
        sock.close()


if __name__ == "__main__":
    main()
