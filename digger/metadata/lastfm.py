"""Last.fm 메타데이터 클라이언트 (API 키 필요)."""

from __future__ import annotations

from typing import Any

import requests

from .. import config

BASE_URL = "http://ws.audioscrobbler.com/2.0/"

_NOT_FOUND_ERROR = 6


class NotFound(Exception):
    """Last.fm이 해당 트랙/아티스트를 모른다고 답한 경우(error 6).

    요청 실패와는 다른 상태다 — 재시도해도 결과가 같고, "태그가 없다"는 것 자체가
    확정된 답이다. 호출부가 실패와 구분해 다룰 수 있게 별도 예외로 던진다.
    """


def _request(method: str, **params: str) -> dict[str, Any]:
    response = requests.get(
        BASE_URL,
        params={
            "method": method,
            "api_key": config.LASTFM_API_KEY,
            "format": "json",
            **params,
        },
        timeout=10,
    )
    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        raise

    if "error" in data:
        if data["error"] == _NOT_FOUND_ERROR:
            raise NotFound(data.get("message", "not found"))
        raise RuntimeError(f"Last.fm API error {data['error']}: {data.get('message')}")

    response.raise_for_status()
    return data


def get_top_tags(artist: str, title: str) -> list[dict[str, Any]]:
    """트랙 단위 태그(name, count 0~100)를 조회한다. 없으면 아티스트 단위로 폴백.

    트랙을 모른다는 응답(error 6)에 예외를 던지면 이 폴백이 실행조차 되지 않아,
    정작 폴백이 필요한 경우에 죽어 있었다. "모른다"는 답은 실패가 아니라 결과이므로
    폴백으로 이어가고, 아티스트까지 모르면 빈 목록을 돌려준다.
    """
    try:
        data = _request("track.getTopTags", artist=artist, track=title)
        tags = data.get("toptags", {}).get("tag", [])
        if tags:
            return tags
    except NotFound:
        pass

    try:
        data = _request("artist.getTopTags", artist=artist)
    except NotFound:
        return []
    return data.get("toptags", {}).get("tag", [])
