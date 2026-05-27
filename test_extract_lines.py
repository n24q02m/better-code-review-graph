import random
import time


class Node:
    def __init__(self, fp, ls, le):
        self.file_path = fp
        self.line_start = ls
        self.line_end = le


nodes = [
    Node(
        f"file{random.randint(0, 100)}.py",
        random.randint(0, 100),
        random.randint(100, 200),
    )
    for _ in range(1000)
]
file_path = "file50.py"


def original():
    start = time.time()
    for _ in range(1000):
        ranges = []
        for n in nodes:
            if n.file_path == file_path:
                start_l = max(0, n.line_start - 3)
                end_l = min(1000, n.line_end + 2)
                ranges.append((start_l, end_l))
    return time.time() - start


print(original())
