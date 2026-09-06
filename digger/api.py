"""CLI(cli.py)와 같은 로직을 REST API로 노출하는 FastAPI 앱.

cli.py는 print 중심이라 그대로 재사용하지 않고, db.py/similarity.py/graph.py/
boredom.py/metadata 쪽 저수준 함수를 직접 호출해 JSON으로 반환한다(파이프라인
트리거 엔드포인트는 예외적으로 cli.py 함수를 그대로 호출한다 — 배치 성격이라
로직 중복이 오히려 더 나쁨). SQLite를 그대로 쓴다 — 아직 5곡짜리 테스트 규모라
Postgres 이관은 과함. CLI와 나란히 쓰는 두 번째 인터페이스로 둔다.
"""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from .boredom import compute_boredom_scores
from .db import connect, insert_feedback
from .graph import dig_relations
from .relations import CATEGORIES
from .similarity import DEFAULT_ZONE_HIGH, DEFAULT_ZONE_LOW, find_digging_zone, find_similar

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


@app.get("/tracks/{track_id}/similar")
def get_similar(
    track_id: int,
    top: int = 5,
    dig: bool = False,
    zone_low: float = DEFAULT_ZONE_LOW,
    zone_high: float = DEFAULT_ZONE_HIGH,
    boredom_weight: float = 0.0,
    exclude_tired_above: float | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict]:
    """장르 태그 유사도 기준 유사곡. dig=True면 [zone_low, zone_high] 구간의 디깅 존 탐색."""
    _get_track_row(conn, track_id)
    boredom_scores = (
        compute_boredom_scores(conn) if (boredom_weight > 0 or exclude_tired_above is not None) else None
    )

    try:
        if dig:
            results = find_digging_zone(
                conn,
                track_id,
                top_n=top,
                zone_low=zone_low,
                zone_high=zone_high,
                boredom_scores=boredom_scores,
                boredom_weight=boredom_weight,
                exclude_tired_above=exclude_tired_above,
            )
        else:
            results = find_similar(
                conn,
                track_id,
                top_n=top,
                boredom_scores=boredom_scores,
                boredom_weight=boredom_weight,
                exclude_tired_above=exclude_tired_above,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return [dict(r._asdict()) for r in results]


@app.get("/tracks/{track_id}/relations")
def get_relations(
    track_id: int,
    category: str,
    top: int = 10,
    include_known: bool = False,
    exclude_tired_above: float | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict]:
    """협업/레이블/샘플/영향 관계 축을 따라가 발견 후보를 찾는다."""
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category는 {CATEGORIES} 중 하나여야 함")

    _, artist, title, *_rest, mb_recording_id = _get_track_row(conn, track_id)
    boredom_scores = compute_boredom_scores(conn) if exclude_tired_above is not None else None

    return dig_relations(
        conn,
        track_id,
        artist,
        title,
        mb_recording_id,
        category,
        top_n=top,
        include_known=include_known,
        boredom_scores=boredom_scores,
        exclude_tired_above=exclude_tired_above,
    )


@app.get("/boredom")
def get_boredom_ranking(top: int = 10, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    scores = compute_boredom_scores(conn)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top]
    results = []
    for track_id, score in ranked:
        row = conn.execute("SELECT artist, title FROM tracks WHERE id = ?", (track_id,)).fetchone()
        artist, title = row if row else (None, None)
        results.append({"track_id": track_id, "artist": artist, "title": title, "boredom_score": score})
    return results


class FeedbackIn(BaseModel):
    track_id: int
    action: Literal["like", "skip"]
    context: str | None = None
    seed_track_id: int | None = None


@app.post("/feedback", status_code=201)
def post_feedback(body: FeedbackIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _get_track_row(conn, body.track_id)
    if body.seed_track_id is not None:
        _get_track_row(conn, body.seed_track_id)
    insert_feedback(conn, body.track_id, body.action, context=body.context, seed_track_id=body.seed_track_id)
    return {"status": "ok"}


@app.get("/feedback")
def get_feedback_log(top: int = 20, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = conn.execute(
        """
        SELECT f.id, f.created_at, f.track_id, t.artist, t.title, f.action, f.context,
               f.seed_track_id, s.artist, s.title
        FROM feedback f
        JOIN tracks t ON t.id = f.track_id
        LEFT JOIN tracks s ON s.id = f.seed_track_id
        ORDER BY f.created_at DESC
        LIMIT ?
        """,
        (top,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "created_at": r[1],
            "track_id": r[2],
            "artist": r[3],
            "title": r[4],
            "action": r[5],
            "context": r[6],
            "seed_track_id": r[7],
            "seed_artist": r[8],
            "seed_title": r[9],
        }
        for r in rows
    ]
