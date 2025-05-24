%%%%%%%%%%%%%%%%%%%
% File: warehouse_management.lp
%%%%%%%%%%%%%%%%%%%

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Domain Declarations
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Max x coordinate
#const max_x = 4. 
% Max Y coordinate from example
#const max_y = 4. 

% t_max passed as an external parameter for max timesteps, (-c t_max=13)

% Define coordinate, time, and unit domains.
coord(X) :- init(object(node, _), value(at, pair(X, _))).
coord(Y) :- init(object(node, _), value(at, pair(_, Y))).
time(T)  :- T = 0..t_max.


% max_u is derived from input, but we could also hardcode an upper bound
% Hardcoded units- #const max_u = 10.

% Determine Maximum Units Dynamically

% Collect all unit values from initial shelf quantities
initial_shelf_units(U) :- init(object(product, _), value(on, pair(_, U))).

% Collect all unit values from initial order requirements
initial_order_units(U) :- init(object(order, _), value(line, pair(_, U))).

% Combine all possible unit values that might be relevant
possible_units(U) :- initial_shelf_units(U).
possible_units(U) :- initial_order_units(U).

% Calculate the Maximum Unit Value

% Calculate the maximum unit value using aggregate
% This predicate will be true, binding M to the max, only if there are 'possible_units'
calculated_max_u(M) :- M = #max { U : possible_units(U) }.

% Determine the final maximum unit value to use
% This predicate 'final_max_u(Max)' will hold exactly one fact in any stable model:
% either the calculated maximum M or the default value 1
final_max_u(M) :- calculated_max_u(M). % Use the calculated maximum M if it exists.
final_max_u(1) :- not calculated_max_u(_). % Otherwise (no units found), default to 1.

% --- Define the Unit Domain ---
% Define units based on the values actually present in the input, plus 1 if needed
% This avoids the grounding issue with dynamic ranges based on aggregates.
unit(U) :- possible_units(U).
unit(1) :- not possible_units(_). % Ensure unit(1) exists if no units are in the input.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Object Declarations from Input
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Object sorts inferred from initialization facts
node(N)           :- init(object(node, N), value(at, _)).
highway(H)        :- init(object(highway, H), value(at, _)).
pickingStation(P) :- init(object(pickingStation, P), value(at, _)).
robot(R)          :- init(object(robot, R), value(at, _)).
shelf(S)          :- init(object(shelf, S), value(at, _)).

product(I)        :- init(object(product, I), value(on, _)).
order(O)          :- init(object(order, O), _).

% Static information extracted from input
pos(object(OType, Name), X, Y) :- init(object(OType, Name), value(at, pair(X,Y))).
initial_quantity(I, S, Q) :- init(object(product, I), value(on, pair(S, Q))).
initial_requirement(O, I, U) :- init(object(order, O), value(line, pair(I, U))).
orderPickingStation(O, P) :- init(object(order, O), value(pickingStation, P)).
is_highway(X, Y) :- pos(object(highway, _), X, Y).
is_picking_station(P, X, Y) :- pos(object(pickingStation, P), X, Y).

%%%%%%%%%%%%%%%%%%%%%%%%%%
% Initial State (Time 0)
%%%%%%%%%%%%%%%%%%%%%%%%%%

% Location of robots and shelves on the grid at T=0
on(robot, R, X, Y, 0) :- pos(object(robot, R), X, Y).
on(shelf, S, X, Y, 0) :- pos(object(shelf, S), X, Y).

% No robot carries a shelf initially
% carries(R, S, 0) is false by default.

% Initial product quantities on shelves
quantity(I, S, Q, 0) :- initial_quantity(I, S, Q).
% Ensure quantity is 0 if not specified
quantity(I, S, 0, 0) :- product(I), shelf(S), not initial_quantity(I, S, _).


% Initial order requirements
requirement(O, I, U, 0) :- initial_requirement(O, I, U).
% Ensure requirement is 0 if not specified
requirement(O, I, 0, 0) :- order(O), product(I), not initial_requirement(O, I, _).


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Action Generation (Choice)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Defining Potential Actions

% Potential Move Action
potential_action(R, move(DX, DY), T) :-
    robot(R), time(T), T > 0,
    DX = -1..1, DY = -1..1, |DX| + |DY| == 1, % valid moves
    on(robot, R, X, Y, T-1),
    X1 = X + DX, Y1 = Y + DY,
    pos(object(node, _), X1, Y1). % target must be a valid grid cell

% Potential Pickup Action
potential_action(R, pickup, T) :-
    robot(R), time(T), T > 0,
    on(robot, R, X, Y, T-1),
    on(shelf, _, X, Y, T-1),   % A shelf must be at the robot's location
    not carries(R, _, T-1).     % Robot must not be carrying anything

% Potential Putdown Action
potential_action(R, putdown, T) :-
    robot(R), time(T), T > 0,
    carries(R, S, T-1),        % Must be carrying a shelf
    on(robot, R, X, Y, T-1),
    not is_highway(X, Y),      % Cannot put down on highway
    not on(shelf, _, X, Y, T-1). % Cannot put down where another shelf is already on the floor

% Potential Deliver Action
potential_action(R, deliver(O, I, U), T) :-
    robot(R), order(O), product(I), unit(U), time(T), T > 0,
    U > 0,                         % Must deliver a positive amount
    on(robot, R, X, Y, T-1),
    orderPickingStation(O, P),
    is_picking_station(P, X, Y),   % Must be at the correct picking station for the order
    carries(R, S, T-1),            % Must be carrying a shelf
    quantity(I, S, Q, T-1), Q >= U,% Shelf must have enough units
    requirement(O, I, RQ, T-1), RQ >= U. % Order must still require at least U units

% Choice rule- choosing at Most One Action Per Robot Per Step
{ occurs(object(robot, R), A, T) : potential_action(R, A, T) } <= 1 :- robot(R), time(T), T > 0.


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% State Update Rules (Effects and Inertia)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Robot Location
% Effect of move
on(robot, R, X1, Y1, T) :-
    occurs(object(robot, R), move(DX, DY), T),
    on(robot, R, X, Y, T-1),
    X1 = X + DX, Y1 = Y + DY.
% Inertia
on(robot, R, X, Y, T) :-
    on(robot, R, X, Y, T-1),
    not occurs(object(robot, R), move(_, _), T), % Robot didn't move
    time(T), T > 0.

% Shelf Location (on floor)
% Effect of putdown
on(shelf, S, X, Y, T) :-
    occurs(object(robot, R), putdown, T),
    carries(R, S, T-1),
    on(robot, R, X, Y, T-1). % Put down at robot's location
% Inertia
on(shelf, S, X, Y, T) :-
    on(shelf, S, X, Y, T-1),
    not shelf_picked_up(S, X, Y, T), % Wasn't picked up from this location
    time(T), T > 0.

% Helper: Shelf S was picked up from X,Y at time T
shelf_picked_up(S, X, Y, T) :-
    occurs(object(robot, R), pickup, T),
    on(robot, R, X, Y, T-1),
    on(shelf, S, X, Y, T-1).

% Carrying State
% Effect of pickup
carries(R, S, T) :-
    occurs(object(robot, R), pickup, T),
    on(robot, R, X, Y, T-1),
    on(shelf, S, X, Y, T-1). % The specific shelf S at that location
% Inertia
carries(R, S, T) :-
    carries(R, S, T-1),
    not occurs(object(robot, R), putdown, T), % Robot didn't put down the shelf it carries
    time(T), T > 0.

% Product Quantity on Shelf
% Effect of deliver
quantity(I, S, Q_new, T) :-
    occurs(object(robot, R), deliver(O, I, U), T),
    carries(R, S, T-1), % Delivery from shelf S carried by R
    quantity(I, S, Q, T-1),
    Q_new = Q - U.
% Inertia (Quantity persists if not delivered from this shelf)
quantity(I, S, Q, T) :-
    quantity(I, S, Q, T-1),
    product(I), shelf(S), % Domain
    not exists_delivery(I, S, T),
    time(T), T > 0.

% Helper: Product I was delivered from shelf S at time T
exists_delivery(I, S, T) :-
    occurs(object(robot, R), deliver(_, I, _), T),
    carries(R, S, T-1).

% Order Requirement
% Effect of deliver
requirement(O, I, RQ_new, T) :-
    occurs(object(robot, R), deliver(O, I, U), T),
    requirement(O, I, RQ, T-1),
    RQ_new = RQ - U.
% Inertia (Requirement persists if not delivered for this order/item)
requirement(O, I, RQ, T) :-
    requirement(O, I, RQ, T-1),
    order(O), product(I), % Domain
    not occurs(object(robot, _), deliver(O, I, _), T),
    time(T), T > 0.


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Constraints
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Action Preconditions (handled by potential_action)
% Additional check to ensure deliver amount is valid
:- occurs(object(robot, R), deliver(O, I, U), T), carries(R, S, T-1), quantity(I, S, Q, T-1), Q < U.
:- occurs(object(robot, R), deliver(O, I, U), T), requirement(O, I, RQ, T-1), RQ < U.
:- occurs(object(robot, R), deliver(O, I, U), T), U <= 0.

% Collision Constraints

% 1. Two robots cannot be in the same cell at the same time
:- on(robot, R1, X, Y, T), on(robot, R2, X, Y, T), R1 != R2.

% 2. Two robots cannot swap cells
:- occurs(object(robot, R1), move(DX, DY), T),
   occurs(object(robot, R2), move(-DX, -DY), T),
   on(robot, R1, X, Y, T-1),
   on(robot, R2, X+DX, Y+DY, T-1).

% 3. Two shelves cannot be on the floor in the same cell at the same time
:- on(shelf, S1, X, Y, T), on(shelf, S2, X, Y, T), S1 != S2.

% 4. A robot carrying a shelf cannot move into a cell occupied by another shelf (on the floor)
:- occurs(object(robot, R), move(DX, DY), T),
   carries(R, S1, T-1), % Robot R is carrying S1
   on(robot, R, X, Y, T-1),
   X1 = X + DX, Y1 = Y + DY, % Target cell
   on(shelf, S2, X1, Y1, T-1). % Another shelf S2 is on the floor at the target cell at T-1
   % Note: S2 must still be there at T for collision, but checking T-1 is sufficient
   % because if S2 was picked up at T, the pickup action would need a robot there at T-1,
   % which would conflict with R moving into X1,Y1 (constraint 1 or 2).

% 5. A robot (carrying or not) cannot move into a cell where another robot *will be* at time T
% This is covered by constraint 1 applied at time T.

% Other Constraints
% Ensure a robot doesn't try to pickup a shelf it's already carrying (redundant as potential_action takes care)
:- occurs(object(robot, R), pickup, T), carries(R, _, T-1).

% Ensure a robot doesn't try to putdown if not carrying (redundant as potential_action takes care)
:- occurs(object(robot, R), putdown, T), not carries(R, _, T-1).

% Ensure a robot doesn't try to deliver if not carrying (redundant as potential_action takes care)
:- occurs(object(robot, R), deliver(_,_,_), T), not carries(R, _, T-1).

% Ensure a shelf is actually present for pickup (redundant as potential_action takes care)
:- occurs(object(robot, R), pickup, T), on(robot, R, X, Y, T-1), not on(shelf, _, X, Y, T-1).


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Goal State and Optimization
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Goal: All order requirements must be met by the final timestep t_max
:- requirement(O, I, U, t_max), U > 0.

% Minimize the makespan (the time of the last action)
#minimize { T : occurs(_, _, T) }.

% Output the plan
#show occurs/3.