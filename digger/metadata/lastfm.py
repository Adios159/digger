"""Last.fm 메타데이터 클라이언트 (API 키 필요)."""

from __future__ import annotations

from typing import Any

import requests

from .. import config

BASE_URL = "http://ws.audioscrobbler.com/2.0/"


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
        raise RuntimeError(f"Last.fm API error {data['error']}: {data.get('message')}")

    response.raise_for_status()
    return data


def get_top_tags(artist: str, title: str) -> list[dict[str, Any]]:
    """트랙 단위 태그(name, count 0~100)를 조회한다. 없으면 아티스트 단위로 폴백."""
    data = _request("track.getTopTags", artist=artist, track=title)
    tags = data.get("toptags", {}).get("tag", [])
    if tags:
        return tags

    data = _request("artist.getTopTags", artist=artist)
    return data.get("toptags", {}).get("tag", [])
