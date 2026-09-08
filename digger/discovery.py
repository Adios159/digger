"""로컬 DB 밖에서 아직 안 들어본 후보를 찾아, 기존 태그 벡터 유사도로 순위를 매긴다.

similarity.py의 find_similar/find_digging_zone은 로컬 tracks 테이블 안에서만 후보를
고른다 — 그 테이블엔 로컬 음원 분석분과 Spotify 좋아요 임포트분만 있어서, 결국 이미
아는 곡끼리만 서로 추천하게 된다. 여기서는 후보 "발굴"만 Last.fm(track.getSimilar)에
맡기고, "진짜 취향에 맞는지" 판단은 이미 검증된 것과 같은 알고리즘 — canonical style
태그 벡터 코사인 유사도(vectorize.py) — 을 그대로 재사용한다.
"""

from __future__ import annotations

import sqlite3
import sys
from typing import NamedTuple

import numpy as np

from . import crosswalk
from .metadata import lastfm
from .vectorize import agreement_weights, build_feature_blocks

# Last.fm이 준 후보 중 태그까지 조회할 상위 개수. 동기 API에서 후보마다 태그 조회가
# 추가로 발생하므로(과호출 방지) 실제로 화면에 노출할 top_n보다 여유 있게만 잡는다.
CANDIDATE_LIMIT = 10


class UnheardTrack(NamedTuple):
    artist: str
    title: str
    similarity: float


def _unit(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def _already_known(conn: sqlite3.Connection, artist: str, title: str) -> bool:
    """로컬 tracks에 같은 아티스트+제목이 이미 있는지 확인한다(대소문자 무시 정확 일치).

    graph.py의 _is_known_locally는 이름 하나가 아티스트/제목 어디든 부분 매칭되면
    맞다고 보는 느슨한 검사라 "이미 아는 사람/곡" 힌트용으로는 맞지만, 여기서는
    "이 정확한 곡을 이미 들었는가"를 걸러야 해서 아티스트와 제목 둘 다 일치하는지 본다.
    """
    row = conn.execute(
        "SELECT 1 FROM tracks WHERE artist = ? COLLATE NOCASE AND title = ? COLLATE NOCASE LIMIT 1",
        (artist, title),
    ).fetchone()
    return row is not None


def _candidate_vector(resolver, tag_names: list[str], raw_tags: list[dict]) -> np.ndarray:
    """Last.fm 태그 목록을 시드와 같은 vocabulary 공간의 벡터로 투영한다.

    vocabulary(로컬 라이브러리 전체에 등장한 style)에 없는 태그는 시드 쪽 성분이
    항상 0이라 코사인 곱에 기여할 수 없으므로 투영에서 그냥 버린다. 후보는 Discogs
    대조군이 없는 자유형 태그뿐이라, agreement_weights({}, freeform)로 기존 "단독
    자유형 태그" 처리(UNCONTESTED_WEIGHT * strength)를 그대로 적용한다.
    """
    freeform_styles: dict[str, float] = {}
    for tag in raw_tags:
        style = resolver(tag.get("name", ""))
        if style is None:
            continue
        strength = (min(float(tag.get("count") or 0), 100.0) / 100.0) ** 0.5
        freeform_styles[style] = max(freeform_styles.get(style, 0.0), strength)

    weights = agreement_weights({}, freeform_styles)
    index = {name: i for i, name in enumerate(tag_names)}
    vec = np.zeros(len(tag_names))
    for style, weight in weights.items():
        i = index.get(f"tag:{style}")
        if i is not None:
            vec[i] = weight
    return vec


def find_unheard(
    conn: sqlite3.Connection,
    seed_track_id: int,
    top_n: int = 5,
    candidate_limit: int = CANDIDATE_LIMIT,
) -> list[UnheardTrack]:
    """시드 트랙 기준 Last.fm 유사곡 후보 중 로컬에 없는 것만 태그 유사도로 순위 매겨 반환한다."""
    row = conn.execute("SELECT artist, title FROM tracks WHERE id = ?", (seed_track_id,)).fetchone()
    if row is None:
        raise ValueError(f"트랙 id {seed_track_id}가 DB에 없음")
    seed_artist, seed_title = row
    if not seed_artist or not seed_title:
        return []

    blocks = build_feature_blocks(conn)
    seed_vec = blocks.tag_vectors.get(seed_track_id)
    if seed_vec is None or np.linalg.norm(seed_vec) == 0:
        return []

    try:
        candidates = lastfm.get_similar_tracks(seed_artist, seed_title, limit=candidate_limit)
    except Exception as e:
        print(f"    Last.fm 유사곡 조회 실패, 미청취 후보 생략: {e}", file=sys.stderr)
        return []

    resolver = crosswalk.build_resolver(conn)
    seed_unit = _unit(seed_vec)

    results = []
    for candidate in candidates:
        artist = (candidate.get("artist") or {}).get("name")
        title = candidate.get("name")
        if not artist or not title or _already_known(conn, artist, title):
            continue

        try:
            raw_tags = lastfm.get_top_tags(artist, title)
        except Exception as e:
            print(f"    {artist} - {title} 태그 조회 실패, 건너뜀: {e}", file=sys.stderr)
            continue

        candidate_vec = _candidate_vector(resolver, blocks.tag_names, raw_tags)
        if np.linalg.norm(candidate_vec) == 0:
            continue

        similarity = float(np.dot(seed_unit, _unit(candidate_vec)))
        results.append(UnheardTrack(artist, title, similarity))

    results.sort(key=lambda t: t.similarity, reverse=True)
    return results[:top_n]
