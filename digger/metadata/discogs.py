"""Discogs 메타데이터 클라이언트 (personal access token 필요).

검색 결과 자체에 공식 genre/style 필드가 포함되어 있어,
크로스워크 없이 바로 canonical 태그로 쓸 수 있다.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

from .. import config

BASE_URL = "https://api.discogs.com"
_MIN_INTERVAL = 1.1  # 인증된 요청 분당 60회 제한 대비 여유
_last_request_time = 0.0

# 컴필레이션 후보는 트랙리스트 확인에 추가 요청이 들어가므로 검사할 후보 수를 제한한다
_MAX_CANDIDATES = 5
_VARIOUS_ARTISTS_KEYS = {"various", "variousartists"}


def _request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    response = requests.get(
        f"{BASE_URL}/{path}",
        params={**params, "token": config.DISCOGS_TOKEN},
        headers={"User-Agent": "digger/0.1"},
        timeout=10,
    )
    _last_request_time = time.monotonic()
    response.raise_for_status()
    return response.json()


def _match_key(name: str) -> str:
    """비교용 키: Discogs 표기 장식을 걷어내고 영숫자만 남긴다.

    Discogs는 동명이인을 "No Brain (2)"처럼 번호로 구분하고, 표기가 다른 크레딧에는
    "Lil' Wayne*"처럼 별표를 붙인다. 둘 다 같은 아티스트로 취급해야 한다.
    """
    name = re.sub(r"\s*\(\d+\)\s*$", "", name.strip()).rstrip("*")
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _release_artist_key(release_title: str) -> str:
    """Discogs 릴리즈 제목("아티스트 - 릴리즈명")에서 아티스트 구간만 뽑는다."""
    return _match_key(release_title.split(" - ", 1)[0])


def _release_has_track(release_id: int, artist: str, title: str) -> bool:
    """컴필레이션 후보의 트랙리스트에 우리 곡이 실제로 들어 있는지 확인한다.

    릴리즈 아티스트가 "Various"면 제목만으로는 우리 곡이 실린 판인지 알 수 없어
    상세를 한 번 더 조회한다(요청이 늘어나므로 컴필레이션 후보에 대해서만).
    """
    detail = _request(f"releases/{release_id}", {})
    artist_key, title_key = _match_key(artist), _match_key(title)
    for track in detail.get("tracklist", []):
        if _match_key(track.get("title", "")) != title_key:
            continue
        track_artists = {_match_key(a.get("name", "")) for a in track.get("artists") or []}
        # 트랙별 아티스트를 안 적어둔 릴리즈도 있어 그 경우엔 제목 일치로 인정한다
        if not track_artists or artist_key in track_artists:
            return True
    return False


def search_release(artist: str, title: str) -> dict[str, Any] | None:
    """아티스트+트랙 제목으로 검색해 아티스트가 확인된 릴리즈를 반환한다.

    `artist`/`track` 필드로 엄격 검색해도 Discogs가 유사 이름으로 퍼지 매칭을 해버려서
    (한국 아티스트 "Marv" -> "Marv Herzog"의 폴카 앨범) 검색 방식만으로는 못 거른다.
    게다가 엄격 검색은 컴필레이션(릴리즈 아티스트가 "Various")을 놓친다.

    그래서 통합 텍스트 쿼리(`q`)로 느슨하게 찾은 뒤 결과를 직접 검증한다:
    릴리즈 제목의 아티스트 구간이 정확히 일치하거나, "Various"인 경우 트랙리스트에
    우리 곡이 실제로 있어야 채택한다. 확인이 안 되면 억지로 고르지 않고 공백으로 남긴다.
    """
    data = _request("database/search", {"q": f"{artist} {title}", "type": "release"})
    artist_key = _match_key(artist)

    for result in data.get("results", [])[:_MAX_CANDIDATES]:
        release_artist_key = _release_artist_key(result.get("title", ""))
        if release_artist_key == artist_key:
            return result
        if release_artist_key in _VARIOUS_ARTISTS_KEYS and _release_has_track(result["id"], artist, title):
            return result
    return None


def get_credits(release_id: int, title: str) -> list[dict[str, Any]]:
    """릴리즈 크레딧(프로듀서·작곡·믹싱 등)을 [{role, name, discogs_artist_id}]로 반환한다.

    Discogs는 크레딧을 릴리즈 전체(`extraartists`)와 트랙별(`tracklist[].extraartists`)
    두 군데에 나눠 담는다. 컴필레이션에서는 트랙별 크레딧만 우리 곡의 것이므로,
    해당 트랙의 크레딧과 릴리즈 전체 크레딧을 함께 모은다.

    MusicBrainz가 비영어권 곡 크레딧을 거의 갖고 있지 않아 "사람 축" 탐색이 비는데,
    이미 쓰고 있는 Discogs 토큰으로 메울 수 있는 만큼은 여기서 메운다.
    """
    detail = _request(f"releases/{release_id}", {})

    credits = list(detail.get("extraartists") or [])
    title_key = _match_key(title)
    for track in detail.get("tracklist") or []:
        if _match_key(track.get("title", "")) == title_key:
            credits += track.get("extraartists") or []

    seen = set()
    result = []
    for credit in credits:
        name, role = credit.get("name"), credit.get("role")
        if not name or not role:
            continue
        # Discogs는 "Producer, Mixed By"처럼 한 사람의 여러 역할을 한 필드에 몰아넣는다
        for single_role in (r.strip() for r in role.split(",")):
            if not single_role or (name, single_role) in seen:
                continue
            seen.add((name, single_role))
            result.append({"role": single_role, "name": name, "discogs_artist_id": credit.get("id")})
    return result
