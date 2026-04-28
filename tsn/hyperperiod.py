"""Hyperperiod helper: LCM of stream periods."""
from functools import reduce
from math import lcm


def hyperperiod(streams):
    """Return the LCM of all stream periods (microseconds)."""
    periods = [int(s['period']) for s in streams]
    if not periods:
        return 0
    return reduce(lcm, periods)


def simulation_duration(streams, factor=2, min_us=1000):
    """Recommended simulation duration: factor * hyperperiod (>= min_us).

    factor=2 ensures every release-phase alignment occurs at least once
    for periodic streams released synchronously at t=0.
    """
    return max(factor * hyperperiod(streams), min_us)
