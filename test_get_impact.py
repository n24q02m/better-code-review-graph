import random
import time


def original(impact):
    tested_qns = set()
    for e in impact["edges"]:
        if e.kind == "TESTED_BY":
            tested_qns.add(e.source_qualified)
            tested_qns.add(e.target_qualified)
    out = []
    for n in impact["changed_nodes"]:
        if n.kind != "Function" or n.is_test:
            continue
        if n.qualified_name in tested_qns:
            continue
        out.append(n)
    return out


class E:
    def __init__(self, k, s, t):
        self.kind = k
        self.source_qualified = s
        self.target_qualified = t


class N:
    def __init__(self, k, it, qn):
        self.kind = k
        self.is_test = it
        self.qualified_name = qn


edges = [
    E(random.choice(["TESTED_BY", "CALLS"]), f"qn{i}", f"qn{i + 1}")
    for i in range(100000)
]
nodes = [
    N(random.choice(["Function", "Class"]), random.choice([True, False]), f"qn{i}")
    for i in range(100000)
]
impact = {"edges": edges, "changed_nodes": nodes}

start = time.time()
for _ in range(100):
    original(impact)
print(f"Original: {time.time() - start:.4f}s")
