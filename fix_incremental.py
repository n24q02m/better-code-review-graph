import sys

filepath = "src/better_code_review_graph/incremental.py"
with open(filepath) as f:
    lines = f.readlines()

start_line = -1
end_line = -1
for i, line in enumerate(lines):
    if "def incremental_update(" in line:
        start_line = i
    if start_line != -1 and '"files_updated": len(all_files),' in line:
        # Find the end of the return dict
        j = i
        while "}" not in lines[j]:
            j += 1
        end_line = j + 1
        break

if start_line != -1 and end_line != -1:
    new_func = """def incremental_update(
    repo_root: Path,
    store: GraphStore,
    base: str = "HEAD~1",
    changed_files: list[str] | None = None,
) -> dict:
    \"\"\"Incremental update: re-parse changed + dependent files only.\"\"\"
    parser = CodeParser()
    ignore_patterns = _load_ignore_patterns(repo_root)

    # Determine changed files
    if changed_files is None:
        changed_files = get_changed_files(repo_root, base)

    if not changed_files:
        return {
            "files_updated": 0,
            "total_nodes": 0,
            "total_edges": 0,
            "changed_files": [],
            "dependent_files": [],
        }

    # Find dependent files (files that import from changed files)
    dependent_files: set[str] = set()
    repo_resolved = repo_root.resolve()
    for rel_path in changed_files:
        full_path_raw = repo_root / rel_path
        full_path = full_path_raw.resolve()
        if not full_path.is_relative_to(repo_resolved):
            continue
        if full_path_raw.is_symlink() or full_path.is_symlink():
            continue

        deps = find_dependents(store, str(full_path))
        for d in deps:
            # Convert back to relative path if needed
            try:
                dependent_files.add(str(Path(d).relative_to(repo_root)))
            except ValueError:
                dependent_files.add(d)

    # Combine changed + dependent
    all_files = set(changed_files) | dependent_files

    # Pre-fetch existing nodes to avoid N+1 queries
    abs_paths = []
    for rel_path in all_files:
        abs_path = (repo_root / rel_path).resolve()
        abs_paths.append(str(abs_path))

    existing_nodes_batch = store.get_nodes_by_files(abs_paths)
    file_to_hash = {n.file_path: n.file_hash for n in existing_nodes_batch}

    total_nodes = 0
    total_edges = 0
    errors = []

    for rel_path in all_files:
        if _should_ignore(rel_path, ignore_patterns):
            continue
        abs_path_raw = repo_root / rel_path
        abs_path = abs_path_raw.resolve()
        if not abs_path.is_relative_to(repo_root.resolve()):
            continue
        abs_path_str = str(abs_path)
        if not abs_path.is_file():
            # File was deleted
            store.remove_file_data(abs_path_str)
            continue
        if abs_path_raw.is_symlink() or abs_path.is_symlink():
            continue
        if parser.detect_language(abs_path) is None:
            continue

        try:
            source = abs_path.read_bytes()
            fhash = hashlib.sha256(source).hexdigest()

            # Check if file actually changed using pre-fetched hash
            if file_to_hash.get(abs_path_str) == fhash:
                continue

            nodes, edges = parser.parse_bytes(abs_path, source)
            store.store_file_nodes_edges(abs_path_str, nodes, edges, fhash)
            total_nodes += len(nodes)
            total_edges += len(edges)
        except (OSError, PermissionError) as e:
            errors.append({"file": rel_path, "error": str(e)})
        except Exception as e:
            logger.warning("Error parsing %s: %s", rel_path, e)
            errors.append({"file": rel_path, "error": str(e)})

    store.set_metadata("last_updated", time.strftime("%Y-%m-%dT%H:%M:%S"))
    store.set_metadata("last_build_type", "incremental")
    store.commit()

    return {
        "files_updated": len(all_files),
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "changed_files": list(changed_files),
        "dependent_files": list(dependent_files),
        "errors": errors,
    }
"""
    lines[start_line:end_line] = [new_func + "\n"]
    with open(filepath, "w") as f:
        f.writelines(lines)
    print("Successfully patched incremental_update")
else:
    print(f"Could not find incremental_update: {start_line}, {end_line}")
    sys.exit(1)
