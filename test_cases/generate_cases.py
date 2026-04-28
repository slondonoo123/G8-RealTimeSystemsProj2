"""Synthesize three test cases (low/med/high utilization).

Produces topology.json, streams.json, routes.json under each
test_cases/case_*/ directory. JSON shape matches the Paul-Pop generator
output and the original test-case-1-*.json files.
"""
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def two_switch_topology():
    """ES0 -- SW0 -- SW1 -- ES1 (linear, 2 switches)."""
    return {
        "delay_units": "MICRO_SECOND",
        "default_bandwidth_mbps": 100,
        "switches": [{"id": "SW0", "ports": 8, "domain": 0},
                     {"id": "SW1", "ports": 8, "domain": 0}],
        "end_systems": [{"id": "ES0", "domain": 0},
                        {"id": "ES1", "domain": 0}],
        "links": [
            {"id": "L0", "source": "ES0", "destination": "SW0",
             "sourcePort": 0, "destinationPort": 1, "domain": 0,
             "bandwidth_mbps": 100, "delay": 5.0},
            {"id": "L1", "source": "SW0", "destination": "ES0",
             "sourcePort": 1, "destinationPort": 0, "domain": 0,
             "bandwidth_mbps": 100, "delay": 5.0},
            {"id": "L2", "source": "SW0", "destination": "SW1",
             "sourcePort": 2, "destinationPort": 2, "domain": 0,
             "bandwidth_mbps": 1000, "delay": 30.0},
            {"id": "L3", "source": "SW1", "destination": "SW0",
             "sourcePort": 2, "destinationPort": 2, "domain": 0,
             "bandwidth_mbps": 1000, "delay": 30.0},
            {"id": "L4", "source": "SW1", "destination": "ES1",
             "sourcePort": 1, "destinationPort": 0, "domain": 0,
             "bandwidth_mbps": 100, "delay": 5.0},
            {"id": "L5", "source": "ES1", "destination": "SW1",
             "sourcePort": 0, "destinationPort": 1, "domain": 0,
             "bandwidth_mbps": 100, "delay": 5.0},
        ],
    }


def three_switch_topology():
    """ES0 -- SW0 -- SW1 -- SW2 -- ES1 (3 switches, forces 4 hops)."""
    return {
        "delay_units": "MICRO_SECOND",
        "default_bandwidth_mbps": 100,
        "switches": [{"id": f"SW{i}", "ports": 8, "domain": 0} for i in range(3)],
        "end_systems": [{"id": "ES0", "domain": 0},
                        {"id": "ES1", "domain": 0}],
        "links": [
            {"id": "L0", "source": "ES0", "destination": "SW0",
             "sourcePort": 0, "destinationPort": 1, "domain": 0,
             "bandwidth_mbps": 100, "delay": 5.0},
            {"id": "L1", "source": "SW0", "destination": "ES0",
             "sourcePort": 1, "destinationPort": 0, "domain": 0,
             "bandwidth_mbps": 100, "delay": 5.0},
            {"id": "L2", "source": "SW0", "destination": "SW1",
             "sourcePort": 2, "destinationPort": 2, "domain": 0,
             "bandwidth_mbps": 1000, "delay": 30.0},
            {"id": "L3", "source": "SW1", "destination": "SW0",
             "sourcePort": 2, "destinationPort": 2, "domain": 0,
             "bandwidth_mbps": 1000, "delay": 30.0},
            {"id": "L4", "source": "SW1", "destination": "SW2",
             "sourcePort": 3, "destinationPort": 2, "domain": 0,
             "bandwidth_mbps": 1000, "delay": 30.0},
            {"id": "L5", "source": "SW2", "destination": "SW1",
             "sourcePort": 2, "destinationPort": 3, "domain": 0,
             "bandwidth_mbps": 1000, "delay": 30.0},
            {"id": "L6", "source": "SW2", "destination": "ES1",
             "sourcePort": 1, "destinationPort": 0, "domain": 0,
             "bandwidth_mbps": 100, "delay": 5.0},
            {"id": "L7", "source": "ES1", "destination": "SW2",
             "sourcePort": 0, "destinationPort": 1, "domain": 0,
             "bandwidth_mbps": 100, "delay": 5.0},
        ],
    }


def shortest_path(topology, src, dst):
    """BFS shortest path; returns list of (node, egress_port) pairs ending at dst."""
    adj = defaultdict(list)
    for l in topology['links']:
        adj[l['source']].append((l['destination'], l['sourcePort']))

    # BFS
    from collections import deque
    q = deque([(src, [(src, None)])])
    visited = {src}
    while q:
        node, path = q.popleft()
        if node == dst:
            return path
        for nxt, port in adj[node]:
            if nxt in visited:
                continue
            visited.add(nxt)
            new_path = path[:-1] + [(node, port)] + [(nxt, None)]
            q.append((nxt, new_path))
    return None


def make_case(case_dir, topology, stream_specs):
    """stream_specs: list of dicts with keys: id, name, src, dst, PCP, size, period, deadline."""
    streams = []
    routes = []
    for spec in stream_specs:
        streams.append({
            "id": spec['id'],
            "name": spec.get('name', f"Stream{spec['id']}"),
            "source": spec['src'],
            "destinations": [{"id": spec['dst'], "deadline": spec['deadline']}],
            "type": "ISOCHRONOUS",
            "PCP": spec['PCP'],
            "size": spec['size'],
            "period": spec['period'],
            "redundancy": 0,
        })
        path = shortest_path(topology, spec['src'], spec['dst'])
        # Last hop's port is irrelevant (terminal); set to 0.
        path = [{"node": n, "port": p if p is not None else 0} for n, p in path]
        routes.append({
            "flow_id": spec['id'],
            "paths": [path],
            "min_e2e_delay": float(spec['period'] * 2),
        })

    os.makedirs(case_dir, exist_ok=True)
    with open(os.path.join(case_dir, 'topology.json'), 'w') as f:
        json.dump({"topology": topology}, f, indent=2)
    with open(os.path.join(case_dir, 'streams.json'), 'w') as f:
        json.dump({"delay_units": "MICRO_SECOND", "streams": streams}, f, indent=2)
    with open(os.path.join(case_dir, 'routes.json'), 'w') as f:
        json.dump({"delay_units": "MICRO_SECOND", "routes": routes}, f, indent=2)
    print(f"Wrote {case_dir} ({len(streams)} streams)")


def case_low():
    """6 streams, ~25% utilization on edge links."""
    topo = two_switch_topology()
    specs = [
        # PCP 2 (Class A): 2 streams
        {'id': 0, 'src': 'ES0', 'dst': 'ES1', 'PCP': 2, 'size': 500, 'period': 2000, 'deadline': 2000},
        {'id': 1, 'src': 'ES1', 'dst': 'ES0', 'PCP': 2, 'size': 500, 'period': 2000, 'deadline': 2000},
        # PCP 1 (Class B): 2 streams
        {'id': 2, 'src': 'ES0', 'dst': 'ES1', 'PCP': 1, 'size': 600, 'period': 4000, 'deadline': 4000},
        {'id': 3, 'src': 'ES1', 'dst': 'ES0', 'PCP': 1, 'size': 600, 'period': 4000, 'deadline': 4000},
        # PCP 0 (BE): 2 streams
        {'id': 4, 'src': 'ES0', 'dst': 'ES1', 'PCP': 0, 'size': 800, 'period': 4000, 'deadline': 4000},
        {'id': 5, 'src': 'ES1', 'dst': 'ES0', 'PCP': 0, 'size': 800, 'period': 4000, 'deadline': 4000},
    ]
    make_case(os.path.join(HERE, 'case_low'), topo, specs)


def case_med():
    """Asymmetric: heavy Class A, sparse Class B (showcases proportional slope)."""
    topo = three_switch_topology()
    specs = [
        # 6 Class A (dense)
        {'id': 0, 'src': 'ES0', 'dst': 'ES1', 'PCP': 2, 'size': 1000, 'period': 1000, 'deadline': 1000},
        {'id': 1, 'src': 'ES1', 'dst': 'ES0', 'PCP': 2, 'size': 1000, 'period': 1000, 'deadline': 1000},
        {'id': 2, 'src': 'ES0', 'dst': 'ES1', 'PCP': 2, 'size': 800, 'period': 1000, 'deadline': 1000},
        {'id': 3, 'src': 'ES1', 'dst': 'ES0', 'PCP': 2, 'size': 800, 'period': 1000, 'deadline': 1000},
        {'id': 4, 'src': 'ES0', 'dst': 'ES1', 'PCP': 2, 'size': 600, 'period': 1000, 'deadline': 1000},
        {'id': 5, 'src': 'ES1', 'dst': 'ES0', 'PCP': 2, 'size': 600, 'period': 1000, 'deadline': 1000},
        # 2 Class B (sparse)
        {'id': 6, 'src': 'ES0', 'dst': 'ES1', 'PCP': 1, 'size': 400, 'period': 4000, 'deadline': 4000},
        {'id': 7, 'src': 'ES1', 'dst': 'ES0', 'PCP': 1, 'size': 400, 'period': 4000, 'deadline': 4000},
        # 2 BE
        {'id': 8, 'src': 'ES0', 'dst': 'ES1', 'PCP': 0, 'size': 900, 'period': 1000, 'deadline': 1000},
        {'id': 9, 'src': 'ES1', 'dst': 'ES0', 'PCP': 0, 'size': 900, 'period': 1000, 'deadline': 1000},
    ]
    make_case(os.path.join(HERE, 'case_med'), topo, specs)


def case_high():
    """14 streams, ~80% utilization on edge links, 4-hop."""
    topo = three_switch_topology()
    specs = [
        # Class A: 5 streams
        {'id': 0, 'src': 'ES0', 'dst': 'ES1', 'PCP': 2, 'size': 1200, 'period': 1000, 'deadline': 1000},
        {'id': 1, 'src': 'ES1', 'dst': 'ES0', 'PCP': 2, 'size': 1200, 'period': 1000, 'deadline': 1000},
        {'id': 2, 'src': 'ES0', 'dst': 'ES1', 'PCP': 2, 'size': 900, 'period': 1000, 'deadline': 1000},
        {'id': 3, 'src': 'ES1', 'dst': 'ES0', 'PCP': 2, 'size': 900, 'period': 1000, 'deadline': 1000},
        {'id': 4, 'src': 'ES0', 'dst': 'ES1', 'PCP': 2, 'size': 600, 'period': 2000, 'deadline': 2000},
        # Class B: 5 streams
        {'id': 5, 'src': 'ES1', 'dst': 'ES0', 'PCP': 1, 'size': 1100, 'period': 1000, 'deadline': 1000},
        {'id': 6, 'src': 'ES0', 'dst': 'ES1', 'PCP': 1, 'size': 1100, 'period': 1000, 'deadline': 1000},
        {'id': 7, 'src': 'ES1', 'dst': 'ES0', 'PCP': 1, 'size': 800, 'period': 2000, 'deadline': 2000},
        {'id': 8, 'src': 'ES0', 'dst': 'ES1', 'PCP': 1, 'size': 800, 'period': 2000, 'deadline': 2000},
        {'id': 9, 'src': 'ES1', 'dst': 'ES0', 'PCP': 1, 'size': 600, 'period': 2000, 'deadline': 2000},
        # BE: 4 streams (these get squeezed in SP, protected in CBS)
        {'id': 10, 'src': 'ES0', 'dst': 'ES1', 'PCP': 0, 'size': 1000, 'period': 2000, 'deadline': 2000},
        {'id': 11, 'src': 'ES1', 'dst': 'ES0', 'PCP': 0, 'size': 1000, 'period': 2000, 'deadline': 2000},
        {'id': 12, 'src': 'ES0', 'dst': 'ES1', 'PCP': 0, 'size': 700, 'period': 1000, 'deadline': 1000},
        {'id': 13, 'src': 'ES1', 'dst': 'ES0', 'PCP': 0, 'size': 700, 'period': 1000, 'deadline': 1000},
    ]
    make_case(os.path.join(HERE, 'case_high'), topo, specs)


if __name__ == '__main__':
    case_low()
    case_med()
    case_high()
