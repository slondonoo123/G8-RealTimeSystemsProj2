import json
import math

# ==========================================
# 1. FILE LOADING & PARSING
# ==========================================
def load_data():
    with open('test-case-1-topology.json') as f:
        topology = json.load(f)['topology']
    with open('test-case-1-streams.json') as f:
        streams = json.load(f)['streams']
    with open('test-case-1-routes.json') as f:
        routes = json.load(f)['routes']
    return topology, streams, routes

# ==========================================
# 2. HELPER FUNCTIONS FOR NETWORK ROUTING
# ==========================================
def get_link(topology, node_id, port):
    """Finds the link object based on the source node and egress port."""
    for link in topology['links']:
        if link['source'] == node_id and link['sourcePort'] == port:
            return link
    return None

def get_streams_on_link(all_streams, routes, link):
    """Finds all streams that travel across a specific link."""
    streams_on_link = []
    route_dict = {r['flow_id']: r for r in routes}
    
    for stream in all_streams:
        route = route_dict.get(stream['id'])
        if not route: continue
        
        # Check if the link matches any hop in the stream's route
        # We ignore the last hop [:-1] because it's the destination (no egress link)
        for hop in route['paths'][0][:-1]:
            if hop['node'] == link['source'] and hop['port'] == link['sourcePort']:
                streams_on_link.append(stream)
                break
                
    return streams_on_link

def group_streams_by_priority(target_stream, streams_on_link):
    """Separates competing streams into Same, Higher, and Lower priority."""
    same_prio = []
    higher_prio = []
    lower_prio =[]
    
    for s in streams_on_link:
        if s['id'] == target_stream['id']:
            continue # Skip the stream we are currently analyzing
            
        if s['PCP'] == target_stream['PCP']:
            same_prio.append(s)
        elif s['PCP'] > target_stream['PCP']:
            higher_prio.append(s)
        elif s['PCP'] < target_stream['PCP']:
            lower_prio.append(s)
            
    return same_prio, higher_prio, lower_prio

# ==========================================
# 3. CORE MATHEMATICAL FORMULAS
# ==========================================
def calculate_transmission_time(size_bytes, bandwidth_mbps):
    # (Bytes * 8 bits/byte) / Mbps = microseconds (µs)
    return (size_bytes * 8) / bandwidth_mbps

def calculate_SPI(same_priority_streams, bandwidth):
    """Same-Priority Interference"""
    spi = 0
    # The assignment says idleSlope and sendSlope are both 0.5. 
    # Therefore, alpha_ratio (sendSlope / idleSlope) = 1.0
    alpha_ratio = 1.0 
    for stream in same_priority_streams:
        C_j = calculate_transmission_time(stream['size'], bandwidth)
        spi += C_j * (1 + alpha_ratio)
    return spi

def calculate_LPI(lower_priority_streams, bandwidth):
    """Lower-Priority Interference (Blocking)"""
    if not lower_priority_streams:
        return 0
    c_times = [calculate_transmission_time(s['size'], bandwidth) for s in lower_priority_streams]
    # Blocked by the SINGLE largest lower-priority frame
    return max(c_times)

def calculate_HPI(target_pcp, LPI, higher_priority_streams, bandwidth):
    """Higher-Priority Interference"""
    # In this test case, PCP 2 is Class A (Highest), PCP 1 is Class B.
    if target_pcp == 2:
        # Highest priority class suffers NO higher priority interference
        return 0
    elif target_pcp == 1:
        if not higher_priority_streams:
            return 0
        alpha_ratio_H = 1.0
        c_times =[calculate_transmission_time(s['size'], bandwidth) for s in higher_priority_streams]
        # Consuming accumulated credit + max transmission time of Class A
        return (LPI * alpha_ratio_H) + max(c_times)
    return 0

# ==========================================
# 4. MAIN WCRT ALGORITHM
# ==========================================
def calculate_end_to_end_WCRT(stream_id, topology, streams, routes):
    # Retrieve the target stream and its route
    target_stream = next(s for s in streams if s['id'] == stream_id)
    target_route = next(r for r in routes if r['flow_id'] == stream_id)
    
    total_wcrt = 0
    
    print(f"\n--- Analyzing Stream {stream_id} (PCP {target_stream['PCP']}, Size {target_stream['size']}B) ---")
    
    # Iterate through each hop in the path to calculate link-by-link WCRT
    path = target_route['paths'][0]
    for i, hop in enumerate(path[:-1]):
        node_id = hop['node']
        port = hop['port']
        
        # 1. Get Link Properties
        link = get_link(topology, node_id, port)
        bandwidth = link['bandwidth_mbps']
        
        # 2. Determine Competing Traffic on this Link
        streams_on_link = get_streams_on_link(streams, routes, link)
        same_prio, higher_prio, lower_prio = group_streams_by_priority(target_stream, streams_on_link)
        
        # 3. Calculate delays
        C_i = calculate_transmission_time(target_stream['size'], bandwidth)
        SPI = calculate_SPI(same_prio, bandwidth)
        LPI = calculate_LPI(lower_prio, bandwidth)
        HPI = calculate_HPI(target_stream['PCP'], LPI, higher_prio, bandwidth)
        
        link_wcrt = SPI + HPI + LPI + C_i
        
        print(f"Hop {i+1} ({node_id} -> port {port}):")
        print(f"  - Transmission Time (C_i): {C_i:.2f} µs")
        print(f"  - Same-Priority Interf (SPI): {SPI:.2f} µs")
        print(f"  - Lower-Priority Block (LPI): {LPI:.2f} µs")
        print(f"  - Higher-Priority Interf (HPI): {HPI:.2f} µs")
        print(f"  => Total Link WCRT: {link_wcrt:.2f} µs\n")
        
        total_wcrt += link_wcrt
        
    return total_wcrt

# ==========================================
# 5. RUN THE SCRIPT
# ==========================================
if __name__ == '__main__':
    # Load the JSON files
    topology, streams, routes = load_data()
    
    # Run the analysis for Stream 0
    stream_id_to_test = 0
    final_wcrt = calculate_end_to_end_WCRT(stream_id_to_test, topology, streams, routes)
    
    print("==================================================")
    print(f" FINAL END-TO-END WCRT FOR STREAM {stream_id_to_test}: {final_wcrt:.1f} µs")
    print(" EXPECTED (FROM test-case-1-WCRTs.csv): 603.2 µs")
    print("==================================================")
    
    if round(final_wcrt, 1) == 603.2:
        print("✅ SUCCESS! The mathematical model perfectly matches the paper.")
    else:
        print("❌ MISMATCH! Something went wrong.")

