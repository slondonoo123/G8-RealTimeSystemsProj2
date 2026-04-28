"""Analytical end-to-end WCRT for TSN CBS streams (Cao et al. 2016)."""
from .slope import SlopeConfig, equal_split


def calculate_transmission_time(size_bytes, bandwidth_mbps):
    """Bytes -> microseconds at link bandwidth (Mbps)."""
    return (size_bytes * 8) / bandwidth_mbps


def get_link(topology, node_id, port):
    for link in topology['links']:
        if link['source'] == node_id and link['sourcePort'] == port:
            return link
    return None


def get_streams_on_link(all_streams, routes, link):
    streams_on_link = []
    route_dict = {r['flow_id']: r for r in routes}
    for stream in all_streams:
        route = route_dict.get(stream['id'])
        if not route:
            continue
        for hop in route['paths'][0][:-1]:
            if hop['node'] == link['source'] and hop['port'] == link['sourcePort']:
                streams_on_link.append(stream)
                break
    return streams_on_link


def group_streams_by_priority(target, streams_on_link):
    same, higher, lower = [], [], []
    for s in streams_on_link:
        if s['id'] == target['id']:
            continue
        if s['PCP'] == target['PCP']:
            same.append(s)
        elif s['PCP'] > target['PCP']:
            higher.append(s)
        else:
            lower.append(s)
    return same, higher, lower


def calculate_SPI(target, same_priority_streams, bandwidth, slope, port_key):
    """Same-Priority Interference (Cao et al.).

    For each same-class stream j: C_j * (1 + alpha) where
    alpha = sendSlope/idleSlope of the target's class.
    """
    if not same_priority_streams:
        return 0.0
    alpha = slope.alpha(target['PCP'], port_key)
    return sum(
        calculate_transmission_time(s['size'], bandwidth) * (1 + alpha)
        for s in same_priority_streams
    )


def calculate_LPI(lower_priority_streams, bandwidth):
    """Lower-Priority blocking: largest non-preemptive lower-class frame."""
    if not lower_priority_streams:
        return 0.0
    return max(
        calculate_transmission_time(s['size'], bandwidth)
        for s in lower_priority_streams
    )


def calculate_HPI(target, streams_on_link, bandwidth, slope, port_key):
    """Higher-Priority Interference, computed per higher class.

    For each higher class h: contribution = LPI_h * alpha_h + max(C_h),
    where LPI_h is *that class's own* blocking by frames with PCP < h
    on this link, and alpha_h = sendSlope_h / idleSlope_h.

    This generalises the original equal-split formula and is correct
    when classes have different idleSlope settings.
    """
    target_pcp = target['PCP']
    higher = [s for s in streams_on_link
              if s['PCP'] > target_pcp and s['id'] != target['id']]
    if not higher:
        return 0.0

    by_class = {}
    for s in higher:
        by_class.setdefault(s['PCP'], []).append(s)

    hpi = 0.0
    for h_pcp, h_streams in by_class.items():
        h_lower = [s for s in streams_on_link if s['PCP'] < h_pcp]
        h_lpi = (max(calculate_transmission_time(s['size'], bandwidth) for s in h_lower)
                 if h_lower else 0.0)
        alpha_h = slope.alpha(h_pcp, port_key)
        c_max = max(calculate_transmission_time(s['size'], bandwidth) for s in h_streams)
        hpi += h_lpi * alpha_h + c_max
    return hpi


def calculate_end_to_end_WCRT(stream_id, topology, streams, routes,
                              slope=None, verbose=True):
    """Analytical end-to-end WCRT in microseconds, or None for BE (PCP 0)."""
    if slope is None:
        slope = equal_split()

    target = next(s for s in streams if s['id'] == stream_id)
    target_route = next(r for r in routes if r['flow_id'] == stream_id)

    if target['PCP'] == 0:
        if verbose:
            print(f"\n--- Stream {stream_id} (PCP 0 - Best Effort) ---")
            print("  Analytical WCRT: N/A (Cao et al. covers AVB classes only)")
        return None

    total = 0.0
    if verbose:
        print(f"\n--- Analyzing Stream {stream_id} "
              f"(PCP {target['PCP']}, Size {target['size']}B) ---")

    path = target_route['paths'][0]
    for i, hop in enumerate(path[:-1]):
        node_id, port = hop['node'], hop['port']
        link = get_link(topology, node_id, port)
        bw = link['bandwidth_mbps']
        port_key = (node_id, port)

        on_link = get_streams_on_link(streams, routes, link)
        same, higher, lower = group_streams_by_priority(target, on_link)

        C_i = calculate_transmission_time(target['size'], bw)
        SPI = calculate_SPI(target, same, bw, slope, port_key)
        LPI = calculate_LPI(lower, bw)
        HPI = calculate_HPI(target, on_link, bw, slope, port_key)

        link_wcrt = SPI + HPI + LPI + C_i

        if verbose:
            print(f"Hop {i+1} ({node_id} -> port {port}):")
            print(f"  - Transmission Time (C_i): {C_i:.2f} us")
            print(f"  - Same-Priority Interf (SPI): {SPI:.2f} us")
            print(f"  - Lower-Priority Block (LPI): {LPI:.2f} us")
            print(f"  - Higher-Priority Interf (HPI): {HPI:.2f} us")
            print(f"  => Total Link WCRT: {link_wcrt:.2f} us\n")

        total += link_wcrt
    return total


def all_wcrts(topology, streams, routes, slope=None, verbose=False):
    return {s['id']: calculate_end_to_end_WCRT(
        s['id'], topology, streams, routes, slope=slope, verbose=verbose)
        for s in streams}
