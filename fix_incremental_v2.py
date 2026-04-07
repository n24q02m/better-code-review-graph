filepath = "src/better_code_review_graph/incremental.py"
with open(filepath) as f:
    lines = f.readlines()

# Look for the duplicated find_dependents
start_idx = -1
for i, line in enumerate(lines):
    if (
        line.startswith("def find_dependents(")
        and i + 1 < len(lines)
        and lines[i + 1].strip()
        == '"""Find files that import from or depend on the given file.'
    ):
        if i + 2 < len(lines) and lines[i + 2].startswith("def find_dependents("):
            start_idx = i
            break

if start_idx != -1:
    # Remove the first two lines (the duplicate definition and docstring)
    del lines[start_idx : start_idx + 2]
    with open(filepath, "w") as f:
        f.writelines(lines)
    print("Successfully fixed duplicated find_dependents")
else:
    print("Could not find duplicated find_dependents")
