# G8-RealTimeSystemsProj2

02225 DRTS Mini-Project 2: TSN Credit-Based Shaper Analysis & Simulation
This project implements an analytical tool and a Discrete-Event Simulator (DES) to evaluate the Worst-Case Response Times (WCRT) of Time-Sensitive Networking (TSN) streams. Specifically, it compares the performance of the Credit-Based Shaper (CBS) (IEEE 802.1Qav) against traditional Strict Priority (SP) shaping, demonstrating how CBS bounds high-priority traffic to prevent the starvation of lower-priority (Best Effort) queues.

📂 Project Files

run_demo.py (Analytical Tool): Calculates the theoretical end-to-end WCRT for streams using the mathematical models defined in Cao et al. (2016). It calculates Same-Priority Interference (SPI), Lower-Priority Interference (LPI), and Higher-Priority Interference (HPI).
run_simulations.py (Discrete-Event Simulator): A custom event-driven simulator that dynamically routes frames across the network. It tracks exact credit accumulation/depletion for CBS queues and logs the maximum observed response times. It also includes code to generate a comparative bar chart (matplotlib).
Input JSON Files: The scripts require test-case-1-topology.json, test-case-1-streams.json, and test-case-1-routes.json to be located in the same directory.

⚙️ Prerequisites

The analytical tool uses standard Python libraries. The simulation and graphing tool requires matplotlib and numpy. Install them via pip:

pip install matplotlib numpy

🚀 How to Run

1. Analytical WCRT Calculation
To run the mathematical WCRT calculation:
python run_demo.py

Expected Output: The script will print the hop-by-hop breakdown of interference (SPI, LPI, HPI, Ci) for Stream 0 and output the final theoretical WCRT (which matches the expected 603.2 µs).

2. Discrete-Event Simulation & Graphing
To run the simulation and generate the comparison graph:

python run_simulations.py

Expected Output:
The script will run the simulator for 20,000 µs and print the Maximum Simulated Response Time for each stream in the terminal. A window will pop up displaying a bar chart comparing CBS vs. SP response times. The chart will automatically be saved to your directory as cbs_vs_sp_comparison.png.

Note: In run_simulations.py, the is_cbs flag inside the setup_simulator() function controls the active shaper mechanism. To test Strict Priority, is_cbs should be set to False. To test CBS, change is_cbs=True. The graphing section at the bottom of the script contains the recorded results of running both modes.
