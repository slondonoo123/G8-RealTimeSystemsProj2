"""Strict-Priority WCRT analysis (classical non-preemptive RTA).

Per output port, for each stream i:

    R_i^(n+1) = C_i + B_i + sum_{j != i, prio(j) >= prio(i)} ceil(R_i^n / T_j) * C_j

where:
- C_x = transmission time of one frame of stream x on the link.
- B_i = blocking term = max C_k over lower-priority streams on the link
       (a non-preemptive frame in service cannot be displaced).
- Same-priority streams are included on the >= side, modelling FIFO order
  conservatively (every same-priority job that *could* arrive within R_i
  contributes its full C_j).

End-to-end WCRT = sum over hops in the path (an over-approximation that
matches the CBS analytical's per-hop independence).
"""
import math

from .analytical import (calculate_transmission_time, get_link,
                         get_streams_on_link)


def _per_hop_R(target, on_link, bandwidth, max_iter=10000):
    """Fixed-point response time at a single output port."""
    others = [s for s in on_link if s['id'] != target['id']]
    higher_or_eq = [s for s in others if s['PCP'] >= target['PCP']]
    lower = [s for s in others if s['PCP'] < target['PCP']]

    C_i = calculate_transmission_time(target['size'], bandwidth)
    B_i = (max(calculate_transmission_time(s['size'], bandwidth) for s in lower)
           if lower else 0.0)

    R = C_i + B_i
    for _ in range(max_iter):
        interference = 0.0
        for j in higher_or_eq:
            C_j = calculate_transmission_time(j['size'], bandwidth)
            T_j = j['period']
            interference += math.ceil(R / T_j) * C_j
        R_new = C_i + B_i + interference
        if abs(R_new - R) < 1e-9:
            return R_new
        R = R_new
    # Did not converge; treat as infeasible
    return float('inf')


def calculate_SP_WCRT(stream_id, topology, streams, routes):
    """End-to-end SP WCRT (sum of per-hop fixed-point response times).

    Returns the WCRT in microseconds, or float('inf') if any hop is
    infeasible (response time would exceed the period without bound).
    """
    target = next(s for s in streams if s['id'] == stream_id)
    target_route = next(r for r in routes if r['flow_id'] == stream_id)

    total = 0.0
    for hop in target_route['paths'][0][:-1]:
        link = get_link(topology, hop['node'], hop['port'])
        on_link = get_streams_on_link(streams, routes, link)
        R = _per_hop_R(target, on_link, link['bandwidth_mbps'])
        if math.isinf(R):
            return float('inf')
        total += R
    return total


def all_sp_wcrts(topology, streams, routes):
    return {s['id']: calculate_SP_WCRT(s['id'], topology, streams, routes)
            for s in streams}
