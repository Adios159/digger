"""Discogs 메타데이터 클라이언트 (personal access token 필요).

검색 결과 자체에 공식 genre/style 필드가 포함되어 있어,
크로스워크 없이 바로 canonical 태그로 쓸 수 있다.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from .. import config

BASE_URL = "https://api.discogs.com"
_MIN_INTERVAL = 1.1  # 인증된 요청 분당 60회 제한 대비 여유
_last_request_time = 0.0


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


def search_release(artist: str, title: str) -> dict[str, Any] | None:
    """아티스트+트랙 제목으로 검색해 최상위 결과(genre/style 포함)를 반환한다.

    `artist`/`track` 필드로 엄격 검색하면 컴필레이션 릴리즈(release 아티스트가
    "Various"로 등록된 경우)를 놓치므로, 통합 텍스트 쿼리(`q`)로 느슨하게 검색한다.
    대신 느슨한 검색이 엉뚱한 결과를 상위에 올릴 수 있으므로, 결과의 `title`에
    요청한 아티스트명이 실제로 포함된 경우에만 채택하고 아니면 공백(None)으로 남긴다.
    """
    data = _request(
        "database/search",
        {"q": f"{artist} {title}", "type": "release"},
    )
    results = data.get("results", [])
    artist_lower = artist.strip().lower()
    for result in results:
        if artist_lower in result.get("title", "").lower():
            return result
    return None
