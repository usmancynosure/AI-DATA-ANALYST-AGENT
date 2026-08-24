import pytest

from app.datasources.sql_guard import UnsafeQueryError, ensure_read_only


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM sales",
        "select id, name from users where name = 'bob'",
        "WITH t AS (SELECT 1 AS x) SELECT * FROM t",
        "SELECT * FROM t WHERE note = 'please delete everything'",  # keyword inside literal
        "  SELECT 1 ;  ",  # trailing semicolon on single statement
    ],
)
def test_allows_read_only(query):
    assert ensure_read_only(query)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM sales",
        "DROP TABLE users",
        "UPDATE users SET admin = true",
        "INSERT INTO t VALUES (1)",
        "SELECT 1; DROP TABLE users",  # stacked statement
        "SELECT * FROM t; SELECT * FROM u",  # multiple statements
        "TRUNCATE t",
        "ALTER TABLE t ADD COLUMN x INT",
        "PRAGMA table_info(t)",
        "ATTACH 'evil.db' AS e",
        "COPY t TO '/tmp/x.csv'",
        "",
        "   ",
    ],
)
def test_rejects_non_read_only(query):
    with pytest.raises(UnsafeQueryError):
        ensure_read_only(query)


def test_comment_smuggling_is_stripped():
    # A comment cannot hide a second statement.
    with pytest.raises(UnsafeQueryError):
        ensure_read_only("SELECT 1 -- comment\n; DROP TABLE t")
