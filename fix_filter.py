import sys

content = open('src/better_code_review_graph/tools.py').read()

search_text = """    for f in changed_files:
        if f in result_cache:
            res = result_cache[f]
            if res is not None:
                abs_files.append(res)
            continue

        full_path_raw = root / f
        try:
            parent_raw = full_path_raw.parent
            if parent_raw not in parent_cache:
                try:
                    parent_cache[parent_raw] = parent_raw.resolve(strict=True)
                except OSError:
                    # Parent directory might not exist yet if it's a deleted file,
                    # fallback to resolving the full path.
                    parent_cache[parent_raw] = None

            parent_resolved = parent_cache[parent_raw]
            if parent_resolved:
                full_path = parent_resolved / full_path_raw.name
            else:
                full_path = full_path_raw.resolve()

            if not full_path.is_relative_to(root_resolved):
                result_cache[f] = None
                continue

            if full_path_raw.is_symlink() or full_path.is_symlink():
                result_cache[f] = None
                continue

            res_str = str(full_path)
            result_cache[f] = res_str
            abs_files.append(res_str)
        except (OSError, ValueError):
            result_cache[f] = None
            continue"""

replace_text = """    for f in changed_files:
        if f in result_cache:
            res = result_cache[f]
            if res is not None:
                abs_files.append(res)
            continue

        full_path = _resolve_secure_path(root, root_resolved, f, parent_cache)
        if full_path:
            res_str = str(full_path)
            result_cache[f] = res_str
            abs_files.append(res_str)
        else:
            result_cache[f] = None"""

if search_text in content:
    new_content = content.replace(search_text, replace_text)
    with open('src/better_code_review_graph/tools.py', 'w') as f:
        f.write(new_content)
    print("Success")
else:
    print("Search text not found")
