"""
Schema execution verification test.
"""

import sqlite3

from src import config


def test_schema_sql_syntax():
    """Verifies that data/schema.sql parses and executes without error in SQLite."""
    schema_path = config.get_schema_path()
    assert schema_path.exists(), f"Schema file not found at {schema_path}"

    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    conn = sqlite3.connect(":memory:")
    conn.executescript(sql)

    # Check created tables
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "conversations" in tables
    assert "facts" in tables
    conn.close()
