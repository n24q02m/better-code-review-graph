import random
import time


class Edge:
    def __init__(self, k, sq, tq):
        self.kind = k
        self.source_qualified = sq
        self.target_qualified = tq


class Node:
    def __init__(self, k, it, qn, l):
        self.kind = k
        self.is_test = it
        self.qualified_name = qn
        self.language = l
        self.name = qn


edges = [
    Edge(
        random.choice(["TESTED_BY", "CALLS", "INHERITS", "IMPLEMENTS"]),
        f"s{i}",
        f"t{i}",
    )
    for i in range(100000)
]
nodes = [
    Node(
        random.choice(["Function", "Class"]),
        random.choice([True, False]),
        f"qn{i}",
        "python",
    )
    for i in range(100000)
]


def original(impact):
    start = time.time()
    tested_funcs = set()
    inheritance_edges_count = 0
    for e in impact["edges"]:
        if e.kind == "TESTED_BY":
            tested_funcs.add(e.source_qualified)
            # Wait, `_compute_untested_functions` adds both source and target.
            # Here it only adds `source_qualified`! Wait, tests call the function, so the function is the target of TESTED_BY...
            # Actually TESTED_BY edge is from the function TO the test? Wait, let's check `_handle_tests_for`
    return time.time() - start


print(
    original(
        {
            "edges": edges,
            "changed_nodes": nodes,
            "impacted_nodes": [],
            "impacted_files": [],
        }
    )
)
