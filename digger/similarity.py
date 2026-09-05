"""코사인 유사도 기반 유사곡 탐색."""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .vectorize import build_feature_vectors


class SimilarTrack(NamedTuple):
    track_id: int
    artist: str | None
    title: str | None
    similarity: float
    top_features: list[str]


def _track_label(conn: sqlite3.Connection, track_id: int) -> tuple[str | None, str | None]:
    row = conn.execute("SELECT artist, title FROM tracks WHERE id = ?", (track_id,)).fetchone()
    return (row[0], row[1]) if row else (None, None)


def _top_contributing_features(
    seed_vec: np.ndarray, other_vec: np.ndarray, feature_names: list[str], top_n: int = 3
) -> list[str]:
    """두 벡터의 원소별 곱(코사인 유사도에 대한 기여분)이 큰 특성 이름을 반환한다."""
    contributions = seed_vec * other_vec
    top_indices = np.argsort(contributions)[::-1][:top_n]
    return [feature_names[i] for i in top_indices if contributions[i] > 0]


def find_similar(conn: sqlite3.Connection, seed_track_id: int, top_n: int = 5) -> list[SimilarTrack]:
    """시드 트랙과 코사인 유사도가 높은 순으로 다른 트랙을 랭킹한다."""
    feature_names, vectors = build_feature_vectors(conn)
    if seed_track_id not in vectors:
        raise ValueError(f"트랙 id {seed_track_id}가 DB에 없음")

    seed_vec = vectors[seed_track_id]
    other_ids = [tid for tid in vectors if tid != seed_track_id]
    if not other_ids:
        return []

    other_matrix = np.array([vectors[tid] for tid in other_ids])
    sims = cosine_similarity(seed_vec.reshape(1, -1), other_matrix)[0]

    ranked = sorted(zip(other_ids, sims), key=lambda pair: pair[1], reverse=True)[:top_n]

    results = []
    for track_id, sim in ranked:
        artist, title = _track_label(conn, track_id)
        top_features = _top_contributing_features(seed_vec, vectors[track_id], feature_names)
        results.append(SimilarTrack(track_id, artist, title, float(sim), top_features))
    return results
