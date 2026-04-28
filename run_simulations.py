"""CBS vs SP simulation + analytical comparison.

Thin CLI wrapper around tsn.simulator. Simulation duration is derived
from the system hyperperiod (factor=2 by default), not hardcoded.
"""
import argparse

from tsn.analytical import all_wcrts
from tsn.hyperperiod import hyperperiod, simulation_duration
from tsn.io import load_data
from tsn.simulator import extract_max_rts, setup_simulator
from tsn.slope import equal_split, proportional_idle_slope
from tsn.sp_analytical import all_sp_wcrts


def run_case(case_dir, prefix, policy='equal', factor=2, plot_path=None,
             show_plot=False):
    topology, streams, routes = load_data(case_dir, prefix=prefix)

    H = hyperperiod(streams)
    duration = simulation_duration(streams, factor=factor)
    print(f"Hyperperiod = {H} us; running {factor}x = {duration} us "
          f"(ensures all release-phase alignments).")

    if policy == 'proportional':
        slope = proportional_idle_slope(streams, routes, topology)
    else:
        slope = equal_split()

    print(f"\nRunning CBS simulation (slope policy: {policy})...")
    sim_cbs = setup_simulator(topology, streams, routes, slope=slope, is_cbs=True)
    sim_cbs.run(max_time=duration)
    cbs_wcrts = extract_max_rts(sim_cbs)

    print("Running Strict Priority simulation...")
    sim_sp = setup_simulator(topology, streams, routes, slope=slope, is_cbs=False)
    sim_sp.run(max_time=duration)
    sp_wcrts = extract_max_rts(sim_sp)

    analytical = all_wcrts(topology, streams, routes, slope=slope, verbose=False)
    sp_analytical = all_sp_wcrts(topology, streams, routes)

    stream_ids = sorted(set(list(cbs_wcrts.keys()) + list(sp_wcrts.keys())))

    print("\n" + "=" * 95)
    print(" COMPARISON: Analytical (CBS+SP) vs Simulated CBS vs Simulated SP")
    print("=" * 95)
    print(f" {'Str':>3} | {'PCP':>3} | {'CBS Anal':>10} | {'SP Anal':>10} "
          f"| {'Sim CBS':>10} | {'Sim SP':>10} | {'CBS ok':>6} | {'SP ok':>6}")
    print("-" * 95)
    sound = True
    for sid in stream_ids:
        pcp = next(s['PCP'] for s in streams if s['id'] == sid)
        anal = analytical.get(sid)
        sp_anal = sp_analytical.get(sid)
        cbs = cbs_wcrts.get(sid, 0)
        sp = sp_wcrts.get(sid, 0)

        cbs_a_str = f"{anal:>8.2f}" if anal is not None else f"{'N/A':>8}"
        if sp_anal is None:
            sp_a_str = f"{'N/A':>8}"
        elif sp_anal == float('inf'):
            sp_a_str = f"{'inf':>8}"
        else:
            sp_a_str = f"{sp_anal:>8.2f}"

        cbs_ok = "Yes" if (anal is None or anal >= cbs - 1e-6) else "NO!"
        sp_ok = ("Yes" if (sp_anal == float('inf') or sp_anal >= sp - 1e-6)
                 else "NO!")
        if cbs_ok == "NO!" or sp_ok == "NO!":
            sound = False

        print(f" {sid:>3} |  {pcp:>2} | {cbs_a_str} us | {sp_a_str} us "
              f"| {cbs:>8.2f} us | {sp:>8.2f} us | {cbs_ok:>6} | {sp_ok:>6}")

    be = [s for s in streams if s['PCP'] == 0]
    if be:
        print("\n--- CBS Impact on Best Effort (PCP 0) ---")
        for s in be:
            sid = s['id']
            cbs_rt = cbs_wcrts.get(sid, 0)
            sp_rt = sp_wcrts.get(sid, 0)
            if sp_rt > 0:
                red = ((sp_rt - cbs_rt) / sp_rt) * 100
                verb = 'reduces' if red > 0 else 'increases'
                print(f"  Stream {sid}: CBS={cbs_rt:.2f} us, SP={sp_rt:.2f} us "
                      f"(CBS {verb} by {abs(red):.1f}%)")

    if plot_path or show_plot:
        _plot(stream_ids, streams, cbs_wcrts, sp_wcrts, analytical,
              plot_path, show_plot)
    return analytical, cbs_wcrts, sp_wcrts, sound


def _plot(stream_ids, streams, cbs_wcrts, sp_wcrts, analytical,
          plot_path, show_plot):
    import matplotlib.pyplot as plt
    import numpy as np
    x = np.arange(len(stream_ids))
    width = 0.25
    fig, ax = plt.subplots(figsize=(12, 6))
    cbs_vals = [cbs_wcrts.get(sid, 0) for sid in stream_ids]
    sp_vals = [sp_wcrts.get(sid, 0) for sid in stream_ids]
    rcbs = ax.bar(x - width / 2, cbs_vals, width,
                  label='CBS Simulated', color='#1f77b4', edgecolor='black')
    rsp = ax.bar(x + width / 2, sp_vals, width,
                 label='SP Simulated', color='#ff7f0e', edgecolor='black')
    plotted = False
    for i, sid in enumerate(stream_ids):
        a = analytical.get(sid)
        if a is not None:
            ax.scatter(i - width / 2, a, color='red', marker='v', s=100, zorder=5,
                       label='CBS Analytical (WCD)' if not plotted else None)
            plotted = True
    ax.set_xlabel('Stream ID (Priority: High -> Low)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Max Response Time (us)', fontsize=12, fontweight='bold')
    ax.set_title('CBS vs SP: Simulated Response Times & Analytical WCD',
                 fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([
        f"Str {sid}\n(PCP {next(s['PCP'] for s in streams if s['id'] == sid)})"
        for sid in stream_ids])
    ax.legend(fontsize=11)
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    def label(rects):
        for rect in rects:
            h = rect.get_height()
            ax.annotate(f'{h:.1f}', xy=(rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=8, rotation=45)
    label(rcbs); label(rsp)
    fig.tight_layout()
    if plot_path:
        plt.savefig(plot_path, dpi=300)
        print(f"\nChart saved to {plot_path}")
    if show_plot:
        plt.show()
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', default='.', help='Directory with JSONs')
    parser.add_argument('--prefix', default='test-case-1',
                        help='Filename prefix at repo root')
    parser.add_argument('--policy', choices=['equal', 'proportional'],
                        default='equal')
    parser.add_argument('--factor', type=int, default=2,
                        help='Simulation duration = factor * hyperperiod')
    parser.add_argument('--plot', default='cbs_vs_sp_comparison.png')
    parser.add_argument('--no-show', action='store_true')
    args = parser.parse_args()

    run_case(args.case, args.prefix, policy=args.policy, factor=args.factor,
             plot_path=args.plot, show_plot=not args.no_show)


if __name__ == '__main__':
    main()
