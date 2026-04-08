import subprocess
for i in range(230, 210, -1):
    cmd = f"curl -s https://github.com/n24q02m/better-code-review-graph/pull/{i} | grep '<title>'"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if "Search Nodes" in res.stdout:
        print(f"PR {i}: {res.stdout.strip()}")
