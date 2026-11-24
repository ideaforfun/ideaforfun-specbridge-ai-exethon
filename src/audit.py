"""Append-only local workflow history."""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("REQUESTED", "REVIEWED", "CHANGES_REQUIRED")


def scope_key(*values) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _connect(path: Path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS review_log (
                id INTEGER PRIMARY KEY,
                scope TEXT NOT NULL, target TEXT NOT NULL, actor TEXT NOT NULL,
                status TEXT NOT NULL, note TEXT NOT NULL, recorded_at TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS review_log_scope ON review_log(scope, target, id)")
    except sqlite3.Error:
        db.close()
        raise
    return db


def _validate(actor, note):
    if not actor.strip() or len(actor.strip()) > 80 or not note.strip() or len(note.strip()) > 2000:
        raise ValueError("이름 또는 식별자(80자 이하)와 사유(2,000자 이하)를 입력하세요.")


def history(path: Path, scope: str) -> list[dict]:
    with closing(_connect(path)) as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM review_log WHERE scope = ? ORDER BY id DESC", (scope,))]


def request_reviews(path: Path, scope: str, targets: list[str], actor: str, note: str) -> int:
    _validate(actor,note)
    if not targets:
        raise ValueError("검토 요청 부서를 선택하세요.")
    with closing(_connect(path)) as db, db:
        inserted = 0
        for target in targets:
            row = db.execute("""
                INSERT INTO review_log(scope,target,actor,status,note,recorded_at)
                SELECT ?,?,?,'REQUESTED',?,?
                WHERE NOT EXISTS (SELECT 1 FROM review_log WHERE scope=? AND target=?)
            """,(scope,target,actor.strip(),note.strip(),datetime.now(timezone.utc).isoformat(),scope,target))
            inserted += row.rowcount
        return inserted


def save_result(path: Path, scope: str, target: str, actor: str, status: str, note: str, *, expected_id=None):
    _validate(actor,note)
    data = (scope,target,actor.strip(),status,note.strip(),datetime.now(timezone.utc).isoformat())
    with closing(_connect(path)) as db, db:
        if expected_id is None:
            db.execute("INSERT INTO review_log(scope,target,actor,status,note,recorded_at) VALUES(?,?,?,?,?,?)",data)
        else:
            cursor = db.execute("""
                INSERT INTO review_log(scope,target,actor,status,note,recorded_at)
                SELECT ?,?,?,?,?,?
                WHERE (SELECT MAX(id) FROM review_log WHERE scope=? AND target=?) = ?
            """,(*data,scope,target,expected_id))
            if not cursor.rowcount:
                raise ValueError("다른 검토 결과가 기록되었습니다. 최신 이력을 확인해 주세요.")
