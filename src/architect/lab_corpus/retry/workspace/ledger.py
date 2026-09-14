def credit(state, request_id, amount):
    state["balance"] = state.get("balance", 0) + amount
    return state["balance"]
