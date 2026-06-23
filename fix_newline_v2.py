import sys

with open('src/better_code_review_graph/tools.py', 'rb') as f:
    content = f.read()

# Look for the hex pattern of '\n'.join where \n is a literal newline
# ' is 0x27, \n is 0x0a
bad_pattern = b"snippets[rel_path] = '\n'.join("
good_pattern = b"snippets[rel_path] = '\\n'.join("

if bad_pattern in content:
    new_content = content.replace(bad_pattern, good_pattern)
    with open('src/better_code_review_graph/tools.py', 'wb') as f:
        f.write(new_content)
    print("Success")
else:
    print("Bad pattern not found")
