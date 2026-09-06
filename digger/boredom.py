"""청취 이력 기반 "질림 스코어" 계산.

재생 횟수와 최근성을 함께 반영해, 최근에 많이 들을수록 스코어가 높아지고
과거에 많이 들었어도 최근엔 안 들었으면 낮아지도록 설계한다(재발견 후보와
현재 과다 청취곡을 구분하기 위함). 아직 로컬 트랙과 매칭되지 않은
청취 이력(track_id IS NULL)은 계산 대상에서 제외한다 — 잘못된 매칭으로
엉뚱한 트랙에 스코어를 붙이지 않기 위함.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_HALF_LIFE_DAYS = 30.0

# 상위 청취곡 time_range별 기여 가중치. short_term(최근 4주)일수록 "지금 질림" 신호에
# 가깝고, long_term(전체 기간)은 오래된 취향일 수 있어 낮게 반영한다.
TOP_TRACK_RANGE_WEIGHTS = {"short_term": 3.0, "medium_term": 1.5, "long_term": 0.5}


def _parse_played_at(played_at: str) -> datetime:
    dt = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_boredom_scores(
    conn: sqlite3.Connection, half_life_days: float = DEFAULT_HALF_LIFE_DAYS
) -> dict[int, float]:
    """트랙 id별 질림 스코어를 계산해 반환한다.

    - 최근 재생 이력: 재생일로부터 경과일수에 지수 감쇠(half-life)를 적용해 합산
    - 상위 청취곡: time_range별 가중치를 랭킹 역수로 나눠 합산(1위가 가장 크게 기여)
    """
    scores: dict[int, float] = defaultdict(float)
    now = datetime.now(timezone.utc)

    for track_id, played_at in conn.execute(
        "SELECT track_id, played_at FROM listening_history WHERE track_id IS NOT NULL"
    ):
        days_ago = (now - _parse_played_at(played_at)).total_seconds() / 86400
        scores[track_id] += 0.5 ** (days_ago / half_life_days)

    for track_id, time_range, rank in conn.execute(
        "SELECT track_id, time_range, rank FROM top_tracks WHERE track_id IS NOT NULL"
    ):
        weight = TOP_TRACK_RANGE_WEIGHTS.get(time_range, 0.0)
        if weight and rank:
            scores[track_id] += weight / rank

    return dict(scores)


def get_boredom_score(scores: dict[int, float], track_id: int) -> float:
    """특정 트랙의 질림 스코어. 청취 이력이 없으면 0(질리지 않음)."""
    return scores.get(track_id, 0.0)
