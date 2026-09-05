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


def _request(path: str, params: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    response = requests.get(
        f"{BASE_URL}/{path}",
        params={**params, "fmt": "json"},
        headers={"User-Agent": _user_agent()},
        timeout=timeout,
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


def get_artist_recording_credits(artist_mbid: str) -> list[dict[str, Any]]:
    """아티스트가 프로듀서/작곡가/엔지니어 등으로 참여한 다른 레코딩 목록(관계)을 조회한다.

    시드 곡의 협업자가 "다른 어떤 곡에 참여했는지"를 찾는 관계 기반 디깅의 핵심 조회.
    다작 프로듀서는 관계 수가 수백~수천 개라 응답이 커서 기본 타임아웃보다 넉넉하게 잡음.
    """
    data = _request(f"artist/{artist_mbid}", {"inc": "recording-rels"}, timeout=30)
    return data.get("relations", [])


def browse_releases_by_label(label_mbid: str, limit: int = 15) -> list[dict[str, Any]]:
    """레이블이 발매한 릴리즈 목록(아티스트 크레딧 포함)을 조회한다 (레이블 동료 탐색용).

    Warp/Def Jam급 대형 레이블은 릴리즈 수가 수천 개라 응답이 느려서 넉넉한 타임아웃 사용.
    """
    data = _request("release", {"label": label_mbid, "inc": "artist-credits", "limit": limit}, timeout=25)
    return data.get("releases", [])
