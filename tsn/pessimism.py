"""Pessimism gap analysis: how loose is the analytical bound vs simulation?"""


def gap(analytical, simulated):
    """Return (absolute_us, percent) gap = analytical - simulated."""
    if analytical is None or simulated is None:
        return None, None
    abs_gap = analytical - simulated
    pct = (abs_gap / analytical * 100.0) if analytical > 0 else 0.0
    return abs_gap, pct


def classify(percent):
    """Bucket a gap percentage into {tight, moderate, loose}."""
    if percent is None:
        return 'n/a'
    if percent < 5:
        return 'tight'
    if percent < 20:
        return 'moderate'
    return 'loose'


def summarise(analytical_dict, simulated_dict, streams):
    """Return list of dicts: [{stream_id, pcp, anal, sim, abs, pct, bucket}, ...]."""
    rows = []
    for s in streams:
        sid = s['id']
        anal = analytical_dict.get(sid)
        sim = simulated_dict.get(sid)
        a_gap, pct = gap(anal, sim)
        rows.append({
            'stream_id': sid,
            'pcp': s['PCP'],
            'analytical': anal,
            'simulated': sim,
            'abs_gap': a_gap,
            'pct_gap': pct,
            'bucket': classify(pct),
        })
    return rows


def histogram(rows):
    """Count rows per bucket (only AVB classes)."""
    h = {'tight': 0, 'moderate': 0, 'loose': 0, 'n/a': 0}
    for r in rows:
        h[r['bucket']] += 1
    return h


def print_table(rows, title="Pessimism gap"):
    print(f"\n--- {title} ---")
    print(f" {'Stream':>6} | {'PCP':>3} | {'Anal (us)':>10} | "
          f"{'Sim (us)':>10} | {'Gap (us)':>10} | {'Gap %':>7} | {'Bucket':>9}")
    print("-" * 72)
    for r in rows:
        if r['analytical'] is None:
            print(f" {r['stream_id']:>6} | {r['pcp']:>3} | "
                  f"{'N/A':>10} | {r['simulated']:>10.2f} | "
                  f"{'N/A':>10} | {'N/A':>7} | {'n/a':>9}")
        else:
            print(f" {r['stream_id']:>6} | {r['pcp']:>3} | "
                  f"{r['analytical']:>10.2f} | {r['simulated']:>10.2f} | "
                  f"{r['abs_gap']:>10.2f} | {r['pct_gap']:>6.1f}% | "
                  f"{r['bucket']:>9}")


def scatter_plot(all_rows_by_case, save_path):
    """Scatter plot: x=analytical, y=simulated, with diagonal reference.

    all_rows_by_case: dict[case_name -> list of summary rows].
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 8))
    cmap = plt.cm.tab10
    max_v = 0
    for i, (case, rows) in enumerate(all_rows_by_case.items()):
        xs, ys = [], []
        for r in rows:
            if r['analytical'] and r['simulated'] is not None:
                xs.append(r['analytical'])
                ys.append(r['simulated'])
        if not xs:
            continue
        ax.scatter(xs, ys, color=cmap(i % 10), label=case, s=50, alpha=0.75,
                   edgecolor='black', linewidth=0.5)
        max_v = max(max_v, max(xs), max(ys))
    if max_v > 0:
        ax.plot([0, max_v], [0, max_v], 'k--', alpha=0.4,
                label='Tight bound (sim = anal)')
    ax.set_xlabel('Analytical WCRT (us)', fontweight='bold')
    ax.set_ylabel('Simulated max RT (us)', fontweight='bold')
    ax.set_title('Pessimism: simulated vs analytical (closer to diagonal = tighter)',
                 fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=300)
    plt.close(fig)
