"""Discrete-event simulator for TSN with optional CBS shaping."""
import heapq

from .slope import CBS_PCPS, SlopeConfig, equal_split


class Frame:
    __slots__ = ('stream_id', 'size_bytes', 'pcp', 'generation_time',
                 'path', 'current_hop_index')

    def __init__(self, stream_id, size_bytes, pcp, generation_time, path):
        self.stream_id = stream_id
        self.size_bytes = size_bytes
        self.pcp = pcp
        self.generation_time = generation_time
        self.path = path
        self.current_hop_index = 0


class OutputPort:
    def __init__(self, port_id, bandwidth, slope, port_key, is_cbs=False):
        self.port_id = port_id
        self.bandwidth = bandwidth
        self.is_cbs = is_cbs
        self.port_key = port_key

        self.queues = {pcp: [] for pcp in range(8)}
        self.is_transmitting = False
        self.transmitting_pcp = None

        # Per-class idleSlope as a fraction of bandwidth, then sendSlope = 1 - idle.
        # Slopes here are dimensionless rates (credit per unit time, normalised
        # so transmission of 1 us at rate 1.0 = 1 unit of credit). This matches
        # the original simulator's convention with idle = send = 0.5.
        self.idle_slope = {p: slope.get(p, port_key) for p in CBS_PCPS}
        self.send_slope = {p: 1.0 - self.idle_slope[p] for p in CBS_PCPS}
        self.credits = {p: 0.0 for p in CBS_PCPS}
        self.last_credit_update = 0.0
        self.waiting_for_credit = {p: False for p in CBS_PCPS}

    def update_credit(self, now):
        if not self.is_cbs:
            return
        delta = now - self.last_credit_update
        if delta <= 0:
            return
        for pcp in CBS_PCPS:
            if self.is_transmitting and self.transmitting_pcp == pcp:
                self.credits[pcp] -= self.send_slope[pcp] * delta
            else:
                has_frames = bool(self.queues[pcp])
                if has_frames or self.credits[pcp] < 0:
                    self.credits[pcp] += self.idle_slope[pcp] * delta
                # 802.1Qav: clear positive credit when queue is empty
                if not has_frames and self.credits[pcp] > 0:
                    self.credits[pcp] = 0.0
            if abs(self.credits[pcp]) < 1e-9:
                self.credits[pcp] = 0.0
        self.last_credit_update = now


class TSNSimulator:
    def __init__(self):
        self.time = 0.0
        self.event_queue = []
        self.completed_frames = []
        self.ports = {}
        self.event_id = 0

    def schedule_event(self, ts, etype, data):
        self.event_id += 1
        heapq.heappush(self.event_queue, (ts, self.event_id, etype, data))

    def run(self, max_time):
        while self.event_queue and self.time < max_time:
            t, _, etype, data = heapq.heappop(self.event_queue)
            self.time = t
            if etype == "GENERATE_FRAME":
                self._on_generate(data)
            elif etype == "ENQUEUE":
                self._on_enqueue(data)
            elif etype == "FINISH_TRANSMISSION":
                self._on_finish(data)
            elif etype == "CREDIT_ZERO":
                self._on_credit_zero(data)

    def _on_generate(self, data):
        stream = data['stream']
        frame = Frame(stream['id'], stream['size'], stream['PCP'],
                      self.time, data['route'])
        self.schedule_event(self.time + stream['period'], "GENERATE_FRAME", data)
        first = frame.path[0]
        self.schedule_event(self.time, "ENQUEUE",
                            {'frame': frame, 'node': first['node'], 'port': first['port']})

    def _on_enqueue(self, data):
        frame = data['frame']
        key = (data['node'], data['port'])
        if frame.current_hop_index >= len(frame.path) - 1:
            self.completed_frames.append(
                {'stream_id': frame.stream_id, 'rt': self.time - frame.generation_time})
            return
        if key not in self.ports:
            self.completed_frames.append(
                {'stream_id': frame.stream_id, 'rt': self.time - frame.generation_time})
            return
        port = self.ports[key]
        port.update_credit(self.time)
        port.queues[frame.pcp].append(frame)
        self._try_dequeue(port)

    def _try_dequeue(self, port):
        if port.is_transmitting:
            return
        port.update_credit(self.time)
        selected = None
        for pcp in range(7, -1, -1):
            if not port.queues[pcp]:
                continue
            if port.is_cbs and pcp in CBS_PCPS:
                if port.credits[pcp] >= -1e-9:
                    selected = pcp
                    break
                if not port.waiting_for_credit[pcp]:
                    time_to_zero = abs(port.credits[pcp]) / port.idle_slope[pcp]
                    self.schedule_event(self.time + time_to_zero, "CREDIT_ZERO",
                                        {'port': port, 'pcp': pcp})
                    port.waiting_for_credit[pcp] = True
                continue
            selected = pcp
            break

        if selected is not None:
            frame = port.queues[selected].pop(0)
            port.is_transmitting = True
            port.transmitting_pcp = selected
            tx = (frame.size_bytes * 8) / port.bandwidth
            self.schedule_event(self.time + tx, "FINISH_TRANSMISSION",
                                {'frame': frame, 'port': port})

    def _on_finish(self, data):
        frame, port = data['frame'], data['port']
        port.update_credit(self.time)
        port.is_transmitting = False
        port.transmitting_pcp = None
        frame.current_hop_index += 1
        if frame.current_hop_index < len(frame.path):
            nxt = frame.path[frame.current_hop_index]
            self.schedule_event(self.time, "ENQUEUE",
                                {'frame': frame, 'node': nxt['node'], 'port': nxt['port']})
        else:
            self.completed_frames.append(
                {'stream_id': frame.stream_id, 'rt': self.time - frame.generation_time})
        self._try_dequeue(port)

    def _on_credit_zero(self, data):
        port, pcp = data['port'], data['pcp']
        port.waiting_for_credit[pcp] = False
        self._try_dequeue(port)


def setup_simulator(topology, streams, routes, slope=None, is_cbs=False):
    if slope is None:
        slope = equal_split()
    sim = TSNSimulator()
    for link in topology['links']:
        key = (link['source'], link['sourcePort'])
        sim.ports[key] = OutputPort(link['sourcePort'], link['bandwidth_mbps'],
                                    slope, key, is_cbs=is_cbs)

    route_dict = {r['flow_id']: r for r in routes}
    for stream in streams:
        route = route_dict.get(stream['id'])
        if not route:
            continue
        sim.schedule_event(0.0, "GENERATE_FRAME",
                           {'stream': stream, 'route': route['paths'][0]})
    return sim


def extract_max_rts(sim):
    wcrts = {}
    for r in sim.completed_frames:
        sid, rt = r['stream_id'], r['rt']
        if sid not in wcrts or rt > wcrts[sid]:
            wcrts[sid] = rt
    return wcrts
