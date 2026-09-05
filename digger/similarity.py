"""태그(장르)/오디오(bpm·energy)/화성 키 블록별 유사도를 가중합하는 유사곡 탐색.

화성 키 유사도는 장르가 겹칠 때만 의미 있는 신호라고 보고, 최종 점수에서
태그 유사도를 곱해 게이팅한다 — 장르가 완전히 다르면(tag_sim≈0) 키가 아무리
가까워도 점수에 거의 기여하지 못한다.
"""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .vectorize import build_feature_blocks

DEFAULT_TAG_WEIGHT = 0.5
DEFAULT_AUDIO_WEIGHT = 0.35
DEFAULT_KEY_WEIGHT = 0.15
DEFAULT_ZONE_LOW = 0.6
DEFAULT_ZONE_HIGH = 0.8
DEFAULT_BOREDOM_WEIGHT = 0.0


class SimilarTrack(NamedTuple):
    track_id: int
    artist: str | None
    title: str | None
    similarity: float
    top_features: list[str]
    boredom_score: float = 0.0


def _track_label(conn: sqlite3.Connection, track_id: int) -> tuple[str | None, str | None]:
    row = conn.execute("SELECT artist, title FROM tracks WHERE id = ?", (track_id,)).fetchone()
    return (row[0], row[1]) if row else (None, None)


def _unit(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def _pairwise_cosine(seed_vec: np.ndarray, others: np.ndarray) -> np.ndarray:
    """0벡터(예: key 정보 없음)가 섞여 있어도 NaN 없이 유사도 0으로 처리한다."""
    if np.linalg.norm(seed_vec) == 0:
        return np.zeros(len(others))
    sims = cosine_similarity(seed_vec.reshape(1, -1), others)[0]
    sims[np.linalg.norm(others, axis=1) == 0] = 0.0
    return sims


def _top_contributing_features(
    blocks,
    seed_id: int,
    other_id: int,
    tag_weight: float,
    audio_weight: float,
    key_contribution: float,
    top_n: int = 3,
) -> list[str]:
    """블록별 원소 기여도를 가중치까지 반영해 합치고, 상위 항목의 이름을 반환한다.

    key 블록은 cos/sin 차원 각각이 사람이 읽기엔 의미가 없어서, 미리 계산해둔
    key_contribution(=key_weight * key_sim * tag_sim) 하나를 "key:harmonic_match"로 대표시킨다.
    """
    contributions: list[tuple[float, str]] = []
    for names, vectors, weight in (
        (blocks.tag_names, blocks.tag_vectors, tag_weight),
        (blocks.audio_names, blocks.audio_vectors, audio_weight),
    ):
        seed_vec = _unit(vectors[seed_id])
        other_vec = _unit(vectors[other_id])
        for name, elementwise in zip(names, seed_vec * other_vec):
            contrib = weight * elementwise
            if contrib > 0:
                contributions.append((contrib, name))

    if key_contribution > 0:
        contributions.append((key_contribution, "key:harmonic_match"))

    contributions.sort(key=lambda pair: pair[0], reverse=True)
    return [name for _, name in contributions[:top_n]]


def _boredom_penalty_factor(boredom_score: float, boredom_weight: float) -> float:
    """질림 스코어를 [0, 1) 구간으로 눌러 담아, 유사도를 최대 boredom_weight 비율만큼 깎는 계수를 만든다.

    원본 질림 스코어는 상한이 없는 누적값이라 그대로 빼면 가중치의 의미가
    불분명해지므로, score/(1+score) 포화 함수로 정규화한 뒤 곱셈 페널티로 적용한다.
    """
    normalized = boredom_score / (1 + boredom_score)
    return 1 - boredom_weight * normalized


def _rank_all(
    conn: sqlite3.Connection,
    seed_track_id: int,
    tag_weight: float,
    audio_weight: float,
    key_weight: float,
    boredom_scores: dict[int, float] | None = None,
    boredom_weight: float = DEFAULT_BOREDOM_WEIGHT,
    exclude_tired_above: float | None = None,
) -> list[SimilarTrack]:
    """시드 트랙 대비 다른 모든 트랙의 가중합 유사도를 계산해 내림차순으로 반환한다.

    boredom_weight > 0이면 질림 스코어가 높은 트랙의 유사도를 깎아 순위를 낮추고,
    exclude_tired_above가 주어지면 그 값을 넘는 트랙은 아예 후보에서 제외한다.
    """
    blocks = build_feature_blocks(conn)
    if seed_track_id not in blocks.tag_vectors:
        raise ValueError(f"트랙 id {seed_track_id}가 DB에 없음")

    other_ids = [tid for tid in blocks.tag_vectors if tid != seed_track_id]
    if not other_ids:
        return []

    tag_matrix = np.array([blocks.tag_vectors[tid] for tid in other_ids])
    audio_matrix = np.array([blocks.audio_vectors[tid] for tid in other_ids])
    key_matrix = np.array([blocks.key_vectors[tid] for tid in other_ids])

    tag_sims = _pairwise_cosine(blocks.tag_vectors[seed_track_id], tag_matrix)
    audio_sims = _pairwise_cosine(blocks.audio_vectors[seed_track_id], audio_matrix)
    key_sims_raw = _pairwise_cosine(blocks.key_vectors[seed_track_id], key_matrix)
    key_sims = (key_sims_raw + 1) / 2  # [-1, 1] -> [0, 1] (부분점수 취지에 맞게 재조정)

    key_contributions = key_weight * key_sims * tag_sims
    scores = tag_weight * tag_sims + audio_weight * audio_sims + key_contributions

    boredom_scores = boredom_scores or {}
    candidate_idx = range(len(other_ids))
    if exclude_tired_above is not None:
        candidate_idx = [i for i in candidate_idx if boredom_scores.get(other_ids[i], 0.0) <= exclude_tired_above]

    if boredom_weight > 0:
        rank_key = lambda i: scores[i] * _boredom_penalty_factor(boredom_scores.get(other_ids[i], 0.0), boredom_weight)  # noqa: E731
    else:
        rank_key = lambda i: scores[i]  # noqa: E731
    ranked_idx = sorted(candidate_idx, key=rank_key, reverse=True)

    results = []
    for idx in ranked_idx:
        track_id = other_ids[idx]
        artist, title = _track_label(conn, track_id)
        top_features = _top_contributing_features(
            blocks, seed_track_id, track_id, tag_weight, audio_weight, float(key_contributions[idx])
        )
        results.append(
            SimilarTrack(
                track_id, artist, title, float(scores[idx]), top_features, boredom_scores.get(track_id, 0.0)
            )
        )
    return results


def find_similar(
    conn: sqlite3.Connection,
    seed_track_id: int,
    top_n: int = 5,
    tag_weight: float = DEFAULT_TAG_WEIGHT,
    audio_weight: float = DEFAULT_AUDIO_WEIGHT,
    key_weight: float = DEFAULT_KEY_WEIGHT,
    boredom_scores: dict[int, float] | None = None,
    boredom_weight: float = DEFAULT_BOREDOM_WEIGHT,
    exclude_tired_above: float | None = None,
) -> list[SimilarTrack]:
    """시드 트랙과 가중합 유사도가 높은 순으로 다른 트랙을 랭킹한다."""
    return _rank_all(
        conn, seed_track_id, tag_weight, audio_weight, key_weight, boredom_scores, boredom_weight, exclude_tired_above
    )[:top_n]


def find_digging_zone(
    conn: sqlite3.Connection,
    seed_track_id: int,
    top_n: int = 5,
    zone_low: float = DEFAULT_ZONE_LOW,
    zone_high: float = DEFAULT_ZONE_HIGH,
    tag_weight: float = DEFAULT_TAG_WEIGHT,
    audio_weight: float = DEFAULT_AUDIO_WEIGHT,
    key_weight: float = DEFAULT_KEY_WEIGHT,
    boredom_scores: dict[int, float] | None = None,
    boredom_weight: float = DEFAULT_BOREDOM_WEIGHT,
    exclude_tired_above: float | None = None,
) -> list[SimilarTrack]:
    """가장 가까운 트랙 대신, 유사도가 [zone_low, zone_high] 구간인 "디깅 존" 트랙을 찾는다.

    최근접 이웃만 계속 추천하면 이미 아는 것과 비슷한 곡만 나오는 필터버블
    위험이 있어서(기획서 7-4), 일부러 "적당히 먼" 구간에서 후보를 뽑는다.
    """
    ranked = _rank_all(
        conn, seed_track_id, tag_weight, audio_weight, key_weight, boredom_scores, boredom_weight, exclude_tired_above
    )
    zone = [r for r in ranked if zone_low <= r.similarity <= zone_high]
    return zone[:top_n]
