"""분석 결과를 저장하는 SQLite 특성 벡터 DB."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
-- file_path가 nullable인 이유: Spotify Liked Songs처럼 로컬 음원이 없는 트랙도
-- 같은 tracks 테이블에 담기 때문. 이 경우 spotify_track_id가 식별자 역할을 하고
-- bpm/key/energy는 NULL로 남는다(Essentia 분석 대상이 아니므로). 유사도 계산은
-- 태그 벡터만 쓰기 때문에(vectorize.py) 음향 특성이 없어도 탐색에 그대로 참여한다.
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE,
    spotify_track_id TEXT UNIQUE,
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

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    action TEXT NOT NULL,
    context TEXT,
    seed_track_id INTEGER REFERENCES tracks(id),
    created_at TEXT NOT NULL
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
    # check_same_thread=False: FastAPI(api.py)가 동기 의존성을 스레드풀에서 실행할 때
    # 커넥션을 연 스레드와 닫는 스레드가 달라질 수 있어서 필요함(CLI는 단일 스레드라 무해).
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """`CREATE TABLE IF NOT EXISTS`로는 반영되지 않는, 기존 테이블에 대한 변경을 처리한다."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
    if "mb_recording_id" not in columns:
        conn.execute("ALTER TABLE tracks ADD COLUMN mb_recording_id TEXT")
        columns.add("mb_recording_id")

    if "enriched_at" not in columns:
        conn.execute("ALTER TABLE tracks ADD COLUMN enriched_at TEXT")
        columns.add("enriched_at")

    if "spotify_track_id" not in columns:
        _rebuild_tracks_for_non_local_sources(conn)


def _rebuild_tracks_for_non_local_sources(conn: sqlite3.Connection) -> None:
    """기존 tracks의 `file_path NOT NULL` 제약을 풀고 spotify_track_id를 추가한다.

    SQLite는 컬럼 제약 변경을 ALTER TABLE로 못 해서 새 테이블로 옮겨 담는 방식을 쓴다.
    id 값을 그대로 복사하는 게 핵심 — track_tags/listening_history/top_tracks/feedback이
    tracks(id)를 참조하고 있어서 id가 바뀌면 기존 태그·피드백이 통째로 끊긴다.
    """
    conn.executescript(
        """
        CREATE TABLE tracks_migrated (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            spotify_track_id TEXT UNIQUE,
            artist TEXT,
            title TEXT,
            album TEXT,
            bpm REAL,
            key TEXT,
            key_scale TEXT,
            energy REAL,
            duration_sec REAL,
            raw_features TEXT,
            analyzed_at TEXT NOT NULL,
            mb_recording_id TEXT,
            enriched_at TEXT
        );

        INSERT INTO tracks_migrated (
            id, file_path, artist, title, album, bpm, key, key_scale, energy,
            duration_sec, raw_features, analyzed_at, mb_recording_id, enriched_at
        )
        SELECT id, file_path, artist, title, album, bpm, key, key_scale, energy,
               duration_sec, raw_features, analyzed_at, mb_recording_id, enriched_at
        FROM tracks;

        DROP TABLE tracks;
        ALTER TABLE tracks_migrated RENAME TO tracks;
        """
    )


_UPSERT_TAG_SQL = """
INSERT INTO track_tags (track_id, source, tag_type, raw_tag, weight, canonical_style, fetched_at)
VALUES (:track_id, :source, :tag_type, :raw_tag, :weight, :canonical_style, :fetched_at)
ON CONFLICT(track_id, source, tag_type, raw_tag) DO UPDATE SET
    weight=excluded.weight,
    canonical_style=excluded.canonical_style,
    fetched_at=excluded.fetched_at;
"""


def replace_track_tags(
    conn: sqlite3.Connection, track_id: int, fetched_sources: list[str], tags: list[dict[str, Any]]
) -> None:
    """조회에 성공한 소스의 태그를 이번 결과로 통째로 교체한다.

    upsert만 하면 지난 실행에서 잘못 붙은 태그가 영원히 남는다 — 아티스트 오매칭으로
    한국 랩 곡에 들어온 "Polka" 같은 것들은 재수집해도 안 지워졌다.

    그렇다고 무조건 지우면 MusicBrainz 503처럼 일시적으로 실패한 소스의 멀쩡한 기존
    태그까지 날아가므로, `fetched_sources`(이번에 조회가 성공한 소스)에 한해서만 지운다.
    결과가 0건인 것과 조회가 실패한 것은 다른 상태라는 뜻이기도 하다.

    tags의 각 항목은 source, tag_type, raw_tag, weight(선택), canonical_style(선택) 키를 가진다.
    """
    if fetched_sources:
        conn.executemany(
            "DELETE FROM track_tags WHERE track_id = ? AND source = ?",
            [(track_id, source) for source in fetched_sources],
        )

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


_UPSERT_SPOTIFY_TRACK_SQL = """
INSERT INTO tracks (spotify_track_id, artist, title, album, duration_sec, analyzed_at)
VALUES (:spotify_track_id, :artist, :title, :album, :duration_sec, :analyzed_at)
ON CONFLICT(spotify_track_id) DO UPDATE SET
    artist=excluded.artist,
    title=excluded.title,
    album=excluded.album,
    duration_sec=excluded.duration_sec,
    analyzed_at=excluded.analyzed_at;
"""


def upsert_spotify_tracks(conn: sqlite3.Connection, tracks: list[dict[str, Any]]) -> None:
    """로컬 음원 없이 Spotify 메타데이터만 있는 트랙을 spotify_track_id 기준으로 저장한다.

    bpm/key/energy는 Essentia 분석 대상이 아니라 NULL로 남고, analyzed_at은 이 행을
    마지막으로 가져온 시각으로 쓴다. 이미 같은 곡을 로컬 파일로 분석해 둔 경우에도
    (file_path 기준 행과) 별도 행이 되는데, 그건 어느 쪽이 같은 곡인지 추측하지 않고
    정직하게 따로 두는 쪽을 택한 것 — 매칭은 아티스트/제목 기준 별도 작업으로 다룬다.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "spotify_track_id": track["spotify_track_id"],
            "artist": track.get("artist"),
            "title": track.get("title"),
            "album": track.get("album"),
            "duration_sec": track.get("duration_sec"),
            "analyzed_at": fetched_at,
        }
        for track in tracks
    ]
    if not rows:
        return
    conn.executemany(_UPSERT_SPOTIFY_TRACK_SQL, rows)
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


def mark_track_enriched(conn: sqlite3.Connection, track_id: int) -> None:
    """enrich에서 태그 조회에 성공한 트랙을 표시한다.

    enrich_tracks()가 이 값이 NULL인 트랙만 골라 재처리하므로, 다음 실행이
    외부 API rate limit에 걸려 이미 끝난 트랙까지 다시 도는 병목을 피할 수 있다.
    """
    conn.execute(
        "UPDATE tracks SET enriched_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), track_id),
    )
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


def insert_feedback(
    conn: sqlite3.Connection,
    track_id: int,
    action: str,
    context: str | None = None,
    seed_track_id: int | None = None,
) -> None:
    """트랙에 대한 좋아요/스킵 피드백을 한 건 기록한다.

    같은 트랙에 대한 반복 피드백도 listening_history처럼 각각 별도 이벤트로 쌓는다 —
    "예전엔 스킵했는데 최근엔 좋아함" 같은 시계열 신호를 나중에 협업 필터링에 쓰기 위함.
    """
    conn.execute(
        """
        INSERT INTO feedback (track_id, action, context, seed_track_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (track_id, action, context, seed_track_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
