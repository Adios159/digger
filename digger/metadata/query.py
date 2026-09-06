"""외부 메타데이터 소스에 던질 검색어를 만드는 규칙.

Spotify에서 받아온 트랙 정보는 그 자체로는 정확하지만 조회 키로는 못 쓴다.
아티스트가 여러 명이면 ", "로 이어붙인 한 덩어리이고("Travis Scott, ROSALÍA, Lil Baby"),
제목에는 "(feat. …)"나 "- REMIX" 같은 꼬리표가 붙는다. Discogs/Last.fm/MusicBrainz
어디에도 그런 이름으로 등록된 아티스트나 릴리즈는 없다.

저장된 값은 건드리지 않는다 — 그건 이 곡에 대한 사실이다. 조회용 키만 따로 만든다.
"""

from __future__ import annotations

import re

# "(feat. X)", "(with X)", "(Prod. X)" — 협연·프로듀서 표기는 릴리즈 제목에 없다
_CREDIT_PARENTHETICAL = re.compile(r"\s*[(\[](feat|ft|with|prod)\b[^)\]]*[)\]]", re.IGNORECASE)

# Spotify가 " - " 뒤에 붙이는 버전 표기(REMIX, Radio Edit, Remastered 2011 …).
# 버전 키워드가 있을 때만 떼서, 제목에 원래 하이픈이 들어간 곡은 건드리지 않는다.
_VERSION_SUFFIX = re.compile(
    r"\s+-\s+[^-]*\b(remix|edit|version|remaster(ed)?|live|mix|mono|stereo|instrumental|acoustic|demo)\b.*$",
    re.IGNORECASE,
)


def primary_artist(artist: str) -> str:
    """이어붙인 아티스트 문자열에서 주 아티스트만 뽑는다."""
    return artist.split(",")[0].strip() or artist.strip()


def base_title(title: str) -> str:
    """제목에서 협연·버전 꼬리표를 떼어 원곡 제목에 가깝게 만든다.

    리믹스 꼬리표를 떼면 원곡 릴리즈에 매칭돼 원곡 장르를 물려받는다. 리믹스와 원곡을
    같은 것으로 취급하는 셈이지만, 장르 태깅 목적에서는 아무 태그도 못 받는 것보다
    낫다고 보고 감수한다.
    """
    cleaned = _VERSION_SUFFIX.sub("", title)
    cleaned = _CREDIT_PARENTHETICAL.sub("", cleaned)
    return cleaned.strip() or title.strip()


def lookup_terms(artist: str, title: str) -> tuple[str, str]:
    """외부 소스 조회에 쓸 (아티스트, 제목) 쌍을 만든다."""
    return primary_artist(artist), base_title(title)
