"""관계 타입 문자열을 프로듀서/레이블/샘플/영향 4가지 축으로 분류하는 공용 규칙.

MusicBrainz 관계 타입은 커뮤니티가 자유롭게 붙이는 문자열이라 정확한 목록을 미리 다
알 수 없음. 키워드로 느슨하게 매칭해 수집(cli.collect_relations)과 탐색(graph.dig_relations)
양쪽에서 동일한 기준을 쓴다.
"""

from __future__ import annotations

# "writ"은 Discogs의 "Written-By"(작곡·작사)와 MusicBrainz의 "writer"를 함께 잡는다 —
# 비영어권 곡에서 가장 아쉬운 크레딧이라 빠뜨리면 사람 축이 그만큼 빈다.
COLLAB_KEYWORDS = (
    "produc", "compos", "engineer", "mix", "master", "arrang", "program", "remix", "lyric", "writ",
)
SAMPLE_KEYWORDS = ("sampl",)
INFLUENCE_KEYWORDS = ("influenc",)

CATEGORIES = ("collab", "label", "samples", "influence")


def matches_category(relation_type: str, to_entity_type: str, category: str) -> bool:
    """relations 테이블의 한 엣지가 주어진 카테고리에 속하는지 판단한다.

    label은 관계 타입 이름이 제각각(예: "recording contract", "personal publisher")이라
    타입 키워드 대신 to_entity_type만으로 판단한다.
    """
    rel = (relation_type or "").lower()
    if category == "collab":
        return to_entity_type == "artist" and any(k in rel for k in COLLAB_KEYWORDS)
    if category == "samples":
        return to_entity_type == "recording" and any(k in rel for k in SAMPLE_KEYWORDS)
    if category == "influence":
        return to_entity_type == "artist" and any(k in rel for k in INFLUENCE_KEYWORDS)
    if category == "label":
        return to_entity_type == "label"
    raise ValueError(f"알 수 없는 관계 카테고리: {category}")
