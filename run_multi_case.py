"""Drive multiple test cases; compare slope policies; analyse pessimism.

Usage:
    python run_multi_case.py                # runs every test_cases/case_*/
    python run_multi_case.py --skip-plots   # text only

Exits with non-zero status if any analytical bound is violated by simulation.
"""
import argparse
import os
import sys

from tsn.analytical import all_wcrts
from tsn.hyperperiod import hyperperiod, simulation_duration
from tsn.io import load_data
from tsn.pessimism import histogram, print_table, summarise
from tsn.simulator import extract_max_rts, setup_simulator
from tsn.slope import equal_split, proportional_idle_slope
from tsn.sp_analytical import all_sp_wcrts


def evaluate(case_dir, factor=2):
    topology, streams, routes = load_data(case_dir)
    H = hyperperiod(streams)
    duration = simulation_duration(streams, factor=factor)

    print(f"\n{'#' * 78}\n# Case: {case_dir}")
    print(f"# Streams: {len(streams)}  Hyperperiod: {H} us  "
          f"Sim duration: {duration} us ({factor}x H)")
    print('#' * 78)

    results = {}
    for policy_name, slope in [
        ('equal', equal_split()),
        ('proportional', proportional_idle_slope(streams, routes, topology)),
    ]:
        sim_cbs = setup_simulator(topology, streams, routes,
                                  slope=slope, is_cbs=True)
        sim_cbs.run(max_time=duration)
        cbs_max = extract_max_rts(sim_cbs)

        sim_sp = setup_simulator(topology, streams, routes,
                                 slope=slope, is_cbs=False)
        sim_sp.run(max_time=duration)
        sp_max = extract_max_rts(sim_sp)

        anal = all_wcrts(topology, streams, routes, slope=slope, verbose=False)
        results[policy_name] = (anal, cbs_max, sp_max, slope)

    # SP RTA (independent of slope policy)
    sp_anal = all_sp_wcrts(topology, streams, routes)

    # Side-by-side table
    stream_ids = sorted({sid for s in streams for sid in [s['id']]})
    print(f"\n{'Str':>3} | {'PCP':>3} | "
          f"{'CBS eq':>9} | {'CBS prop':>9} | {'SP RTA':>9} | "
          f"{'Sim CBS':>9} | {'Sim SP':>9}")
    print('-' * 78)
    sound = True
    for sid in stream_ids:
        pcp = next(s['PCP'] for s in streams if s['id'] == sid)
        ae = results['equal'][0].get(sid)
        ap = results['proportional'][0].get(sid)
        sa = sp_anal.get(sid)
        sc = results['equal'][1].get(sid, 0)
        ss = results['equal'][2].get(sid, 0)
        a_str = f"{ae:>9.2f}" if ae is not None else f"{'N/A':>9}"
        p_str = f"{ap:>9.2f}" if ap is not None else f"{'N/A':>9}"
        if sa is None:
            sa_str = f"{'N/A':>9}"
        elif sa == float('inf'):
            sa_str = f"{'inf':>9}"
        else:
            sa_str = f"{sa:>9.2f}"
        print(f"{sid:>3} | {pcp:>3} | {a_str} | {p_str} | {sa_str} | "
              f"{sc:>9.2f} | {ss:>9.2f}")
        if ae is not None and sc > ae + 1e-6:
            sound = False
            print(f"  !! CBS soundness violation: sim ({sc:.2f}) > anal ({ae:.2f})")
        if sa is not None and sa != float('inf') and ss > sa + 1e-6:
            sound = False
            print(f"  !! SP soundness violation: sim ({ss:.2f}) > RTA ({sa:.2f})")

    # Pessimism report (under equal-split policy)
    rows_eq = summarise(results['equal'][0], results['equal'][1], streams)
    print_table(rows_eq, title=f"Pessimism (equal split) - {os.path.basename(case_dir)}")
    h = histogram(rows_eq)
    print(f"  buckets: tight={h['tight']}  moderate={h['moderate']}  loose={h['loose']}")

    # Slope policy comparison: which streams' bounds tighten?
    tightened = []
    for sid in stream_ids:
        ae = results['equal'][0].get(sid)
        ap = results['proportional'][0].get(sid)
        if ae and ap and ap < ae - 1e-6:
            tightened.append((sid, ae, ap))
    if tightened:
        print(f"\n  Proportional slope tightens {len(tightened)} stream(s):")
        for sid, ae, ap in tightened:
            print(f"    Stream {sid}: {ae:.2f} -> {ap:.2f} us "
                  f"({(ae - ap) / ae * 100:.1f}% reduction)")
    else:
        print("\n  Proportional slope did not tighten any bound on this case.")

    return rows_eq, sound


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='test_cases',
                        help='Directory containing case_*/ subdirectories')
    parser.add_argument('--factor', type=int, default=2,
                        help='Sim duration = factor * hyperperiod')
    parser.add_argument('--skip-plots', action='store_true')
    args = parser.parse_args()

    case_dirs = sorted(
        os.path.join(args.root, d) for d in os.listdir(args.root)
        if d.startswith('case_') and
        os.path.isdir(os.path.join(args.root, d)))

    if not case_dirs:
        print(f"No test cases found under {args.root}/case_*/")
        sys.exit(1)

    all_rows = {}
    all_sound = True
    for case in case_dirs:
        rows, sound = evaluate(case, factor=args.factor)
        all_rows[os.path.basename(case)] = rows
        all_sound = all_sound and sound

    # Aggregate scatter plot across cases
    if not args.skip_plots:
        try:
            from tsn.pessimism import scatter_plot
            scatter_plot(all_rows, os.path.join(args.root, 'pessimism_scatter.png'))
            print(f"\nScatter plot: {args.root}/pessimism_scatter.png")
        except ImportError:
            print("\n(matplotlib unavailable - skipping scatter plot)")

    print("\n" + ("=" * 78))
    print(f" Overall soundness: {'OK (all bounds hold)' if all_sound else 'VIOLATED'}")
    print("=" * 78)

    sys.exit(0 if all_sound else 2)


if __name__ == '__main__':
    main()
