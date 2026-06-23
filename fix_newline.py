import sys

content = open('src/better_code_review_graph/tools.py').read()

bad_snippet = """                    snippets[rel_path] = '
'.join("""

good_snippet = """                    snippets[rel_path] = '\n'.join("""

if bad_snippet in content:
    new_content = content.replace(bad_snippet, good_snippet)
    with open('src/better_code_review_graph/tools.py', 'w') as f:
        f.write(new_content)
    print("Success")
else:
    print("Bad snippet not found")
