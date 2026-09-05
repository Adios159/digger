"""자유형 태그 -> Discogs canonical style 크로스워크 조회."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_CROSSWALK_PATH = Path(__file__).parent / "data" / "tag_crosswalk.yaml"


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    with open(_CROSSWALK_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def normalize(raw_tag: str) -> str | None:
    """자유형 태그를 Discogs canonical style로 정규화한다. 매핑이 없으면 None."""
    return _table().get(raw_tag.strip().lower())
