import ast
import os


def find_n1_queries(repo_root):
    for root, _, files in os.walk(repo_root):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path) as f:
                    try:
                        content = f.read()
                        tree = ast.parse(content)
                    except Exception as e:
                        print(f"Error parsing {path}: {e}")
                        continue

                    for node in ast.walk(tree):
                        if isinstance(
                            node,
                            (
                                ast.For,
                                ast.While,
                                ast.ListComp,
                                ast.SetComp,
                                ast.DictComp,
                                ast.GeneratorExp,
                            ),
                        ):
                            # Look for calls to store methods inside loops/comprehensions
                            for subnode in ast.walk(node):
                                if isinstance(subnode, ast.Call):
                                    func_name = None
                                    if isinstance(subnode.func, ast.Attribute):
                                        func_name = subnode.func.attr
                                    elif isinstance(subnode.func, ast.Name):
                                        func_name = subnode.func.id

                                    if func_name in [
                                        "get_node",
                                        "get_nodes_by_file",
                                        "get_edges_by_source",
                                        "get_edges_by_target",
                                    ]:
                                        # Verify it's likely a method call on a store object
                                        print(
                                            f"Potential N+1 in {path}:{subnode.lineno}: {func_name}"
                                        )


if __name__ == "__main__":
    find_n1_queries("src")
