"""분석 결과를 저장하는 SQLite 특성 벡터 DB."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    artist TEXT,
    title TEXT,
    album TEXT,
    bpm REAL,
    key TEXT,
    key_scale TEXT,
    energy REAL,
    duration_sec REAL,
    raw_features TEXT,
    analyzed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS track_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    source TEXT NOT NULL,
    tag_type TEXT NOT NULL,
    raw_tag TEXT NOT NULL,
    weight REAL,
    canonical_style TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(track_id, source, tag_type, raw_tag)
);

CREATE TABLE IF NOT EXISTS listening_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spotify_track_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    played_at TEXT NOT NULL,
    track_id INTEGER REFERENCES tracks(id),
    fetched_at TEXT NOT NULL,
    UNIQUE(spotify_track_id, played_at)
);

CREATE TABLE IF NOT EXISTS top_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spotify_track_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    time_range TEXT NOT NULL,
    rank INTEGER NOT NULL,
    track_id INTEGER REFERENCES tracks(id),
    fetched_at TEXT NOT NULL,
    UNIQUE(spotify_track_id, time_range)
);

CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    from_entity_type TEXT NOT NULL,
    from_entity_id TEXT NOT NULL,
    from_entity_name TEXT,
    to_entity_type TEXT NOT NULL,
    to_entity_id TEXT,
    to_entity_name TEXT NOT NULL,
    to_entity_key TEXT NOT NULL,
    attributes TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(source, relation_type, from_entity_type, from_entity_id, to_entity_type, to_entity_key)
);
"""

_UPSERT_SQL = """
INSERT INTO tracks (file_path, artist, title, album, bpm, key, key_scale, energy, duration_sec, raw_features, analyzed_at)
VALUES (:file_path, :artist, :title, :album, :bpm, :key, :key_scale, :energy, :duration_sec, :raw_features, :analyzed_at)
ON CONFLICT(file_path) DO UPDATE SET
    artist=excluded.artist,
    title=excluded.title,
    album=excluded.album,
    bpm=excluded.bpm,
    key=excluded.key,
    key_scale=excluded.key_scale,
    energy=excluded.energy,
    duration_sec=excluded.duration_sec,
    raw_features=excluded.raw_features,
    analyzed_at=excluded.analyzed_at;
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """`CREATE TABLE IF NOT EXISTS`로는 반영되지 않는, 기존 테이블에 대한 컬럼 추가를 처리한다."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
    if "mb_recording_id" not in columns:
        conn.execute("ALTER TABLE tracks ADD COLUMN mb_recording_id TEXT")


_UPSERT_TAG_SQL = """
INSERT INTO track_tags (track_id, source, tag_type, raw_tag, weight, canonical_style, fetched_at)
VALUES (:track_id, :source, :tag_type, :raw_tag, :weight, :canonical_style, :fetched_at)
ON CONFLICT(track_id, source, tag_type, raw_tag) DO UPDATE SET
    weight=excluded.weight,
    canonical_style=excluded.canonical_style,
    fetched_at=excluded.fetched_at;
"""


def upsert_track_tags(conn: sqlite3.Connection, track_id: int, tags: list[dict[str, Any]]) -> None:
    """트랙 하나에 대한 태그 목록을 저장한다(있으면 갱신).

    tags의 각 항목은 source, tag_type, raw_tag, weight(선택), canonical_style(선택) 키를 가진다.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "track_id": track_id,
            "source": tag["source"],
            "tag_type": tag["tag_type"],
            "raw_tag": tag["raw_tag"],
            "weight": tag.get("weight"),
            "canonical_style": tag.get("canonical_style"),
            "fetched_at": fetched_at,
        }
        for tag in tags
    ]
    conn.executemany(_UPSERT_TAG_SQL, rows)
    conn.commit()


def upsert_track(conn: sqlite3.Connection, track: dict[str, Any]) -> None:
    """`analyze_track()` 결과를 file_path 기준으로 저장(있으면 갱신)한다."""
    row = {
        "file_path": track["file_path"],
        "artist": track.get("artist"),
        "title": track.get("title"),
        "album": track.get("album"),
        "bpm": track.get("bpm"),
        "key": track.get("key"),
        "key_scale": track.get("key_scale"),
        "energy": track.get("energy"),
        "duration_sec": track.get("duration_sec"),
        "raw_features": json.dumps(track.get("raw_features", {}), ensure_ascii=False),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(_UPSERT_SQL, row)
    conn.commit()


_UPSERT_LISTENING_HISTORY_SQL = """
INSERT INTO listening_history (spotify_track_id, artist, title, played_at, track_id, fetched_at)
VALUES (:spotify_track_id, :artist, :title, :played_at, :track_id, :fetched_at)
ON CONFLICT(spotify_track_id, played_at) DO UPDATE SET
    track_id=excluded.track_id,
    fetched_at=excluded.fetched_at;
"""


def upsert_listening_history(conn: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    """최근 재생 이력을 저장한다(있으면 갱신).

    각 항목은 spotify_track_id, artist, title, played_at을 필수로 갖고,
    track_id(로컬 tracks 매칭 결과, 없으면 None)는 선택.
    같은 곡을 반복 재생해도 played_at이 다르면 별도 이력으로 쌓인다.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "spotify_track_id": item["spotify_track_id"],
            "artist": item.get("artist"),
            "title": item.get("title"),
            "played_at": item["played_at"],
            "track_id": item.get("track_id"),
            "fetched_at": fetched_at,
        }
        for item in items
    ]
    if not rows:
        return
    conn.executemany(_UPSERT_LISTENING_HISTORY_SQL, rows)
    conn.commit()


def replace_top_tracks(conn: sqlite3.Connection, time_range: str, items: list[dict[str, Any]]) -> None:
    """`time_range`(short/medium/long_term) 상위 청취곡을 이번 조회 결과로 교체한다.

    랭킹은 매 조회마다 통째로 바뀌는 스냅샷이라, 시계열 이력 대신 최신 상태만
    유지하는 것이 "지금 뭘 많이 듣는가"를 정직하게 반영한다.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "spotify_track_id": item["spotify_track_id"],
            "artist": item.get("artist"),
            "title": item.get("title"),
            "time_range": time_range,
            "rank": item["rank"],
            "track_id": item.get("track_id"),
            "fetched_at": fetched_at,
        }
        for item in items
    ]
    conn.execute("DELETE FROM top_tracks WHERE time_range = ?", (time_range,))
    if rows:
        conn.executemany(
            """
            INSERT INTO top_tracks (spotify_track_id, artist, title, time_range, rank, track_id, fetched_at)
            VALUES (:spotify_track_id, :artist, :title, :time_range, :rank, :track_id, :fetched_at)
            """,
            rows,
        )
    conn.commit()


def update_track_mbid(conn: sqlite3.Connection, track_id: int, mb_recording_id: str) -> None:
    """트랙의 MusicBrainz 레코딩 mbid를 저장한다(관계 조회 시 재사용)."""
    conn.execute("UPDATE tracks SET mb_recording_id = ? WHERE id = ?", (mb_recording_id, track_id))
    conn.commit()


_UPSERT_RELATION_SQL = """
INSERT INTO relations (
    source, relation_type, from_entity_type, from_entity_id, from_entity_name,
    to_entity_type, to_entity_id, to_entity_name, to_entity_key, attributes, fetched_at
)
VALUES (
    :source, :relation_type, :from_entity_type, :from_entity_id, :from_entity_name,
    :to_entity_type, :to_entity_id, :to_entity_name, :to_entity_key, :attributes, :fetched_at
)
ON CONFLICT(source, relation_type, from_entity_type, from_entity_id, to_entity_type, to_entity_key) DO UPDATE SET
    from_entity_name=excluded.from_entity_name,
    to_entity_name=excluded.to_entity_name,
    attributes=excluded.attributes,
    fetched_at=excluded.fetched_at;
"""


def upsert_relations(conn: sqlite3.Connection, relations: list[dict[str, Any]]) -> None:
    """관계 그래프 엣지 목록을 저장한다(있으면 갱신).

    각 항목은 source, relation_type, from_entity_type, from_entity_id, to_entity_type,
    to_entity_name을 필수로 갖고, from_entity_name/to_entity_id/attributes는 선택.
    to_entity_id가 없는 경우(예: MusicBrainz에 엔티티가 없는 대상) to_entity_name을 대신
    dedup 키(to_entity_key)로 사용해, 이름만 아는 대상도 정직하게 공백 없이 저장한다.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "source": r["source"],
            "relation_type": r["relation_type"],
            "from_entity_type": r["from_entity_type"],
            "from_entity_id": r["from_entity_id"],
            "from_entity_name": r.get("from_entity_name"),
            "to_entity_type": r["to_entity_type"],
            "to_entity_id": r.get("to_entity_id"),
            "to_entity_name": r["to_entity_name"],
            "to_entity_key": r.get("to_entity_id") or r["to_entity_name"],
            "attributes": json.dumps(r.get("attributes") or [], ensure_ascii=False),
            "fetched_at": fetched_at,
        }
        for r in relations
    ]
    if not rows:
        return
    conn.executemany(_UPSERT_RELATION_SQL, rows)
    conn.commit()
