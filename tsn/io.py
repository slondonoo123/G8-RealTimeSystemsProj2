"""JSON loading for TSN test cases."""
import json
import os


def load_data(case_dir=None, prefix=None):
    """Load topology, streams, routes from a directory.

    Two layouts supported:
      1. case_dir contains topology.json, streams.json, routes.json
      2. case_dir contains <prefix>-topology.json etc. (or files at repo root
         with prefix='test-case-1')
    """
    if case_dir is None:
        case_dir = '.'

    candidates = []
    if prefix:
        candidates.append((
            f'{prefix}-topology.json',
            f'{prefix}-streams.json',
            f'{prefix}-routes.json',
        ))
    candidates.append(('topology.json', 'streams.json', 'routes.json'))

    for topo_name, str_name, rt_name in candidates:
        topo_path = os.path.join(case_dir, topo_name)
        if os.path.exists(topo_path):
            with open(topo_path) as f:
                topology = json.load(f)['topology']
            with open(os.path.join(case_dir, str_name)) as f:
                streams = json.load(f)['streams']
            with open(os.path.join(case_dir, rt_name)) as f:
                routes = json.load(f)['routes']
            return topology, streams, routes

    raise FileNotFoundError(
        f"No topology JSON found in {case_dir!r}. "
        f"Expected topology.json or <prefix>-topology.json."
    )
