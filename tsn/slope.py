"""CBS idleSlope policies.

idleSlope is expressed as a *fraction* of the link bandwidth, so
sendSlope_fraction = 1 - idleSlope_fraction, and Cao's
alpha = sendSlope / idleSlope = (1 - idle) / idle.
"""
from dataclasses import dataclass, field

CBS_PCPS = (2, 1)


@dataclass
class SlopeConfig:
    """Per-PCP idleSlope fractions, optionally per (node, port).

    `default` applies to any PCP not in `idle_slope`.
    `per_port` overrides default for specific output ports.
    """
    idle_slope: dict = field(default_factory=lambda: {2: 0.5, 1: 0.5})
    per_port: dict = field(default_factory=dict)  # (node, port) -> {pcp: fraction}

    def get(self, pcp, port_key=None):
        if port_key is not None and port_key in self.per_port:
            override = self.per_port[port_key]
            if pcp in override:
                return override[pcp]
        return self.idle_slope.get(pcp, 0.5)

    def alpha(self, pcp, port_key=None):
        idle = self.get(pcp, port_key)
        if idle <= 0 or idle >= 1:
            raise ValueError(f"idleSlope must be in (0,1), got {idle}")
        return (1.0 - idle) / idle


def equal_split(pcps=CBS_PCPS):
    """Default policy: idleSlope = 0.5 for every CBS class."""
    return SlopeConfig(idle_slope={p: 0.5 for p in pcps})


def proportional_idle_slope(streams, routes, topology, pcps=CBS_PCPS,
                            cbs_budget=0.95, floor=0.05):
    """Per-port per-class idleSlope normalised to total CBS budget.

    For each output port:
      raw_h = max(utilization_h, floor) for each CBS class h
      idle_h = cbs_budget * raw_h / sum(raw)

    This gives the heavier class a larger idleSlope (tightens its
    alpha = (1-idle)/idle) at the expense of the lighter class. When
    classes are equally loaded the result is close to the equal split.

    `floor` keeps a class from collapsing to zero if it has no traffic
    on a port (so adding traffic later wouldn't divide by zero).
    """
    route_dict = {r['flow_id']: r for r in routes}
    link_bw = {(l['source'], l['sourcePort']): l['bandwidth_mbps']
               for l in topology['links']}

    util = {}
    for s in streams:
        route = route_dict.get(s['id'])
        if not route:
            continue
        for hop in route['paths'][0][:-1]:
            key = (hop['node'], hop['port'])
            bw = link_bw.get(key)
            if bw is None:
                continue
            u = (s['size'] * 8) / s['period'] / bw
            util.setdefault(key, {}).setdefault(s['PCP'], 0.0)
            util[key][s['PCP']] += u

    per_port = {}
    for key, class_util in util.items():
        raw = {p: max(class_util.get(p, 0.0), floor) for p in pcps}
        total = sum(raw.values())
        per_port[key] = {p: cbs_budget * raw[p] / total for p in pcps}
    return SlopeConfig(idle_slope={p: 0.5 for p in pcps}, per_port=per_port)
