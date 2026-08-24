"""Read-only SQL validation.

Generated SQL is untrusted: it is produced by an LLM from natural language and may
be influenced by the contents of the data itself (prompt injection). Before any query
runs we require that it be a single, read-only statement. This is a defense-in-depth
layer on top of using a read-only DB connection/role where possible.
"""

from __future__ import annotations

import re


class UnsafeQueryError(ValueError):
    """Raised when a query is not a single read-only statement."""


# Statements that read data. Everything else is rejected.
_ALLOWED_LEADING = ("select", "with")

# Keywords that mutate state or schema — rejected anywhere they appear as a token.
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "insert", "update", "delete", "drop", "truncate", "alter", "create",
        "replace", "merge", "grant", "revoke", "attach", "detach", "copy",
        "call", "execute", "exec", "vacuum", "pragma", "set", "reset",
        "install", "load", "export", "import",
    }
)

_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"--[^\n]*")
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def _strip_comments(sql: str) -> str:
    sql = _COMMENT_BLOCK.sub(" ", sql)
    sql = _COMMENT_LINE.sub(" ", sql)
    return sql


def _split_statements(sql: str) -> list[str]:
    """Naive split on semicolons that are outside string literals."""
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            current.append(ch)
            if ch == quote:
                # handle doubled-quote escape ('' or "")
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    current.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            current.append(ch)
        elif ch == ";":
            statements.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        statements.append("".join(current))
    return [s.strip() for s in statements if s.strip()]


def _string_literal_spans(sql: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of string literals so we can ignore keywords inside them."""
    spans: list[tuple[int, int]] = []
    quote: str | None = None
    start = 0
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                spans.append((start, i))
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            start = i
        i += 1
    return spans


def ensure_read_only(sql: str) -> str:
    """Validate that ``sql`` is a single read-only statement. Returns the cleaned SQL.

    Raises :class:`UnsafeQueryError` otherwise.
    """
    if not sql or not sql.strip():
        raise UnsafeQueryError("Empty query.")

    cleaned = _strip_comments(sql).strip()
    statements = _split_statements(cleaned)

    if len(statements) == 0:
        raise UnsafeQueryError("Empty query.")
    if len(statements) > 1:
        raise UnsafeQueryError("Only a single statement is allowed; multiple statements detected.")

    statement = statements[0]
    lowered = statement.lower()

    if not lowered.startswith(_ALLOWED_LEADING):
        raise UnsafeQueryError(
            "Only read-only SELECT/WITH queries are allowed."
        )

    # Scan tokens outside of string literals for forbidden keywords.
    literal_spans = _string_literal_spans(statement)

    def in_literal(pos: int) -> bool:
        return any(a <= pos <= b for a, b in literal_spans)

    for match in _TOKEN.finditer(lowered):
        if in_literal(match.start()):
            continue
        if match.group() in _FORBIDDEN_KEYWORDS:
            raise UnsafeQueryError(
                f"Query contains a forbidden keyword: '{match.group()}'."
            )

    return statement
