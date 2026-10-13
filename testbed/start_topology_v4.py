#!/usr/bin/env python3
"""
testbed/start_topology_v4.py

Starts the DESiRED 3-switch testbed for Campaign v4:
  - BMv2 switches s1 (9090), s2 (9091), s3 (9092)
  - Console logging explicitly DISABLED (disableLogAll) to prevent BMv2 I/O bottlenecks
  - Keeps network running until SIGINT/SIGTERM
"""

import sys
import time
import signal
from pathlib import Path
from p4utils.mininetlib.network_API import NetworkAPI

REPO_ROOT = Path("/home/p4/DESiRED")
P4_SRC = str(REPO_ROOT / "src/dataplane/DESiRED.p4")

net = NetworkAPI()
net.setLogLevel('info')

net.addP4Switch('s1', thrift_port=9090)
net.addP4Switch('s2', thrift_port=9091)
net.addP4Switch('s3', thrift_port=9092)
net.setP4SourceAll(P4_SRC)

net.addHost('h1')
net.addHost('h2')
net.addHost('h3')
net.addHost('h4')

net.addLink('h1', 's1')
net.addLink('h3', 's1')
net.addLink('s1', 's2')
net.addLink('s2', 's3')
net.addLink('h2', 's3')
net.addLink('h4', 's3')

net.l2()

net.enableCpuPortAll()
net.disableLogAll()     # v4: no --log-console overhead
net.disablePcapDumpAll() # v4: no disk I/O contention from packet dumps
net.disableCli()

def shutdown(sig, frame):
    print("\nStopping network...")
    try:
        net.stopNetwork()
    except Exception as e:
        print(f"Error stopping network: {e}")
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

print("[*] Starting Mininet network (v4 configuration)...")
net.startNetwork()
print("[+] Network successfully started and running in background.")

# Keep process alive
while True:
    time.sleep(1.0)
