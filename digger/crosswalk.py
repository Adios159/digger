"""자유형 태그 -> Discogs canonical style 크로스워크 조회."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import yaml

_CROSSWALK_PATH = Path(__file__).parent / "data" / "tag_crosswalk.yaml"


def _key(raw_tag: str) -> str:
    """비교용 키: 소문자 + 영숫자만 남긴다("Hip-Hop", "hip hop" -> "hiphop")."""
    return re.sub(r"[^a-z0-9]", "", raw_tag.lower())


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    with open(_CROSSWALK_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {_key(tag): style for tag, style in raw.items()}


def normalize(raw_tag: str) -> str | None:
    """자유형 태그를 Discogs canonical style로 정규화한다. 매핑이 없으면 None."""
    return _table().get(_key(raw_tag))


def build_resolver(conn: sqlite3.Connection) -> Callable[[str], str | None]:
    """YAML 크로스워크 + DB에 실제 등장한 Discogs 어휘를 합친 리졸버를 만든다.

    Discogs genre/style은 그 자체가 canonical이라, 이미 DB에 쌓인 Discogs 어휘를
    사전으로 재사용하면 "Hip-Hop"/"hip hop" 같은 표기 차이를 YAML에 일일이 적지
    않아도 흡수된다. 곡이 늘어 Discogs 어휘가 넓어지면 커버 범위도 같이 자라고,
    손으로 적어야 하는 건 "rap" -> "Hip Hop" 같은 동의어뿐이다.

    YAML을 먼저 보는 이유: 수동 큐레이션이 자동 어휘 매칭을 이길 수 있어야 함.
    """
    vocabulary = {
        _key(row[0]): row[0]
        for row in conn.execute("SELECT DISTINCT raw_tag FROM track_tags WHERE source = 'discogs'")
    }

    def resolve(raw_tag: str) -> str | None:
        key = _key(raw_tag)
        return _table().get(key) or vocabulary.get(key)

    return resolve
