# Automated Warehouse Simulation using Answer Set Programming

A declarative model of an automated warehouse in **Answer Set Programming (ASP)** using **[clingo](https://potassco.org/clingo/)**. Robots navigate a grid, pick up shelves, deliver products to picking stations, and cooperate to satisfy orders while avoiding collisions and highways. The solver minimises the overall **makespan** (time of the last action).

## Repository layout

```
.
├── warehouse_management.lp      # ASP encoding
├── simpleInstances/             # Sample instances from the ASP Challenge
│   ├── inst1.asp … inst5.asp
├── visualize_warehouse.py       # Optional ASCII visualiser for plans
└── README.md
```

## Quick start

### 1 · Install clingo

```bash
pip install clingo           # or brew install clingo / apt‑get install clingo
```

### 2 · Run the solver

```bash
# solve instance 1 with four solver threads and horizon 13
clingo warehouse_management.lp simpleInstances/inst1.asp -c t_max=13 -t 4
```

### 3 · Render the plan (optional)

```bash
clingo warehouse_management.lp simpleInstances/inst2.asp -c t_max=10 --outf=2 > plan.json
python visualize_warehouse.py simpleInstances/inst2.asp plan.json
```

## Input format

Instances follow the **ASP Challenge “Automated Warehouse”** specification fileciteturn0file0:

* `init(object(node,N), value(at, pair(X,Y))).` – grid cells
* `init(object(highway,H), value(at, pair(X,Y))).` – no shelf may be put down here
* `init(object(pickingStation,P), value(at, pair(X,Y))).`
* `init(object(robot,R), value(at, pair(X,Y))).`
* `init(object(shelf,S), value(at, pair(X,Y))).`
* `init(object(product,I), value(on, pair(S,U))).` – *U* units of product *I* on shelf *S*
* `init(object(order,O), value(line, pair(I,U))).` – order *O* wants *U* units of *I*
* `init(object(order,O), value(pickingStation,P)).`

## Encoding highlights

| Concept                 | Rule(s)                                                                      |
| ----------------------- | ---------------------------------------------------------------------------- |
| **Dynamic horizons**    | `time(T) :- T = 0..t_max.` is parameterised via `-c t_max=<int>`.            |
| **Aggregate domains**   | `final_max_u(M)` derives the largest product quantity found in the instance. |
| **Action generation**   | A single choice rule ensures **≤ 1** action per robot and time‑step.         |
| **Collision avoidance** | Constraints forbid co‑location, cell swaps, and shelf blocking.              |
| **Optimisation**        | `#minimize { T : occurs(_,_,T) }` minimises the makespan.                    |

## Visualisation

`visualize_warehouse.py` prints an ASCII snapshot for every time step, highlighting robots, shelves, highways (`#`) and picking stations (`P*`). It consumes the JSON output produced with `--outf=2`. Refer below to see a breakdown of the visualization.

## Requirements

| Component | Tested version |
| --------- | -------------- |
| clingo    | ≥ 5.7.0        |
| Python    | 3.9 + `rich`   |


## License

MIT – see [LICENSE](LICENSE).


# Warehouse Visualization Tool

This tool provides a dynamic visualization of warehouse operations based on ASP (Answer Set Programming) solutions. It creates a video-like console output showing the movement of robots, shelves, and order fulfillment in a warehouse environment.

## Features

- Real-time visualization of warehouse state
- Dynamic grid display with robots, shelves, and picking stations
- Tracking of shelf quantities and order requirements
- Video-like console output with in-place updates
- Support for multiple robots and orders
- Detailed action logging

## Example: Instance 1 (inst1.asp)

Let's walk through the example warehouse setup from `inst1.asp`:

### Warehouse Layout
The warehouse is a 4x4 grid with the following elements:

- **Nodes**: 16 nodes forming a grid (1,1) to (4,4)
- **Highways**: Located at positions (4,1), (4,2), (4,3), and the entire bottom row (1,4) to (4,4)
- **Picking Stations**: 
  - Station 1 at (1,3)
  - Station 2 at (3,1)
- **Robots**:
  - Robot 1 at (4,3)
  - Robot 2 at (2,2)
- **Shelves**:
  - Shelf 1 at (3,3)
  - Shelf 2 at (2,1)
  - Shelf 3 at (2,3)
  - Shelf 4 at (2,2)
  - Shelf 5 at (3,2)
  - Shelf 6 at (1,2)
- **Products**:
  - Product 1 on Shelf 3
  - Product 2 on Shelf 4
  - Product 3 on Shelf 6
  - Product 4 on Shelves 5 and 6
- **Orders**:
  - Order 1 at Station 1: Requires 1 unit of Product 1 and 4 units of Product 3
  - Order 2 at Station 2: Requires 1 unit of Product 2
  - Order 3 at Station 2: Requires 1 unit of Product 4

### Visualization

The visualization shows:
- A grid where each cell can contain:
  - `.` for empty nodes
  - `#` for highways
  - `P1`, `P2` for picking stations
  - `R1`, `R2` for robots
  - `S1`, `S2`, etc. for shelves
  - `R1[S1]` format when a robot is carrying a shelf

Below the grid, the visualization shows:
- Current time step
- Actions being performed by robots
- Current quantities on each shelf
- Remaining order requirements

https://github.com/user-attachments/assets/83b5d264-f349-402f-8ace-387fc6035558


## Usage

```bash
python visualize_warehouse.py init_file.lp plan_file.json [--delay DELAY]
```

Parameters:
- `init_file.lp`: The ASP file containing the initial warehouse state
- `plan_file.json`: The JSON file containing the solution plan from Clingo
- `--delay`: Optional delay between steps in seconds (default: 0.5)

## Requirements

- Python 3.x
- Windows/Linux/MacOS terminal with ANSI escape sequence support

## Notes

- The visualization uses ANSI escape codes for screen manipulation
- On Windows, ANSI support is automatically enabled
- The grid size is automatically calculated based on the input file
- Cell width is pre-calculated to ensure consistent display 
