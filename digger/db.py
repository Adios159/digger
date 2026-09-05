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
    conn.execute(SCHEMA)
    conn.commit()
    return conn


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
