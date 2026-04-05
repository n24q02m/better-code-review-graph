import sys

def fix_test_file(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # Add sqlite3 import
    if "import sqlite3" not in "".join(lines):
        lines.insert(4, "import sqlite3\n")

    with open(file_path, 'w') as f:
        f.writelines(lines)

if __name__ == "__main__":
    fix_test_file(sys.argv[1])
