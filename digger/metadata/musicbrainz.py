"""MusicBrainz 메타데이터 클라이언트.

인증 불필요한 공개 API지만, 정책상 요청 간 최소 1초 간격과
연락처가 포함된 User-Agent가 필요함.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from .. import config

BASE_URL = "https://musicbrainz.org/ws/2"
_MIN_INTERVAL = 1.0
_last_request_time = 0.0


def _user_agent() -> str:
    contact = config.MB_CONTACT or "no-contact-set"
    return f"digger/0.1 ({contact})"


def _request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    response = requests.get(
        f"{BASE_URL}/{path}",
        params={**params, "fmt": "json"},
        headers={"User-Agent": _user_agent()},
        timeout=10,
    )
    _last_request_time = time.monotonic()
    response.raise_for_status()
    return response.json()


def search_recording(artist: str, title: str) -> dict[str, Any] | None:
    """아티스트+제목으로 가장 점수 높은 레코딩 하나를 검색한다."""
    query = f'artist:"{artist}" AND recording:"{title}"'
    data = _request("recording", {"query": query, "limit": 1})
    recordings = data.get("recordings", [])
    return recordings[0] if recordings else None


def get_tags(recording_mbid: str) -> list[dict[str, Any]]:
    """레코딩의 folksonomy 태그(name, count)를 조회한다."""
    data = _request(f"recording/{recording_mbid}", {"inc": "tags"})
    return data.get("tags", [])


def get_recording_relations(recording_mbid: str) -> list[dict[str, Any]]:
    """레코딩의 관계(프로듀서·작곡가·엔지니어 등 아티스트 관계, 샘플 등 레코딩 관계)를 조회한다."""
    data = _request(f"recording/{recording_mbid}", {"inc": "artist-rels+recording-rels"})
    return data.get("relations", [])


def get_artist_relations(artist_mbid: str) -> list[dict[str, Any]]:
    """아티스트의 관계(레이블 소속, 다른 아티스트와의 영향 관계 등)를 조회한다."""
    data = _request(f"artist/{artist_mbid}", {"inc": "label-rels+artist-rels"})
    return data.get("relations", [])
