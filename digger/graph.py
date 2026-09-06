"""관계 기반(사람 축) 디깅: 로컬 relations 테이블 + MusicBrainz 실시간 조회로
시드 곡의 협업자/레이블/샘플/영향 관계를 따라가 아직 모르는 곡·아티스트를 찾는다.

로컬 DB의 relations는 "시드 곡이 누구와 연결돼 있는가"까지만 담고 있어서,
그 자체로는 새로운 곡을 알려주지 않는다(이미 아는 시드 곡의 정보일 뿐).
그래서 collab/label 카테고리는 연결된 아티스트/레이블을 다시 MusicBrainz로
조회해 "그 사람이 참여한 다른 곡", "같은 레이블의 다른 아티스트"까지 한 단계 더
들어간다. samples/influence는 관계 자체가 이미 발견 대상(원곡/영향받은 아티스트)을
가리키므로 추가 조회 없이 바로 결과로 쓴다.
"""

from __future__ import annotations

import sqlite3
import sys
from typing import Any

from .metadata import musicbrainz
from .relations import CATEGORIES, COLLAB_KEYWORDS, matches_category


def _fetch_seed_relations(
    conn: sqlite3.Connection, track_id: int, artist: str | None, mb_recording_id: str | None
) -> list[tuple]:
    """시드 트랙과 관련된 relations 엣지를 전부 모은다.

    소스별로 from_entity가 다르게 저장돼 있음: Discogs 레이블 관계는 track id,
    MusicBrainz 협업/샘플 관계는 recording mbid, 레이블 소속/영향 관계는 아티스트명 기준.
    """
    conditions = ["(from_entity_type = 'track' AND from_entity_id = ?)"]
    params: list[Any] = [str(track_id)]
    if mb_recording_id:
        conditions.append("(from_entity_type = 'recording' AND from_entity_id = ?)")
        params.append(mb_recording_id)
    if artist:
        conditions.append("(from_entity_type = 'artist' AND from_entity_name = ?)")
        params.append(artist)

    query = (
        "SELECT relation_type, to_entity_type, to_entity_id, to_entity_name "
        f"FROM relations WHERE {' OR '.join(conditions)}"
    )
    return conn.execute(query, params).fetchall()


def _is_known_locally(conn: sqlite3.Connection, name: str) -> bool:
    """이름이 로컬 tracks의 artist/title에 이미 등장하는지(=이미 아는 곡/아티스트인지) 확인."""
    row = conn.execute(
        "SELECT 1 FROM tracks WHERE artist LIKE ? OR title LIKE ? LIMIT 1",
        (f"%{name}%", f"%{name}%"),
    ).fetchone()
    return row is not None


def _local_track_id_for_name(conn: sqlite3.Connection, name: str) -> int | None:
    """이름이 가리키는 로컬 트랙 id를 찾는다(질림 스코어 조회용). 모호하면 첫 결과를 씀."""
    row = conn.execute(
        "SELECT id FROM tracks WHERE artist LIKE ? OR title LIKE ? LIMIT 1",
        (f"%{name}%", f"%{name}%"),
    ).fetchone()
    return row[0] if row else None


def _dig_collab(
    conn: sqlite3.Connection, artist: str, title: str, to_id: str | None, to_name: str, relation_type: str
) -> list[dict]:
    """협업자(프로듀서/작곡가/엔지니어 등)가 참여한 다른 레코딩을 찾는다.

    mbid가 없으면(Discogs 크레딧) 추가 탐색은 못 하지만, "이 곡의 프로듀서가 누구인지"
    자체가 사람 축 정보라 레이블과 같은 방식으로 결과에 남긴다.
    """
    if not to_id:
        return [
            {
                "relation_type": relation_type,
                "path": f"{artist} - {title} 의 {relation_type}: {to_name} (mbid 없음 — 추가 탐색 생략)",
                "entity_type": "artist",
                "entity_name": to_name,
                "entity_mbid": None,
                "already_known": _is_known_locally(conn, to_name),
            }
        ]

    results = []
    for rel in musicbrainz.get_artist_recording_credits(to_id):
        rel_type = (rel.get("type") or "").lower()
        if not any(k in rel_type for k in COLLAB_KEYWORDS):
            continue
        recording = rel.get("recording") or {}
        rec_title = recording.get("title")
        if not rec_title or rec_title.lower() == title.lower():
            continue
        results.append(
            {
                "relation_type": rel.get("type"),
                "path": f"{artist} - {title} 의 {rel.get('type')} {to_name} → {rec_title}",
                "entity_type": "recording",
                "entity_name": rec_title,
                "entity_mbid": recording.get("id"),
                "already_known": _is_known_locally(conn, rec_title),
            }
        )
    return results


def _dig_label(conn: sqlite3.Connection, artist: str, to_id: str | None, to_name: str) -> list[dict]:
    """같은 레이블에서 발매한 다른 아티스트를 찾는다. mbid가 없으면(Discogs 이름뿐인 레이블)
    추가 조회 없이 레이블 정보만 정직하게 보여준다."""
    if not to_id:
        return [
            {
                "relation_type": "label",
                "path": f"{artist} 의 소속 레이블 {to_name} (mbid 없음 — 추가 탐색 생략)",
                "entity_type": "label",
                "entity_name": to_name,
                "entity_mbid": None,
                "already_known": False,
            }
        ]

    results = []
    seen = {artist.lower()}
    for release in musicbrainz.browse_releases_by_label(to_id):
        for credit in release.get("artist-credit") or []:
            other = credit.get("artist") or {}
            name = other.get("name")
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            results.append(
                {
                    "relation_type": "label",
                    "path": f"{artist} 와 같은 레이블({to_name}) 소속: {name}",
                    "entity_type": "artist",
                    "entity_name": name,
                    "entity_mbid": other.get("id"),
                    "already_known": _is_known_locally(conn, name),
                }
            )
    return results


def dig_relations(
    conn: sqlite3.Connection,
    track_id: int,
    artist: str,
    title: str,
    mb_recording_id: str | None,
    category: str,
    top_n: int = 10,
    include_known: bool = False,
    boredom_scores: dict[int, float] | None = None,
    exclude_tired_above: float | None = None,
) -> list[dict]:
    """시드 곡에서 `category`(collab/label/samples/influence) 축으로 관계를 따라가 결과를 반환한다.

    boredom_scores가 주어지면 각 결과의 entity_name을 로컬 트랙과 매칭해 질림 스코어를
    붙이고, exclude_tired_above를 넘는 결과는 제외한다 — "이미 아는 곡"이어도 질리지
    않았으면 include_known으로 남겨둘 수 있게, 두 필터를 독립적으로 적용한다.
    """
    if category not in CATEGORIES:
        raise ValueError(f"category는 {CATEGORIES} 중 하나여야 함: {category!r}")

    edges = _fetch_seed_relations(conn, track_id, artist, mb_recording_id)
    matches = [e for e in edges if matches_category(e[0], e[1], category)]

    results: list[dict] = []
    for relation_type, to_entity_type, to_id, to_name in matches:
        if category == "collab":
            try:
                results += _dig_collab(conn, artist, title, to_id, to_name, relation_type)
            except Exception as e:
                print(f"    {to_name} 관련 조회 실패, 건너뜀: {e}", file=sys.stderr)
        elif category == "label":
            try:
                results += _dig_label(conn, artist, to_id, to_name)
            except Exception as e:
                print(f"    {to_name} 관련 조회 실패, 건너뜀: {e}", file=sys.stderr)
        elif category == "samples":
            results.append(
                {
                    "relation_type": relation_type,
                    "path": f"{artist} - {title} 이(가) 샘플링한 원곡",
                    "entity_type": to_entity_type,
                    "entity_name": to_name,
                    "entity_mbid": to_id,
                    "already_known": _is_known_locally(conn, to_name),
                }
            )
        elif category == "influence":
            results.append(
                {
                    "relation_type": relation_type,
                    "path": f"{artist} 이(가) 영향받은 아티스트",
                    "entity_type": to_entity_type,
                    "entity_name": to_name,
                    "entity_mbid": to_id,
                    "already_known": _is_known_locally(conn, to_name),
                }
            )

    for r in results:
        track_id = _local_track_id_for_name(conn, r["entity_name"]) if boredom_scores else None
        r["boredom_score"] = boredom_scores.get(track_id, 0.0) if track_id is not None and boredom_scores else 0.0

    if not include_known:
        results = [r for r in results if not r["already_known"]]
    if exclude_tired_above is not None:
        results = [r for r in results if r["boredom_score"] <= exclude_tired_above]
    return results[:top_n]
