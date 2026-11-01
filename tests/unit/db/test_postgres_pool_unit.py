from __future__ import annotations

from typing import Any

from octop.infra.db.pool import _PgConnectionProxy, qmark_to_pyformat


def test_qmark_to_pyformat_replaces_placeholders():
    assert qmark_to_pyformat("SELECT * FROM t WHERE a = ? AND b = ?") == (
        "SELECT * FROM t WHERE a = %s AND b = %s"
    )


def test_qmark_to_pyformat_leaves_percent_alone():
    assert qmark_to_pyformat("SELECT %s") == "SELECT %s"


class _RecordingCursor:
    """Cursor double: psycopg exposes ``executemany`` here, not on the connection."""

    def __init__(self, owner: _CursorOnlyConnection) -> None:
        self._owner = owner
        self.rowcount = -1

    def executemany(self, sql: str, seq_of_params: Any) -> _RecordingCursor:
        rows = list(seq_of_params)
        self._owner.calls.append((sql, rows))
        self.rowcount = len(rows)
        return self


class _CursorOnlyConnection:
    """Mimics psycopg3's ``Connection``: no ``executemany`` attribute of its own."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Any]]] = []

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self)


def test_executemany_rewrites_placeholders_and_forwards_rows():
    conn = _CursorOnlyConnection()
    proxy = _PgConnectionProxy(conn)
    rows = [("a", 1), ("b", 2)]

    proxy.executemany("INSERT INTO t(x, y) VALUES (?, ?)", rows)

    assert conn.calls == [("INSERT INTO t(x, y) VALUES (%s, %s)", rows)]


def test_executemany_does_not_delegate_to_the_psycopg_connection():
    # The regression: plain delegation raised AttributeError because psycopg only defines
    # executemany on Cursor, and callers swallow that error, so rows vanished silently.
    proxy = _PgConnectionProxy(_CursorOnlyConnection())

    result = proxy.executemany("INSERT INTO t(x) VALUES (?)", [("a",)])

    assert result.rowcount == 1


def test_executemany_accepts_an_empty_row_sequence():
    conn = _CursorOnlyConnection()
    proxy = _PgConnectionProxy(conn)

    proxy.executemany("INSERT INTO t(x) VALUES (?)", [])

    assert conn.calls == [("INSERT INTO t(x) VALUES (%s)", [])]
