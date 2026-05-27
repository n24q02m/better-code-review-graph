class N:
    def __init__(self, fp, ls, le):
        self.file_path = fp
        self.line_start = ls
        self.line_end = le


nodes = [N("file1.py", i, i + 2) for i in range(1, 1000, 10)] + [N("file2.py", 1, 5)]


def original(nodes, fp):
    import time

    start = time.time()
    for _ in range(1000):
        ranges = []
        for n in nodes:
            if n.file_path == fp:
                ranges.append((max(0, n.line_start - 3), n.line_end + 2))
    return time.time() - start


print(original(nodes, "file1.py"))
