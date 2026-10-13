#!/usr/bin/env python3
"""
DESiRED Multi-Class Testbed Topology (FINAL - explicit thrift ports)
3 BMv2 switches in series: s1 -- s2 -- s3
Both video and bulk flows enter at s1, traverse s2, exit at s3.

Host layout:
  h1 (video_server)  --- s1 --- s2 --- s3 --- h2 (video_client)
  h3 (bulk_sender)    ---/                \--- h4 (bulk_receiver)

Thrift ports explicitly pinned (not relying on auto-assignment):
  s1 -> 9090, s2 -> 9091, s3 -> 9092, all reachable at 127.0.0.1
"""

from p4utils.mininetlib.network_API import NetworkAPI

net = NetworkAPI()
net.setLogLevel('info')

net.addP4Switch('s1', thrift_port=9090)
net.addP4Switch('s2', thrift_port=9091)
net.addP4Switch('s3', thrift_port=9092)
net.setP4SourceAll('../src/dataplane/DESiRED.p4')

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
net.enableLogAll()
net.enablePcapDumpAll()

net.startNetwork()
