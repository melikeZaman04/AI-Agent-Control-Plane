import sys
sys.path.insert(0, sys.argv[1])
from ledger import credit

state = {}
assert credit(state, "a", 7) == 7
assert credit(state, "a", 7) == 7
assert credit(state, "b", 3) == 10
assert credit(state, "a", 7) == 10
assert credit({}, "a", 2) == 2

# Request identity does not change when a retried payload changes.
state = {}
assert credit(state, "request", 7) == 7
assert credit(state, "request", 99) == 7
assert credit(state, "next", 3) == 10
assert credit(state, "request", 0) == 10

# Interleave caller-owned ledgers and then revisit both.
first, second = {}, {}
assert credit(first, "a", 7) == 7
assert credit(second, "b", 3) == 3
assert credit(first, "a", 7) == 7
assert credit(first, "b", 2) == 9
assert credit(second, "a", 4) == 7
assert credit(second, "b", 30) == 7
assert credit(first, "b", 20) == 9
