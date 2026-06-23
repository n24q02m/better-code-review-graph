import sys

content = open('src/better_code_review_graph/tools.py').read()

search_text = """    for rel_path in unique_files:
        full_path_raw = root / rel_path
        try:
            parent_raw = full_path_raw.parent
            if parent_raw not in parent_cache:
                try:
                    parent_cache[parent_raw] = parent_raw.resolve(strict=True)
                except OSError:
                    parent_cache[parent_raw] = None

            parent_resolved = parent_cache[parent_raw]
            if parent_resolved:
                full_path = parent_resolved / full_path_raw.name
            else:
                full_path = full_path_raw.resolve()

            if not full_path.is_relative_to(root_resolved):
                continue
            if full_path_raw.is_symlink() or full_path.is_symlink():
                continue

            if full_path.is_file():"""

replace_text = """    for rel_path in unique_files:
        full_path = _resolve_secure_path(root, root_resolved, rel_path, parent_cache)
        if not full_path:
            continue

        if full_path.is_file():"""

if search_text in content:
    new_content = content.replace(search_text, replace_text)
    with open('src/better_code_review_graph/tools.py', 'w') as f:
        f.write(new_content)
    print("Success")
else:
    print("Search text not found")
