"""CLI(cli.py)와 같은 로직을 REST API로 노출하는 FastAPI 앱.

cli.py는 print 중심이라 그대로 재사용하지 않고, db.py/similarity.py/graph.py/
boredom.py/metadata 쪽 저수준 함수를 직접 호출해 JSON으로 반환한다(파이프라인
트리거 엔드포인트는 예외적으로 cli.py 함수를 그대로 호출한다 — 배치 성격이라
로직 중복이 오히려 더 나쁨). SQLite를 그대로 쓴다 — 아직 5곡짜리 테스트 규모라
Postgres 이관은 과함. CLI와 나란히 쓰는 두 번째 인터페이스로 둔다.
"""

from __future__ import annotations

import sqlite3

from fastapi import Depends, FastAPI, HTTPException

from .db import connect

DEFAULT_DB_PATH = "digger.db"

TRACK_COLUMNS = ["id", "artist", "title", "album", "bpm", "key", "key_scale", "energy", "duration_sec"]

app = FastAPI(title="digger API")


def get_db():
    conn = connect(DEFAULT_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def _get_track_row(conn: sqlite3.Connection, track_id: int) -> tuple:
    row = conn.execute(
        "SELECT id, artist, title, album, bpm, key, key_scale, energy, duration_sec, mb_recording_id "
        "FROM tracks WHERE id = ?",
        (track_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"트랙을 찾을 수 없음: id={track_id}")
    return row


@app.get("/tracks")
def list_tracks(conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = conn.execute(
        f"SELECT {', '.join(TRACK_COLUMNS)} FROM tracks ORDER BY id"
    ).fetchall()
    return [dict(zip(TRACK_COLUMNS, row)) for row in rows]


@app.get("/tracks/{track_id}")
def get_track(track_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    columns = [*TRACK_COLUMNS, "mb_recording_id"]
    track = dict(zip(columns, _get_track_row(conn, track_id)))

    tags = conn.execute(
        "SELECT source, tag_type, raw_tag, weight, canonical_style FROM track_tags WHERE track_id = ?",
        (track_id,),
    ).fetchall()
    track["tags"] = [
        {"source": s, "tag_type": t, "raw_tag": r, "weight": w, "canonical_style": c} for s, t, r, w, c in tags
    ]
    return track
