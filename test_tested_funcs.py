import random
import time


class Edge:
    def __init__(self, k, sq, tq):
        self.kind = k
        self.source_qualified = sq
        self.target_qualified = tq


edges = [
    Edge(random.choice(["TESTED_BY", "CALLS"]), f"s{i}", f"t{i}") for i in range(100000)
]


def original(edges):
    start = time.time()
    tested_funcs = set()
    for e in edges:
        if e.kind == "TESTED_BY":
            tested_funcs.add(e.target_qualified)
            tested_funcs.add(e.source_qualified)
    return time.time() - start


print(original(edges))
