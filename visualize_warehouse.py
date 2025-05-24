import json
import re
import argparse
from collections import defaultdict
import copy
import time 
import os

# --- Configuration ---
GRID_SYMBOLS = {
    "empty": ".",
    "highway": "#",
    "station": "P",
    "robot": "R",
    "shelf": "S",
    "robot_shelf_prefix": "[",
    "robot_shelf_suffix": "]",
}

# ANSI escape codes for screen manipulation
CLEAR_SCREEN = '\033[2J'
CURSOR_HOME = '\033[H'
CURSOR_UP = '\033[F'
CLEAR_LINE = '\033[K'

# --- Parsing Functions ---

def parse_init(filepath):
    """
    Parses the init facts from the input .lp file.
    Returns the initial state dictionary and grid dimensions.
    """
    state = {
        'nodes': set(),
        'highways': set(),
        'picking_stations': {}, # id -> (x, y)
        'robots': {},           # id -> {'pos': (x, y), 'carries': None}
        'shelves': {},          # id -> {'pos': (x, y), 'quantities': {product_id: qty}}
        'products': set(),      # set of all product_ids mentioned
        'orders': {},           # id -> {'station_id': sid, 'requirements': {product_id: qty}}
    }
    max_x, max_y = 0, 0
    shelf_quantities_temp = defaultdict(lambda: defaultdict(int))
    order_reqs_temp = defaultdict(lambda: defaultdict(int)) 
    order_station_temp = {} 

    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('%'):
                    continue

                match_node = re.match(r"init\(object\(node,\s*(\w+)\),\s*value\(at,\s*pair\((\d+),(\d+)\)\)\)\.", line)
                match_highway = re.match(r"init\(object\(highway,\s*(\w+)\),\s*value\(at,\s*pair\((\d+),(\d+)\)\)\)\.", line)
                match_station = re.match(r"init\(object\(pickingStation,\s*(\w+)\),\s*value\(at,\s*pair\((\d+),(\d+)\)\)\)\.", line)
                match_robot = re.match(r"init\(object\(robot,\s*(\w+)\),\s*value\(at,\s*pair\((\d+),(\d+)\)\)\)\.", line)
                match_shelf_loc = re.match(r"init\(object\(shelf,\s*(\w+)\),\s*value\(at,\s*pair\((\d+),(\d+)\)\)\)\.", line)
                match_product = re.match(r"init\(object\(product,\s*(\w+)\),\s*value\(on,\s*pair\((\w+),(\d+)\)\)\)\.", line)
                match_order_station = re.match(r"init\(object\(order,\s*(\w+)\),\s*value\(pickingStation,\s*(\w+)\)\)\.", line)
                match_order_line = re.match(r"init\(object\(order,\s*(\w+)\),\s*value\(line,\s*pair\((\w+),(\d+)\)\)\)\.", line)

                if match_node:
                    _, x, y = match_node.groups() # node_id often unused
                    x, y = int(x), int(y)
                    state['nodes'].add((x, y))
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
                elif match_highway:
                    _, x, y = match_highway.groups()
                    state['highways'].add((int(x), int(y)))
                elif match_station:
                    station_id, x, y = match_station.groups()
                    state['picking_stations'][station_id] = (int(x), int(y))
                elif match_robot:
                    robot_id, x, y = match_robot.groups()
                    state['robots'][robot_id] = {'pos': (int(x), int(y)), 'carries': None}
                elif match_shelf_loc:
                    shelf_id, x, y = match_shelf_loc.groups()
                    if shelf_id not in state['shelves']:
                         state['shelves'][shelf_id] = {'pos': (int(x), int(y)), 'quantities': {}}
                    else: 
                         state['shelves'][shelf_id]['pos'] = (int(x), int(y)) 
                elif match_product:
                    product_id, shelf_id, qty = match_product.groups()
                    state['products'].add(product_id)
                    shelf_quantities_temp[shelf_id][product_id] = int(qty)
                elif match_order_station:
                    order_id, station_id = match_order_station.groups()
                    order_station_temp[order_id] = station_id
                elif match_order_line:
                    order_id, product_id, qty = match_order_line.groups()
                    state['products'].add(product_id)
                    order_reqs_temp[order_id][product_id] = int(qty)
                else:
                    print(f"Warning: Unmatched init line: {line}")

        # Link temporary shelf/order data and ensure defaults
        for shelf_id, quantities in shelf_quantities_temp.items():
            if shelf_id in state['shelves']:
                state['shelves'][shelf_id]['quantities'] = quantities
            else:
                print(f"Warning: Product quantity defined for non-existent shelf: {shelf_id}")

        for order_id, reqs in order_reqs_temp.items():
            if order_id in order_station_temp:
                state['orders'][order_id] = {
                    'station_id': order_station_temp[order_id],
                    'requirements': reqs
                }
            else:
                 print(f"Warning: Order lines defined for order without picking station: {order_id}")

        for shelf_id in state['shelves']:
            for product_id in state['products']:
                state['shelves'][shelf_id]['quantities'].setdefault(product_id, 0)
        
        for order_id in state['orders']:
             for product_id in state['products']:
                 state['orders'][order_id]['requirements'].setdefault(product_id, 0)

    except FileNotFoundError:
        print(f"Error: Input file not found at {filepath}")
        return None, None
    except Exception as e:
        print(f"Error parsing init file {filepath}: {e}")
        return None, None

    grid_dims = {'x': max_x, 'y': max_y}
    return state, grid_dims

def parse_action_string(action_str):
    """ Parses the action component string from an occurs/3 atom """
    action_str = action_str.strip()

    match_move = re.match(r"move\((-?\d+),(-?\d+)\)", action_str)
    match_pickup = (action_str == "pickup")
    match_putdown = (action_str == "putdown")
    match_deliver = re.match(r"deliver\((\w+),(\w+),(\d+)\)", action_str)

    if match_move:
        dx, dy = map(int, match_move.groups())
        return {"type": "move", "dx": dx, "dy": dy}
    elif match_pickup:
        return {"type": "pickup"}
    elif match_putdown:
        return {"type": "putdown"}
    elif match_deliver:
        order_id, product_id, units = match_deliver.groups()
        return {"type": "deliver", "order": order_id, "product": product_id, "units": int(units)}
    else:
        print(f"Warning: Could not parse action string: {action_str}")
        return {"type": "unknown", "raw": action_str}

def parse_plan(filepath):
    """ Parses the plan from Clingo's JSON output file. """
    plan = defaultdict(list) 
    max_time = 0
    try:
        # Read file potentially skipping // comments sometimes added by clingo
        with open(filepath, 'r', encoding='utf-8') as f:
            content = "".join(line for line in f if not line.strip().startswith('//'))
        data = json.loads(content)

        if not data.get('Call') or not data['Call'][0].get('Witnesses'):
            print("Warning: JSON structure doesn't contain expected 'Call'/'Witnesses'. No plan found?")
            return plan, max_time

        witness = data['Call'][0]['Witnesses'][0]
        plan_atoms = witness.get('Value', [])

        for atom_str in plan_atoms:
            match = re.match(r"occurs\(object\(robot,\s*(\w+)\),\s*(.+)\s*,\s*(\d+)\)", atom_str)
            if match:
                robot_id, action_part, time_str = match.groups()
                time = int(time_str)
                max_time = max(max_time, time)
                action_details = parse_action_string(action_part)
                if action_details['type'] != 'unknown':
                    plan[time].append({'robot': robot_id, 'action': action_details})

    except FileNotFoundError:
        print(f"Error: Plan file not found at {filepath}")
        return None, 0
    except json.JSONDecodeError as e:
        print(f"Error: Could not decode JSON from plan file {filepath}. {e}")
        return None, 0
    except Exception as e:
        print(f"Error parsing plan file {filepath}: {e}")
        return None, 0

    return plan, max_time

# --- State Update Logic ---

def update_state(current_state, actions_at_this_step):
    """
    Calculates the next state based on the current state and actions performed.
    Returns the new state dictionary.
    """
    next_state = copy.deepcopy(current_state) 

    for action_info in actions_at_this_step:
        robot_id = action_info['robot']
        action = action_info['action']
        robot_curr_state = current_state['robots'].get(robot_id)

        if not robot_curr_state:
            print(f"Warning: Action specified for unknown robot {robot_id}. Skipping.")
            continue

        current_pos = robot_curr_state['pos']
        current_carrying = robot_curr_state['carries']
        robot_next_state = next_state['robots'][robot_id] 

        if action['type'] == 'move':
            next_x = current_pos[0] + action['dx']
            next_y = current_pos[1] + action['dy']
            robot_next_state['pos'] = (next_x, next_y)

        elif action['type'] == 'pickup':
            if current_carrying:
                print(f"Warning: Robot {robot_id} tried to pickup while already carrying {current_carrying}. Ignoring pickup.")
                continue
            
            shelf_to_pickup = None
            for shelf_id, shelf_data in current_state['shelves'].items():
                if shelf_data.get('pos') == current_pos: 
                    shelf_to_pickup = shelf_id
                    break
            
            if shelf_to_pickup:
                robot_next_state['carries'] = shelf_to_pickup
                if shelf_to_pickup in next_state['shelves']:
                     next_state['shelves'][shelf_to_pickup].pop('pos', None) 
            else:
                print(f"Warning: Robot {robot_id} tried to pickup at {current_pos}, but no shelf found there. Ignoring pickup.")

        elif action['type'] == 'putdown':
            if not current_carrying:
                print(f"Warning: Robot {robot_id} tried to putdown while carrying nothing. Ignoring putdown.")
                continue
            
            if current_pos in next_state.get('highways', set()):
                 print(f"Warning: Robot {robot_id} tried to putdown shelf {current_carrying} on highway {current_pos}. Ignoring.")
                 continue

            occupied = False
            for shelf_id, shelf_data in next_state['shelves'].items():
                 if shelf_data.get('pos') == current_pos and shelf_id != current_carrying:
                     print(f"Warning: Robot {robot_id} tried to putdown shelf {current_carrying} at {current_pos}, but shelf {shelf_id} is already there. Ignoring.")
                     occupied = True
                     break
            if occupied: continue

            shelf_id_being_carried = current_carrying
            robot_next_state['carries'] = None
            if shelf_id_being_carried in next_state['shelves']:
                next_state['shelves'][shelf_id_being_carried]['pos'] = current_pos

        elif action['type'] == 'deliver':
            shelf_id_carried = current_carrying
            order_id = action['order']
            product_id = action['product']
            units = action['units']

            if not shelf_id_carried:
                print(f"Warning: Robot {robot_id} tried to deliver while carrying nothing. Ignoring.")
                continue
            if shelf_id_carried not in next_state['shelves']:
                print(f"Warning: Robot {robot_id} carrying unknown shelf {shelf_id_carried}. Ignoring deliver.")
                continue
            if order_id not in next_state['orders']:
                 print(f"Warning: Deliver action for unknown order {order_id}. Ignoring.")
                 continue
            
            # Check if product exists on shelf (even if 0 quantity) before trying to access quantities dict further
            if product_id not in next_state['shelves'][shelf_id_carried].get('quantities', {}):
                 print(f"Warning: Deliver action for unknown product {product_id} on shelf {shelf_id_carried}. Ignoring.")
                 continue

            required_station_id = next_state['orders'][order_id].get('station_id')
            required_station_pos = next_state['picking_stations'].get(required_station_id) if required_station_id else None
            if current_pos != required_station_pos:
                print(f"Warning: Robot {robot_id} tried to deliver for order {order_id} at {current_pos}, but required station {required_station_id} is at {required_station_pos}. Ignoring.")
                continue

            current_shelf_qty = next_state['shelves'][shelf_id_carried]['quantities'].get(product_id, 0)
            if current_shelf_qty < units:
                print(f"Warning: Robot {robot_id} tried to deliver {units} of {product_id} from shelf {shelf_id_carried}, but it only has {current_shelf_qty}. Ignoring.")
                continue
                
            next_state['shelves'][shelf_id_carried]['quantities'][product_id] -= units
            # Ensure requirements exist before decrementing
            if product_id in next_state['orders'][order_id].get('requirements', {}):
                 next_state['orders'][order_id]['requirements'][product_id] -= units
                 if next_state['orders'][order_id]['requirements'][product_id] < 0:
                      next_state['orders'][order_id]['requirements'][product_id] = 0
            else:
                 print(f"Warning: Tried to decrement requirement for product {product_id} not in order {order_id}.")

    return next_state

# --- Visualization ---

def calculate_max_width_for_state(state, grid_dims):
    """Calculates the maximum cell width needed to display the given state."""
    max_w = 0
    for r in range(1, grid_dims['y'] + 1):
         for c in range(1, grid_dims['x'] + 1):
              content = " " 
              pos = (c, r)
              
              robot_here = None
              shelf_here = None
              for rid, rdata in state.get('robots', {}).items():
                  if rdata.get('pos') == pos: robot_here = rid; break 
              for sid, sdata in state.get('shelves', {}).items():
                   if sdata.get('pos') == pos: shelf_here = sid; break 
              
              if robot_here:
                  carried = state['robots'][robot_here].get('carries')
                  content = f"{GRID_SYMBOLS['robot']}{robot_here}"
                  if carried: content += f"{GRID_SYMBOLS['robot_shelf_prefix']}{GRID_SYMBOLS['shelf']}{carried}{GRID_SYMBOLS['robot_shelf_suffix']}"
              elif shelf_here: 
                  content = f"{GRID_SYMBOLS['shelf']}{shelf_here}"
              else:
                  # Check static background
                  station_match = False
                  for station_id, station_pos in state.get('picking_stations', {}).items():
                       if station_pos == pos:
                           content = f"{GRID_SYMBOLS['station']}{station_id}"
                           station_match = True
                           break
                  if not station_match:
                      if pos in state.get('highways', set()): content = GRID_SYMBOLS['highway']
                      elif pos in state.get('nodes', set()): content = GRID_SYMBOLS['empty']
              
              max_w = max(max_w, len(content.strip())) 
              
    return max(max_w, 1) 

def visualize_step(state, time, grid_dims, fixed_cell_width, actions_this_step=None): 
    """
    Prints a textual representation of the warehouse state at a given time.
    Uses a pre-calculated fixed_cell_width for consistent formatting.
    Assumes coordinates are 1-based for display. (0,0) top-left.
    """
    if actions_this_step is None: actions_this_step = []

    # Initialize internal 0-indexed grids
    grid = [[" " for _ in range(grid_dims['x'] + 1)] for _ in range(grid_dims['y'] + 1)]
    display_layer = [[" " for _ in range(grid_dims['x'] + 1)] for _ in range(grid_dims['y'] + 1)]
    final_grid = [[" " for _ in range(grid_dims['x'] + 1)] for _ in range(grid_dims['y'] + 1)]

    # Populate internal grids using 1-based coordinates
    for r in range(1, grid_dims['y'] + 1): 
        for c in range(1, grid_dims['x'] + 1): 
             pos = (c, r)
             if pos in state.get('nodes', set()): grid[r][c] = GRID_SYMBOLS['empty']
             if pos in state.get('highways', set()): grid[r][c] = GRID_SYMBOLS['highway']

    for station_id, pos in state.get('picking_stations', {}).items():
        x, y = pos
        if 1 <= y <= grid_dims['y'] and 1 <= x <= grid_dims['x']:
           grid[y][x] = f"{GRID_SYMBOLS['station']}{station_id}"

    for shelf_id, shelf_data in state.get('shelves', {}).items():
        if 'pos' in shelf_data:
            x, y = shelf_data['pos']
            if 1 <= y <= grid_dims['y'] and 1 <= x <= grid_dims['x']:
                display_layer[y][x] = f"{GRID_SYMBOLS['shelf']}{shelf_id}"

    for robot_id, robot_data in state.get('robots', {}).items():
        x, y = robot_data.get('pos', (-1,-1))
        if 1 <= y <= grid_dims['y'] and 1 <= x <= grid_dims['x']:
            carried_shelf = robot_data.get('carries')
            content = f"{GRID_SYMBOLS['robot']}{robot_id}"
            if carried_shelf:
                 content += f"{GRID_SYMBOLS['robot_shelf_prefix']}{GRID_SYMBOLS['shelf']}{carried_shelf}{GRID_SYMBOLS['robot_shelf_suffix']}"
            display_layer[y][x] = content

    # Combine layers into final_grid
    for r in range(1, grid_dims['y'] + 1): 
         for c in range(1, grid_dims['x'] + 1): 
              if display_layer[r][c] != " ": final_grid[r][c] = display_layer[r][c]
              else: final_grid[r][c] = grid[r][c]

    # Clear screen and move cursor to home position
    print(CLEAR_SCREEN + CURSOR_HOME, end='')

    # --- Grid Printing ---
    print(f"--- Time: {time} ---")
    cols_to_display = grid_dims['x']
    max_cell_width = fixed_cell_width 

    # Define box-drawing characters
    cell_separator = "│"
    row_separator_joint = "┼"
    row_separator_segment = "─" * max_cell_width
    top_joint_left = "┌"
    top_joint_right = "┐"
    top_joint_middle = "┬"
    mid_joint_left = "├"
    mid_joint_right = "┤"
    bottom_joint_left = "└"
    bottom_joint_right = "┘"
    bottom_joint_middle = "┴"

    # Construct separator strings
    top_border = top_joint_left + (row_separator_segment + top_joint_middle) * (cols_to_display - 1) + row_separator_segment + top_joint_right
    mid_separator = mid_joint_left + (row_separator_segment + row_separator_joint) * (cols_to_display - 1) + row_separator_segment + mid_joint_right
    bottom_border = bottom_joint_left + (row_separator_segment + bottom_joint_middle) * (cols_to_display - 1) + row_separator_segment + bottom_joint_right

    print(top_border)
    for r in range(1, grid_dims['y'] + 1): 
        cells_to_print = [final_grid[r][c].ljust(max_cell_width) for c in range(1, grid_dims['x'] + 1)] 
        row_content = cell_separator + cell_separator.join(cells_to_print) + cell_separator
        print(row_content)
        if r < grid_dims['y']: print(mid_separator)
        else: print(bottom_border)

    # --- Action & Summary Printing ---
    if actions_this_step:
        print("Actions Occurring:")
        for action_info in actions_this_step:
            robot_id = action_info['robot']
            action = action_info['action']
            action_str = f"  Robot {robot_id}: {action['type']}"
            if action['type'] == 'move': action_str += f" ({action['dx']},{action['dy']})"
            elif action['type'] == 'deliver': action_str += f" (Order: {action['order']}, Product: {action['product']}, Units: {action['units']})"
            print(action_str)
    elif time > 0: 
        print("No actions occurred.")

    print("\nShelf Quantities:")
    shelf_summary_printed = False
    shelves_exist = bool(state.get('shelves'))
    if shelves_exist:
        for sid, sdata in sorted(state.get('shelves', {}).items()):
            qtys = [f"Product {pid}: Qty {qty}" for pid, qty in sorted(sdata.get('quantities', {}).items()) if qty > 0]
            if qtys: print(f"  Shelf {sid}: {', '.join(qtys)}"); shelf_summary_printed = True
        if not shelf_summary_printed: print("  All shelves appear empty.")
    else: print("  No shelves defined.")
        
    print("\nOrder Requirements:")
    any_unfulfilled_orders = False 
    orders_defined = bool(state.get('orders')) 
    if not orders_defined:
        print("  No orders defined in the input.")
    else:
        for oid, odata in sorted(state.get('orders', {}).items()):
            reqs = [f"Product {pid}: Qty {qty}" for pid, qty in sorted(odata.get('requirements', {}).items()) if qty > 0]
            if reqs: print(f"  Order {oid} (at {GRID_SYMBOLS['station']}{odata.get('station_id','?')}) Req: {', '.join(reqs)}"); any_unfulfilled_orders = True 
        if not any_unfulfilled_orders: print("  All defined orders fulfilled!")

# --- Main Execution ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize Clingo warehouse plan with fixed grid width.")
    parser.add_argument("init_file", help="Path to the input file (.lp) with init facts.")
    parser.add_argument("plan_file", help="Path to the plan file (.json) from Clingo.")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay in seconds between steps (default: 0.5).")
    args = parser.parse_args()

    # Enable ANSI escape sequences for Windows
    if os.name == 'nt':
        os.system('')

    initial_state, grid_dims = parse_init(args.init_file)
    if not initial_state or not grid_dims: exit(1)

    plan, max_time = parse_plan(args.plan_file)
    if plan is None: exit(1)

    # Pre-simulation Pass
    print("Pre-calculating maximum cell width for consistent grid size...")
    overall_max_cell_width = 0
    temp_state = copy.deepcopy(initial_state) 
    overall_max_cell_width = max(overall_max_cell_width, calculate_max_width_for_state(temp_state, grid_dims))

    for t in range(1, max_time + 1):
        temp_state = update_state(temp_state, plan.get(t, [])) 
        overall_max_cell_width = max(overall_max_cell_width, calculate_max_width_for_state(temp_state, grid_dims))
    print(f"Calculation complete. Fixed cell width for visualization: {overall_max_cell_width}")

    # Visualization Loop
    current_state = initial_state 
    print("\nStarting Visualization...")
    visualize_step(current_state, 0, grid_dims, overall_max_cell_width) 
    time.sleep(args.delay * 2) 

    for t in range(1, max_time + 1):
        actions_now = plan.get(t, [])
        current_state = update_state(current_state, actions_now) 
        visualize_step(current_state, t, grid_dims, overall_max_cell_width, actions_now) 
        time.sleep(args.delay)

    print(f"\n--- Simulation Complete (Reached Time {max_time}) ---")
    
    # Final Summary
    print("\nFinal Order Requirements:")
    all_fulfilled = True
    orders_exist_final = bool(current_state.get('orders'))
    if not orders_exist_final: 
        print("  No orders defined.")
    else:
        for oid, odata in sorted(current_state.get('orders', {}).items()):
            reqs = [f"P{pid}:{qty}" for pid, qty in sorted(odata.get('requirements', {}).items()) if qty > 0]
            if reqs: 
                print(f"  Order {oid} (at {GRID_SYMBOLS['station']}{odata.get('station_id','?')}) Req: {', '.join(reqs)} --> NOT FULFILLED")
                all_fulfilled = False
        if all_fulfilled: print("  All defined orders fulfilled!")