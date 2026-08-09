from app.shared.database.postgres_store import _compile


def test_is_placeholder_is_portable():
    sql, bind = _compile("SELECT * FROM users WHERE tenant_id IS ? AND email=?", ("tenant-a", "x@example.com"))
    assert "tenant_id = :p0" in sql
    assert bind == {"p0": "tenant-a", "p1": "x@example.com"}


def test_is_null_remains_null_predicate():
    sql, bind = _compile("SELECT * FROM users WHERE tenant_id IS ? AND email=?", (None, "x@example.com"))
    assert "tenant_id IS NULL" in sql
    assert bind == {"p1": "x@example.com"}


def test_insert_or_ignore_becomes_on_conflict_do_nothing():
    sql, bind = _compile("INSERT OR IGNORE INTO bank_transactions(id,external_id) VALUES(?,?)", ("a", "b"))
    assert sql.startswith("INSERT INTO bank_transactions")
    assert sql.endswith("ON CONFLICT DO NOTHING")
    assert bind == {"p0": "a", "p1": "b"}
