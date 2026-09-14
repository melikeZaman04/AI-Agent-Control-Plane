import sys
sys.path.insert(0, sys.argv[1])
from ledger import credit

state = {}
assert credit(state, "a", 7) == 7
assert credit(state, "a", 7) == 7
assert credit(state, "b", 3) == 10
assert credit(state, "a", 7) == 10
assert credit({}, "a", 2) == 2
