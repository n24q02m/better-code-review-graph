import sys

with open('src/better_code_review_graph/tools.py', 'r') as f:
    lines = f.readlines()

# Indentation fix for _get_source_snippets
# Looking for the loop starting at rel_path in unique_files
start_line = -1
for i, line in enumerate(lines):
    if "for rel_path in unique_files:" in line and i > 1900:
        start_line = i
        break

if start_line != -1:
    # Lines after the loop header
    # 1945: full_path = ...
    # 1946: if not full_path:
    # 1947:     continue
    # 1948:
    # 1949: if full_path.is_file():
    # 1950:       try:

    # We want to re-indent from line 1950 to the end of the loop
    # Let's just rewrite the whole loop body to be sure

    loop_body = [
        "        full_path = _resolve_secure_path(root, root_resolved, rel_path, parent_cache)\n",
        "        if not full_path:\n",
        "            continue\n",
        "\n",
        "        if full_path.is_file():\n",
        "            try:\n",
        "                lines_content = full_path.read_text(errors='replace').splitlines()\n",
        "                if len(lines_content) > max_lines_per_file:\n",
        "                    snippets[rel_path] = _extract_relevant_lines(\n",
        "                        lines_content, changed_nodes, str(full_path)\n",
        "                    )\n",
        "                else:\n",
        "                    snippets[rel_path] = '\n'.join(\n",
        "                        f'{i + 1}: {line}' for i, line in enumerate(lines_content)\n",
        "                    )\n",
        "            except (OSError, UnicodeDecodeError):\n",
        "                snippets[rel_path] = '(could not read file)'\n"
    ]

    # Find where the next function starts to know where to stop replacing
    end_line = -1
    for i in range(start_line + 1, len(lines)):
        if line.startswith("def _build_review_summary_text"): # Wait, need to check the actual next function name
             pass
        if "return snippets" in lines[i]:
            end_line = i
            break

    if end_line != -1:
        new_lines = lines[:start_line + 1] + loop_body + lines[end_line:]
        with open('src/better_code_review_graph/tools.py', 'w') as f:
            f.writelines(new_lines)
        print("Success")
    else:
        print("Could not find end of loop")
else:
    print("Could not find start of loop")
