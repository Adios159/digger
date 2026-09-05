"""Spotify Web API 클라이언트 (OAuth Authorization Code Flow).

recently-played/top-tracks는 사용자 범위(scope) 데이터라 client credentials로는
접근 불가 — 브라우저를 열어 사용자 동의를 받는 Authorization Code Flow가 필수.
최초 인증 이후에는 refresh_token으로 브라우저 없이 access_token을 갱신한다.
"""

from __future__ import annotations

import base64
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import requests

from .. import config

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE_URL = "https://api.spotify.com/v1"
SCOPES = "user-read-recently-played user-top-read"
TOKEN_CACHE_PATH = Path(".spotify_token.json")

# Spotify는 Discogs/MusicBrainz와 달리 고정 요청 간격이 아니라 429 + Retry-After
# 헤더로 레이트리밋을 알려주는 방식이라, 고정 간격 대신 그때그때 헤더를 따른다.
_MAX_RETRIES = 3


class _CallbackHandler(BaseHTTPRequestHandler):
    """리다이렉트로 들어오는 `?code=...`를 잡아 서버 인스턴스에 저장한다."""

    def do_GET(self) -> None:  # noqa: N802 (http.server가 요구하는 이름)
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        self.server.auth_code = params.get("code", [None])[0]  # type: ignore[attr-defined]
        self.server.auth_error = params.get("error", [None])[0]  # type: ignore[attr-defined]

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        message = "인증 완료. 이 창은 닫아도 됨." if self.server.auth_code else "인증 실패. 터미널을 확인할 것."  # type: ignore[attr-defined]
        self.wfile.write(message.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # 콜백 서버 접근 로그는 불필요


def _load_token_cache() -> dict[str, Any] | None:
    if not TOKEN_CACHE_PATH.exists():
        return None
    import json

    return json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))


def _save_token_cache(token_data: dict[str, Any]) -> None:
    import json

    TOKEN_CACHE_PATH.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _basic_auth_header() -> str:
    raw = f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _exchange_code_for_token(code: str) -> dict[str, Any]:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.SPOTIFY_REDIRECT_URI,
        },
        headers={"Authorization": _basic_auth_header()},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _refresh_access_token(refresh_token: str) -> dict[str, Any]:
    response = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers={"Authorization": _basic_auth_header()},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    # Spotify가 새 refresh_token을 안 주는 경우 기존 값을 유지해야 함
    data.setdefault("refresh_token", refresh_token)
    return data


def _authorize_interactively() -> dict[str, Any]:
    """브라우저로 사용자 동의를 받고 authorization code를 교환해 토큰을 발급받는다."""
    redirect = urllib.parse.urlparse(config.SPOTIFY_REDIRECT_URI)
    port = redirect.port or 8888

    auth_url = f"{AUTH_URL}?" + urllib.parse.urlencode(
        {
            "client_id": config.SPOTIFY_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": config.SPOTIFY_REDIRECT_URI,
            "scope": SCOPES,
        }
    )

    server = HTTPServer((redirect.hostname or "127.0.0.1", port), _CallbackHandler)
    server.auth_code = None  # type: ignore[attr-defined]
    server.auth_error = None  # type: ignore[attr-defined]

    print("브라우저에서 Spotify 인증을 진행할 것. 자동으로 안 열리면 아래 URL을 직접 열 것:")
    print(auth_url)
    import webbrowser

    webbrowser.open(auth_url)

    server.handle_request()  # 콜백 1건만 받고 종료
    server.server_close()

    if server.auth_error or not server.auth_code:  # type: ignore[attr-defined]
        raise RuntimeError(f"Spotify 인증 실패: {server.auth_error or '알 수 없는 오류'}")  # type: ignore[attr-defined]

    return _exchange_code_for_token(server.auth_code)  # type: ignore[attr-defined]


def get_access_token() -> str:
    """캐시된 토큰을 재사용하거나, 만료 시 refresh하거나, 없으면 새로 인증한다."""
    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        raise RuntimeError("SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET이 .env에 설정되지 않음")

    cache = _load_token_cache()

    if cache and cache.get("expires_at", 0) > time.time():
        return cache["access_token"]

    if cache and cache.get("refresh_token"):
        token_data = _refresh_access_token(cache["refresh_token"])
    else:
        token_data = _authorize_interactively()

    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600) - 60
    _save_token_cache(token_data)
    return token_data["access_token"]


def _request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(_MAX_RETRIES):
        response = requests.get(
            f"{API_BASE_URL}/{path}",
            params=params,
            headers={"Authorization": f"Bearer {get_access_token()}"},
            timeout=10,
        )
        if response.status_code == 429 and attempt < _MAX_RETRIES - 1:
            time.sleep(int(response.headers.get("Retry-After", "1")))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("Spotify API 요청이 재시도 후에도 실패함(429)")


def get_recently_played(limit: int = 50, max_items: int = 200) -> list[dict[str, Any]]:
    """최근 재생 목록을 최신순으로 조회한다(`before` 커서로 페이지네이션).

    Spotify는 최근 재생을 최대 최근 50건 * 페이지네이션으로 제공하지만
    실제로는 최근 며칠 치 정도만 남아있는 경우가 많음(엔드포인트 자체의 한계).
    """
    items: list[dict[str, Any]] = []
    before: int | None = None
    while len(items) < max_items:
        params: dict[str, Any] = {"limit": min(limit, 50)}
        if before is not None:
            params["before"] = before
        data = _request("me/player/recently-played", params)
        page_items = data.get("items", [])
        if not page_items:
            break
        items.extend(page_items)
        cursors = data.get("cursors") or {}
        next_before = cursors.get("before")
        if not next_before:
            break
        before = int(next_before)
    return items[:max_items]


def get_top_tracks(time_range: str = "medium_term", limit: int = 50, max_items: int = 100) -> list[dict[str, Any]]:
    """상위 청취곡을 조회한다. time_range: short_term(4주)/medium_term(6개월)/long_term(전체)."""
    items: list[dict[str, Any]] = []
    offset = 0
    while len(items) < max_items:
        data = _request(
            "me/top/tracks",
            {"time_range": time_range, "limit": min(limit, 50), "offset": offset},
        )
        page_items = data.get("items", [])
        if not page_items:
            break
        items.extend(page_items)
        offset += len(page_items)
        if not data.get("next"):
            break
    return items[:max_items]
