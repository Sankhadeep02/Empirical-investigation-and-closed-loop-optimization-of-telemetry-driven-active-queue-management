#!/usr/bin/env python3
"""
INT Probe Receiver - DESiRED testbed
Sniffs proto=253 packets, parses nodeCount + stacked 32-byte INT headers,
writes CSV matching receiveMetrics.py's intMetrics() expected format.
"""
import argparse
import time
from scapy.all import sniff, IP, Raw

IP_PROTO_INT = 253
INT_HEADER_BYTES = 32

def parse_int_stack(payload: bytes):
    if len(payload) < 2:
        return None, []
    count = int.from_bytes(payload[0:2], byteorder='big')
    hops = []
    offset = 2
    for i in range(count):
        chunk = payload[offset:offset + INT_HEADER_BYTES]
        if len(chunk) < INT_HEADER_BYTES:
            break
        bits = int.from_bytes(chunk, byteorder='big')
        def take(bits_val, total_bits_remaining, width):
            shift = total_bits_remaining - width
            mask = (1 << width) - 1
            value = (bits_val >> shift) & mask
            return value, total_bits_remaining - width
        remaining = 256
        swid, remaining = take(bits, remaining, 31)
        ingress_port, remaining = take(bits, remaining, 9)
        egress_port, remaining = take(bits, remaining, 9)
        egress_spec, remaining = take(bits, remaining, 9)
        ingress_ts, remaining = take(bits, remaining, 48)
        egress_ts, remaining = take(bits, remaining, 48)
        enq_ts, remaining = take(bits, remaining, 32)
        enq_qdepth, remaining = take(bits, remaining, 19)
        deq_timedelta, remaining = take(bits, remaining, 32)
        deq_qdepth, remaining = take(bits, remaining, 19)
        hops.append({
            "swid": swid, "ingress_port": ingress_port, "egress_port": egress_port,
            "egress_spec": egress_spec, "ingress_global_timestamp": ingress_ts,
            "egress_global_timestamp": egress_ts, "enq_timestamp": enq_ts,
            "enq_qdepth": enq_qdepth, "deq_timedelta": deq_timedelta, "deq_qdepth": deq_qdepth
        })
        offset += INT_HEADER_BYTES
    return count, hops

def make_csv_line(hops):
    ts = str(int(time.time() * 1000))[:14]
    fields = [ts]
    for hop in hops:
        fields += [
            str(hop["swid"]), str(hop["ingress_port"]), str(hop["egress_port"]), str(hop["egress_spec"]),
            str(hop["ingress_global_timestamp"]), str(hop["egress_global_timestamp"]),
            str(hop["enq_timestamp"]), str(hop["enq_qdepth"]),
            str(hop["deq_timedelta"]), str(hop["deq_qdepth"])
        ]
    return ",".join(fields)

def main():
    parser = argparse.ArgumentParser(description="DESiRED INT probe receiver")
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(f"Sniffing on {args.iface} for INT probes (proto={IP_PROTO_INT})... Ctrl+C to stop.")

    def handle_packet(pkt):
        if IP in pkt and pkt[IP].proto == IP_PROTO_INT and Raw in pkt:
            payload = bytes(pkt[Raw].load)
            count, hops = parse_int_stack(payload)
            if count and len(hops) == count:
                line = make_csv_line(hops)
                with open(args.out, "a") as f:
                    f.write(line + "\n")
                print(f"Logged {count} hops: {line[:80]}...")
            else:
                print(f"WARNING: expected {count} hops, parsed {len(hops)}")

    sniff(iface=args.iface, filter=f"ip proto {IP_PROTO_INT}", prn=handle_packet, store=False)

if __name__ == "__main__":
    main()
