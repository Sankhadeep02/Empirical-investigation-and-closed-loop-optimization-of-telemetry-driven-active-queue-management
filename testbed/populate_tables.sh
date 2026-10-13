#!/bin/bash
# populate_tables.sh
# Pushes ipv4_lpm forwarding rules into all 3 DESiRED P4 switches.
# Run this immediately after topology.py has started the network
# (i.e., once you see the "mininet>" prompt), from any regular shell
# on the host (does NOT need to be run inside the mininet CLI).
#
# Usage:
#   ./populate_tables.sh

set -e

echo "Programming s1 (thrift-port 9090)..."
echo "table_add ipv4_lpm ipv4_forward 10.0.0.1/32 => 00:00:0a:00:00:01 1
table_add ipv4_lpm ipv4_forward 10.0.0.3/32 => 00:00:0a:00:00:03 2
table_add ipv4_lpm ipv4_forward 10.0.0.2/32 => 00:00:0a:00:00:02 3
table_add ipv4_lpm ipv4_forward 10.0.0.4/32 => 00:00:0a:00:00:04 3" | simple_switch_CLI --thrift-port 9090

echo "Programming s2 (thrift-port 9091)..."
echo "table_add ipv4_lpm ipv4_forward 10.0.0.1/32 => 00:00:0a:00:00:01 1
table_add ipv4_lpm ipv4_forward 10.0.0.3/32 => 00:00:0a:00:00:03 1
table_add ipv4_lpm ipv4_forward 10.0.0.2/32 => 00:00:0a:00:00:02 2
table_add ipv4_lpm ipv4_forward 10.0.0.4/32 => 00:00:0a:00:00:04 2" | simple_switch_CLI --thrift-port 9091

echo "Programming s3 (thrift-port 9092)..."
echo "table_add ipv4_lpm ipv4_forward 10.0.0.2/32 => 00:00:0a:00:00:02 1
table_add ipv4_lpm ipv4_forward 10.0.0.4/32 => 00:00:0a:00:00:04 2
table_add ipv4_lpm ipv4_forward 10.0.0.1/32 => 00:00:0a:00:00:01 3
table_add ipv4_lpm ipv4_forward 10.0.0.3/32 => 00:00:0a:00:00:03 3" | simple_switch_CLI --thrift-port 9092

echo "Verifying s1 table entries..."
echo "table_dump ipv4_lpm" | simple_switch_CLI --thrift-port 9090

echo "Done. Run 'pingall' inside the mininet CLI to confirm 0% dropped."

echo "Setting swtrace default action on s1 (thrift-port 9090)..."
echo "table_set_default swtrace add_swtrace 1" | simple_switch_CLI --thrift-port 9090

echo "Setting swtrace default action on s2 (thrift-port 9091)..."
echo "table_set_default swtrace add_swtrace 2" | simple_switch_CLI --thrift-port 9091

echo "Setting swtrace default action on s3 (thrift-port 9092)..."
echo "table_set_default swtrace add_swtrace 3" | simple_switch_CLI --thrift-port 9092

echo "Configuring mirroring sessions for P4 clonePacket on all switches..."
for p in 9090 9091 9092; do
  echo -e "mirroring_add 1 1\nmirroring_add 2 2\nmirroring_add 3 3" | simple_switch_CLI --thrift-port $p
done
