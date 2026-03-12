import heapq
import json

class Frame:
    def __init__(self, stream_id, size_bytes, pcp, generation_time, path):
        self.stream_id = stream_id
        self.size_bytes = size_bytes
        self.pcp = pcp                         # Added PCP here!
        self.generation_time = generation_time 
        self.path = path                       
        self.current_hop_index = 0

class OutputPort:
    def __init__(self, port_id, bandwidth, is_cbs=False):
        self.port_id = port_id
        self.bandwidth = bandwidth
        self.is_cbs = is_cbs
        
        # Queues: dictionary mapping PCP to a list of Frames
        self.queues = {pcp:[] for pcp in range(8)} 
        
        # State variables
        self.is_transmitting = False
        self.current_time = 0.0
        
        # CBS variables (assuming idleSlope = sendSlope = 0.5 for this example)
        self.credit = 0.0
        self.idle_slope = 0.5 
        self.send_slope = 0.5
        self.last_credit_update = 0.0
        self.cbs_transmitting = False
        self.waiting_for_credit = False

    def update_credit(self, now):
            if not self.is_cbs: return
            
            delta_t = now - self.last_credit_update
            if delta_t <= 0: return # Safety check
            
            if self.cbs_transmitting:
                self.credit -= self.send_slope * delta_t
            else:
                cbs_has_frames = (len(self.queues[1]) > 0) or (len(self.queues[2]) > 0)
                if cbs_has_frames or self.credit < 0:
                    self.credit += self.idle_slope * delta_t
                    
                    # IEEE 802.1Qav: positive credit resets to 0 if the queue is NOT blocked
                    if not self.is_transmitting and self.credit > 0:
                        self.credit = 0.0
                        
            # --- THE FLOATING POINT FIX ---
            if abs(self.credit) < 1e-9:
                self.credit = 0.0
                
            self.last_credit_update = now

# ==========================================
# 2. THE SIMULATOR ENGINE
# ==========================================
class TSNSimulator:
    def __init__(self):
        self.time = 0.0
        self.event_queue = [] # Heap for discrete events
        self.completed_frames =[] # Store end-to-end delays here
        
        # Example dictionary to hold our ports
        # e.g., self.ports[("SW1", 6)] = OutputPort(...)
        self.ports = {} 
        self.event_id = 0   # NEW

    def schedule_event(self, timestamp, event_type, data):
        self.event_id += 1
        heapq.heappush(self.event_queue, (timestamp, self.event_id, event_type, data))

    def run(self, max_time):
        """The main Event Loop."""
        print("Starting simulation...")
        
        while self.event_queue and self.time < max_time:
            # Pop the earliest event
            event_time, _, event_type, data = heapq.heappop(self.event_queue)
            
            # Advance simulation clock
            self.time = event_time 
            
            # Route the event
            if event_type == "GENERATE_FRAME":
                self.handle_generate_frame(data)
            elif event_type == "ENQUEUE":
                self.handle_enqueue(data)
            elif event_type == "FINISH_TRANSMISSION":
                self.handle_finish_transmission(data)
            elif event_type == "CREDIT_ZERO":
                self.handle_credit_zero(data)
                
        print("Simulation ended.")

    # ==========================================
    # 3. EVENT HANDLERS
    # ==========================================
    def handle_generate_frame(self, data):
        stream = data['stream']
        
        # Create the Frame object, passing the PCP
        frame = Frame(stream['id'], stream['size'], stream['PCP'], self.time, data['route'])
        
        # Schedule the next frame generation (Periodic)
        next_gen_time = self.time + stream['period']
        self.schedule_event(next_gen_time, "GENERATE_FRAME", data)
        
        # Send this frame to the first output port immediately
        first_hop = frame.path[0]
        self.schedule_event(self.time, "ENQUEUE", {'frame': frame, 'node': first_hop['node'], 'port': first_hop['port']})

    def handle_enqueue(self, data):
        frame = data['frame']
        port_key = (data['node'], data['port'])
        
        # If the destination is reached (last hop has no egress port), finish!
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
                if port.is_cbs and pcp in [1, 2]:
                    # Floating point tolerance
                    if port.credit >= -1e-9: 
                        selected_pcp = pcp
                        break
                    else:
                        # Prevent duplicate CREDIT_ZERO events
                        if not port.waiting_for_credit:
                            time_to_zero = abs(port.credit) / port.idle_slope
                            self.schedule_event(self.time + time_to_zero, "CREDIT_ZERO", {'port': port})
                            port.waiting_for_credit = True
                        
                        # Check lower priorities since CBS is blocked!
                        continue 
                else:
                    selected_pcp = pcp
                    break
                    
        if selected_pcp is not None:
            frame = port.queues[selected_pcp].pop(0)
            port.is_transmitting = True
            
            if port.is_cbs and selected_pcp in [1, 2]:
                port.cbs_transmitting = True
            else:
                port.cbs_transmitting = False
                
            tx_time = (frame.size_bytes * 8) / port.bandwidth 
            self.schedule_event(self.time + tx_time, "FINISH_TRANSMISSION", {'frame': frame, 'port': port})

    def handle_finish_transmission(self, data):
        frame = data['frame']
        port = data['port']
        
        # Update credit and free the port
        port.update_credit(self.time)
        port.is_transmitting = False
        port.cbs_transmitting = False
        
        # Move frame to next hop
        frame.current_hop_index += 1
        if frame.current_hop_index < len(frame.path):
            next_hop = frame.path[frame.current_hop_index]
            # Assume 0 propagation delay for this example, otherwise add it here
            self.schedule_event(self.time, "ENQUEUE", {'frame': frame, 'node': next_hop['node'], 'port': next_hop['port']})
        else:
            # DESTINATION REACHED! Record metrics.
            response_time = self.time - frame.generation_time
            self.completed_frames.append({'stream_id': frame.stream_id, 'rt': response_time})
            
        # See if there's another frame waiting to go
        self.try_dequeue(port)
        
    def handle_credit_zero(self, data):
        port = data['port']
        # The credit has recovered to 0. Try to dequeue again.
        port.waiting_for_credit = False

        self.try_dequeue(port)


def setup_simulator(topology, streams, routes):
    sim = TSNSimulator()
    
    # 1. Create Output Ports for every link in the topology
    print("Initializing Network Ports...")
    for link in topology['links']:
        source_node = link['source']
        source_port = link['sourcePort']
        bandwidth = link['bandwidth_mbps']
        
        # We assume all ports can act as CBS ports. 
        # In try_dequeue, we already filter so only PCP 1 and 2 use the CBS logic.
        port = OutputPort(source_port, bandwidth, is_cbs=False)
        
        # Store port in dictionary using a tuple (NodeID, PortID) as the key
        sim.ports[(source_node, source_port)] = port
        
    # 2. Map routes to streams for easy lookup
    route_dict = {r['flow_id']: r for r in routes}
    
    # 3. Schedule the first frame generation for all streams at time 0.0
    print("Scheduling initial stream generations...")
    for stream in streams:
        route = route_dict.get(stream['id'])
        if not route:
            continue
            
        data = {
            'stream': stream,
            'route': route['paths'][0] # route['paths'][0] is a list of {"node": "...", "port": ...}
        }
        
        # Push the first event at t=0.0
        sim.schedule_event(0.0, "GENERATE_FRAME", data)
        
    return sim

def load_data():
    with open('test-case-1-topology.json') as f:
        topology = json.load(f)['topology']
    with open('test-case-1-streams.json') as f:
        streams = json.load(f)['streams']
    with open('test-case-1-routes.json') as f:
        routes = json.load(f)['routes']
    return topology, streams, routes

if __name__ == '__main__':
    # Load JSON files
    topology, streams, routes = load_data()
    
    # Setup the simulator
    sim = setup_simulator(topology, streams, routes)
    
    # Run the simulation for 20,000 microseconds
    sim.run(max_time=20000.0)
    
    # Analyze the results
    print("\n--- SIMULATION RESULTS ---")
    simulated_wcrts = {}
    
    for record in sim.completed_frames:
        s_id = record['stream_id']
        rt = record['rt']
        if s_id not in simulated_wcrts or rt > simulated_wcrts[s_id]:
            simulated_wcrts[s_id] = rt
            
    # Print the maximum observed response time for each stream
    print("Stream ID | Max Simulated RT (µs)")
    print("---------------------------------")
    for s_id in sorted(simulated_wcrts.keys()):
        print(f"   {s_id:2d}     |      {simulated_wcrts[s_id]:.2f} µs")



import matplotlib.pyplot as plt
import numpy as np

# ==========================================
# 1. THE SIMULATION DATA
# ==========================================
streams =[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

# Priorities for labeling purposes
# Streams 0-3: PCP 2 (Highest)
# Streams 4-7: PCP 1 (Medium)
# Streams 8-9: PCP 0 (Lowest / Best Effort)

cbs_results =[561.60, 561.60, 522.32, 522.32, 915.36, 915.36, 1053.76, 1053.76, 296.48, 296.48]
sp_results  =[344.32, 344.32, 344.32, 344.32, 482.72, 482.72,  638.32,  638.32, 705.60, 705.60]

# ==========================================
# 2. SETUP THE BAR CHART
# ==========================================
x = np.arange(len(streams))  # The label locations (0 to 9)
width = 0.35  # The width of the bars

fig, ax = plt.subplots(figsize=(10, 6))

# Create the bars
rects1 = ax.bar(x - width/2, cbs_results, width, label='CBS (Credit-Based Shaper)', color='#1f77b4', edgecolor='black')
rects2 = ax.bar(x + width/2, sp_results, width, label='SP (Strict Priority)', color='#ff7f0e', edgecolor='black')

# ==========================================
# 3. ADD LABELS, TITLES, AND ANNOTATIONS
# ==========================================
ax.set_xlabel('Stream ID (Sorted by Priority: High $\\rightarrow$ Low)', fontsize=12, fontweight='bold')
ax.set_ylabel('Max Simulated Response Time (µs)', fontsize=12, fontweight='bold')
ax.set_title('Comparison of Max Response Times: CBS vs Strict Priority', fontsize=14, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels([f"Str {i}\n(PCP {2 if i<4 else 1 if i<8 else 0})" for i in streams])
ax.legend(fontsize=11)

# Add a grid behind the bars for easier reading
ax.grid(axis='y', linestyle='--', alpha=0.7)

# Add the exact numbers on top of the bars
def autolabel(rects):
    """Attach a text label above each bar in *rects*, displaying its height."""
    for rect in rects:
        height = rect.get_height()
        ax.annotate(f'{height:.1f}',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, rotation=45)

autolabel(rects1)
autolabel(rects2)

# Adjust layout so labels don't get cut off
fig.tight_layout()

# ==========================================
# 4. SHOW AND SAVE THE PLOT
# ==========================================
plt.savefig('cbs_vs_sp_comparison.png', dpi=300) # Saves a high-quality image for your report
plt.show() # Displays the window