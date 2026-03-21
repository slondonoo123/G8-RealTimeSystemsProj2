import heapq
import json
import matplotlib.pyplot as plt
import numpy as np

CBS_PCPS = [2, 1]  # CBS-eligible priority classes (AVB A, AVB B)

# ==========================================
# 1. DATA STRUCTURES
# ==========================================
class Frame:
    def __init__(self, stream_id, size_bytes, pcp, generation_time, path):
        self.stream_id = stream_id
        self.size_bytes = size_bytes
        self.pcp = pcp
        self.generation_time = generation_time
        self.path = path
        self.current_hop_index = 0

class OutputPort:
    def __init__(self, port_id, bandwidth, is_cbs=False):
        self.port_id = port_id
        self.bandwidth = bandwidth
        self.is_cbs = is_cbs

        # Queues: dictionary mapping PCP to a list of Frames
        self.queues = {pcp: [] for pcp in range(8)}

        # State variables
        self.is_transmitting = False
        self.transmitting_pcp = None

        # Per-queue CBS credit state (independent for each CBS class)
        self.credits = {pcp: 0.0 for pcp in CBS_PCPS}
        self.idle_slope = 0.5   # idleSlope = 0.5 (as per assignment)
        self.send_slope = 0.5   # sendSlope = 0.5 (as per assignment)
        self.last_credit_update = 0.0
        self.waiting_for_credit = {pcp: False for pcp in CBS_PCPS}

    def update_credit(self, now):
        if not self.is_cbs:
            return

        delta_t = now - self.last_credit_update
        if delta_t <= 0:
            return

        for pcp in CBS_PCPS:
            if self.is_transmitting and self.transmitting_pcp == pcp:
                # This CBS queue is the one transmitting: credit decreases
                self.credits[pcp] -= self.send_slope * delta_t
            else:
                has_frames = len(self.queues[pcp]) > 0
                if has_frames or self.credits[pcp] < 0:
                    # Queue waiting or recovering negative credit
                    self.credits[pcp] += self.idle_slope * delta_t

                # IEEE 802.1Qav: reset credit to 0 when queue is empty and credit > 0
                if not has_frames and self.credits[pcp] > 0:
                    self.credits[pcp] = 0.0

                # Cap at 0 if port is idle (should have started transmitting)
                if has_frames and not self.is_transmitting and self.credits[pcp] > 0:
                    self.credits[pcp] = 0.0

            # Floating point cleanup
            if abs(self.credits[pcp]) < 1e-9:
                self.credits[pcp] = 0.0

        self.last_credit_update = now

# ==========================================
# 2. THE SIMULATOR ENGINE
# ==========================================
class TSNSimulator:
    def __init__(self):
        self.time = 0.0
        self.event_queue = []       # Heap for discrete events
        self.completed_frames = []  # Store end-to-end delays here
        self.ports = {}             # (NodeID, PortID) -> OutputPort
        self.event_id = 0           # Tie-breaker for heap ordering

    def schedule_event(self, timestamp, event_type, data):
        self.event_id += 1
        heapq.heappush(self.event_queue, (timestamp, self.event_id, event_type, data))

    def run(self, max_time):
        """The main Event Loop."""
        while self.event_queue and self.time < max_time:
            event_time, _, event_type, data = heapq.heappop(self.event_queue)
            self.time = event_time

            if event_type == "GENERATE_FRAME":
                self.handle_generate_frame(data)
            elif event_type == "ENQUEUE":
                self.handle_enqueue(data)
            elif event_type == "FINISH_TRANSMISSION":
                self.handle_finish_transmission(data)
            elif event_type == "CREDIT_ZERO":
                self.handle_credit_zero(data)

    # ==========================================
    # 3. EVENT HANDLERS
    # ==========================================
    def handle_generate_frame(self, data):
        stream = data['stream']

        # Create the Frame object
        frame = Frame(stream['id'], stream['size'], stream['PCP'], self.time, data['route'])

        # Schedule the next frame generation (Periodic)
        next_gen_time = self.time + stream['period']
        self.schedule_event(next_gen_time, "GENERATE_FRAME", data)

        # Send this frame to the first output port immediately
        first_hop = frame.path[0]
        self.schedule_event(self.time, "ENQUEUE", {
            'frame': frame, 'node': first_hop['node'], 'port': first_hop['port']
        })

    def handle_enqueue(self, data):
        frame = data['frame']
        port_key = (data['node'], data['port'])

        # Destination reached: the last hop in the path is the destination node
        if frame.current_hop_index >= len(frame.path) - 1:
            response_time = self.time - frame.generation_time
            self.completed_frames.append({'stream_id': frame.stream_id, 'rt': response_time})
            return

        # Fallback: port not in topology (shouldn't happen with correct routes)
        if port_key not in self.ports:
            response_time = self.time - frame.generation_time
            self.completed_frames.append({'stream_id': frame.stream_id, 'rt': response_time})
            return

        port = self.ports[port_key]

        # Update CBS credit BEFORE changing queue state
        port.update_credit(self.time)

        # Put frame in the correct priority queue using its PCP
        port.queues[frame.pcp].append(frame)

        # Try to start transmitting if the port is idle
        self.try_dequeue(port)

    def try_dequeue(self, port):
        if port.is_transmitting:
            return

        port.update_credit(self.time)
        selected_pcp = None

        for pcp in range(7, -1, -1):
            if len(port.queues[pcp]) > 0:
                if port.is_cbs and pcp in CBS_PCPS:
                    # CBS queue: check per-queue credit
                    if port.credits[pcp] >= -1e-9:
                        selected_pcp = pcp
                        break
                    else:
                        # Schedule credit recovery event if not already pending
                        if not port.waiting_for_credit[pcp]:
                            time_to_zero = abs(port.credits[pcp]) / port.idle_slope
                            self.schedule_event(
                                self.time + time_to_zero, "CREDIT_ZERO",
                                {'port': port, 'pcp': pcp}
                            )
                            port.waiting_for_credit[pcp] = True
                        # CBS blocked — check lower priorities
                        continue
                else:
                    selected_pcp = pcp
                    break

        if selected_pcp is not None:
            frame = port.queues[selected_pcp].pop(0)
            port.is_transmitting = True
            port.transmitting_pcp = selected_pcp

            tx_time = (frame.size_bytes * 8) / port.bandwidth
            self.schedule_event(
                self.time + tx_time, "FINISH_TRANSMISSION",
                {'frame': frame, 'port': port}
            )

    def handle_finish_transmission(self, data):
        frame = data['frame']
        port = data['port']

        # Update credit and free the port
        port.update_credit(self.time)
        port.is_transmitting = False
        port.transmitting_pcp = None

        # Move frame to next hop
        frame.current_hop_index += 1
        if frame.current_hop_index < len(frame.path):
            next_hop = frame.path[frame.current_hop_index]
            self.schedule_event(self.time, "ENQUEUE", {
                'frame': frame, 'node': next_hop['node'], 'port': next_hop['port']
            })
        else:
            # DESTINATION REACHED! Record metrics.
            response_time = self.time - frame.generation_time
            self.completed_frames.append({'stream_id': frame.stream_id, 'rt': response_time})

        # See if there's another frame waiting to go
        self.try_dequeue(port)

    def handle_credit_zero(self, data):
        port = data['port']
        pcp = data['pcp']
        # The credit for this queue has recovered to 0. Try to dequeue again.
        port.waiting_for_credit[pcp] = False
        self.try_dequeue(port)


# ==========================================
# 4. SETUP & HELPERS
# ==========================================
def setup_simulator(topology, streams, routes, is_cbs=False):
    sim = TSNSimulator()

    # Create Output Ports for every link in the topology
    for link in topology['links']:
        port = OutputPort(link['sourcePort'], link['bandwidth_mbps'], is_cbs=is_cbs)
        sim.ports[(link['source'], link['sourcePort'])] = port

    # Schedule the first frame generation for all streams at time 0.0
    route_dict = {r['flow_id']: r for r in routes}
    for stream in streams:
        route = route_dict.get(stream['id'])
        if not route:
            continue
        sim.schedule_event(0.0, "GENERATE_FRAME", {
            'stream': stream,
            'route': route['paths'][0]
        })

    return sim


def extract_max_rts(sim):
    """Extract the maximum observed response time per stream."""
    wcrts = {}
    for record in sim.completed_frames:
        s_id = record['stream_id']
        rt = record['rt']
        if s_id not in wcrts or rt > wcrts[s_id]:
            wcrts[s_id] = rt
    return wcrts


def load_data():
    with open('test-case-1-topology.json') as f:
        topology = json.load(f)['topology']
    with open('test-case-1-streams.json') as f:
        streams = json.load(f)['streams']
    with open('test-case-1-routes.json') as f:
        routes = json.load(f)['routes']
    return topology, streams, routes


# ==========================================
# 5. MAIN
# ==========================================
if __name__ == '__main__':
    topology, streams_data, routes = load_data()

    # ------------------------------------------
    # 1. CBS SIMULATION
    # ------------------------------------------
    print("Running CBS simulation...")
    sim_cbs = setup_simulator(topology, streams_data, routes, is_cbs=True)
    sim_cbs.run(max_time=20000.0)
    cbs_wcrts = extract_max_rts(sim_cbs)
    print("CBS simulation complete.")

    # ------------------------------------------
    # 2. STRICT PRIORITY SIMULATION
    # ------------------------------------------
    print("\nRunning Strict Priority simulation...")
    sim_sp = setup_simulator(topology, streams_data, routes, is_cbs=False)
    sim_sp.run(max_time=20000.0)
    sp_wcrts = extract_max_rts(sim_sp)
    print("SP simulation complete.")

    # ------------------------------------------
    # 3. ANALYTICAL WCRT (CBS - Cao et al.)
    # ------------------------------------------
    from run_demo import calculate_end_to_end_WCRT

    analytical_wcrts = {}
    for stream in streams_data:
        sid = stream['id']
        analytical_wcrts[sid] = calculate_end_to_end_WCRT(
            sid, topology, streams_data, routes, verbose=False
        )

    # ------------------------------------------
    # 4. COMPARISON TABLE
    # ------------------------------------------
    stream_ids = sorted(set(list(cbs_wcrts.keys()) + list(sp_wcrts.keys())))

    print("\n" + "=" * 78)
    print(" COMPARISON: Analytical (CBS) vs Simulated CBS vs Simulated SP")
    print("=" * 78)
    print(f" {'Stream':>6} | {'PCP':>3} | {'Analytical':>14} | {'Sim CBS':>12} | {'Sim SP':>12} | {'Anal>=Sim?':>10}")
    print("-" * 78)

    for sid in stream_ids:
        pcp = next(s['PCP'] for s in streams_data if s['id'] == sid)
        anal = analytical_wcrts.get(sid)
        cbs = cbs_wcrts.get(sid, 0)
        sp = sp_wcrts.get(sid, 0)

        if anal is not None:
            check = "Yes" if anal >= cbs - 1e-6 else "NO!"
            print(f" {sid:>6} |  {pcp:>2} | {anal:>10.2f} µs | {cbs:>8.2f} µs | {sp:>8.2f} µs | {check:>10}")
        else:
            print(f" {sid:>6} |  {pcp:>2} | {'N/A (BE)':>14} | {cbs:>8.2f} µs | {sp:>8.2f} µs | {'N/A':>10}")

    # Highlight CBS benefit for Best Effort
    be_streams = [s for s in streams_data if s['PCP'] == 0]
    if be_streams:
        print("\n--- CBS Impact on Best Effort (PCP 0) ---")
        for s in be_streams:
            sid = s['id']
            cbs_rt = cbs_wcrts.get(sid, 0)
            sp_rt = sp_wcrts.get(sid, 0)
            if sp_rt > 0:
                reduction = ((sp_rt - cbs_rt) / sp_rt) * 100
                print(f"  Stream {sid}: CBS = {cbs_rt:.2f} µs, SP = {sp_rt:.2f} µs "
                      f"({'CBS reduces by' if reduction > 0 else 'CBS increases by'} {abs(reduction):.1f}%)")

    # ------------------------------------------
    # 5. COMPARISON CHART
    # ------------------------------------------
    x = np.arange(len(stream_ids))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 6))

    cbs_vals = [cbs_wcrts.get(sid, 0) for sid in stream_ids]
    sp_vals = [sp_wcrts.get(sid, 0) for sid in stream_ids]

    # Bars for simulated results
    rects_cbs = ax.bar(x - width / 2, cbs_vals, width,
                       label='CBS Simulated', color='#1f77b4', edgecolor='black')
    rects_sp = ax.bar(x + width / 2, sp_vals, width,
                      label='SP Simulated', color='#ff7f0e', edgecolor='black')

    # Analytical markers (CBS classes only — AVB A and AVB B)
    anal_plotted = False
    for i, sid in enumerate(stream_ids):
        anal = analytical_wcrts.get(sid)
        if anal is not None:
            ax.scatter(i - width / 2, anal, color='red', marker='v', s=100, zorder=5,
                       label='CBS Analytical (WCD)' if not anal_plotted else None)
            anal_plotted = True

    ax.set_xlabel('Stream ID (Priority: High → Low)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Max Response Time (µs)', fontsize=12, fontweight='bold')
    ax.set_title('CBS vs SP: Simulated Response Times & Analytical WCD', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([
        f"Str {sid}\n(PCP {next(s['PCP'] for s in streams_data if s['id'] == sid)})"
        for sid in stream_ids
    ])
    ax.legend(fontsize=11)
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    # Value labels on bars
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{height:.1f}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=8, rotation=45)

    autolabel(rects_cbs)
    autolabel(rects_sp)

    fig.tight_layout()
    plt.savefig('cbs_vs_sp_comparison.png', dpi=300)
    print("\nChart saved to cbs_vs_sp_comparison.png")
    plt.show()
