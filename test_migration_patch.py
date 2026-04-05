import sys

def patch_test_file(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()

    new_test = [
        "    def test_migration_adds_provider_column(self, tmp_path):\n",
        "        \"\"\"Test that provider column is added if missing (schema migration).\"\"\"\n",
        "        db_path = tmp_path / \"migration.db\"\n",
        "        # Manually create old schema\n",
        "        conn = sqlite3.connect(str(db_path))\n",
        "        conn.execute(\"\"\"\n",
        "            CREATE TABLE embeddings (\n",
        "                qualified_name TEXT PRIMARY KEY,\n",
        "                vector BLOB NOT NULL,\n",
        "                text_hash TEXT NOT NULL\n",
        "            );\n",
        "        \"\"\")\n",
        "        conn.close()\n",
        "\n",
        "        # Initialize store - should trigger migration\n",
        "        store = EmbeddingStore(db_path)\n",
        "        \n",
        "        # Verify provider column exists\n",
        "        cursor = store._conn.execute(\"PRAGMA table_info(embeddings)\")\n",
        "        columns = [row[\"name\"] for row in cursor.fetchall()]\n",
        "        assert \"provider\" in columns\n",
        "        store.close()\n",
        "\n"
    ]

    for i, line in enumerate(lines):
        if "class TestEmbeddingStore:" in line:
            lines.insert(i + 1, "".join(new_test))
            break

    with open(file_path, 'w') as f:
        f.writelines(lines)

if __name__ == "__main__":
    patch_test_file(sys.argv[1])
