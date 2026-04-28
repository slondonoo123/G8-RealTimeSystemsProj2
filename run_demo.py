"""Analytical WCRT calculator (CBS, Cao et al. 2016).

Thin CLI wrapper around tsn.analytical. Loads test-case-1-*.json from
the repo root by default; pass --case <dir> to use a generated case.
"""
import argparse

from tsn.analytical import all_wcrts, calculate_end_to_end_WCRT
from tsn.io import load_data
from tsn.slope import equal_split


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', default='.', help='Directory containing JSONs')
    parser.add_argument('--prefix', default='test-case-1',
                        help='Filename prefix when files are at repo root')
    parser.add_argument('--quiet', action='store_true', help='Suppress per-hop trace')
    args = parser.parse_args()

    topology, streams, routes = load_data(args.case, prefix=args.prefix)
    slope = equal_split()

    results = {}
    for stream in streams:
        sid = stream['id']
        results[sid] = calculate_end_to_end_WCRT(
            sid, topology, streams, routes, slope=slope, verbose=not args.quiet)

    print("\n==================================================")
    print(" ANALYTICAL WCRT RESULTS (CBS - Cao et al.)")
    print("==================================================")
    print(f" {'Stream':>8} | {'PCP':>3} | {'Analytical WCRT':>18}")
    print("-" * 40)
    for sid in sorted(results.keys()):
        pcp = next(s['PCP'] for s in streams if s['id'] == sid)
        wcrt = results[sid]
        if wcrt is not None:
            print(f" {sid:>8} |  {pcp:>2} | {wcrt:>14.2f} us")
        else:
            print(f" {sid:>8} |  {pcp:>2} | {'N/A (BE)':>18}")

    if results.get(0) is not None and round(results[0], 1) == 603.2:
        print("\nStream 0 WCRT = 603.2 us - matches expected value.")
    elif results.get(0) is not None:
        print(f"\nStream 0 WCRT = {results[0]:.1f} us "
              f"(expected 603.2 us for the original test case).")


if __name__ == '__main__':
    main()
