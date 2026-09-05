"""트랙별 장르 태그 특성 벡터 빌더.

bpm/key/energy 등 음향 특성은 유사도 계산에서 취향과의 상관성이 낮다고 판단해
제외했다 — analyze는 여전히 Essentia로 이 값들을 계산해 tracks 테이블에
저장하지만(추후 Discogs-EffNet 기반 장르 추론 등에 재사용할 여지), 유사도는
태그(장르) 벡터만으로 계산한다.
"""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

import numpy as np


class FeatureBlocks(NamedTuple):
    tag_names: list[str]
    tag_vectors: dict[int, np.ndarray]


def _build_tag_block(
    conn: sqlite3.Connection, track_ids: list[int]
) -> tuple[list[str], dict[int, list[float]]]:
    """canonical_style이 있는 태그만으로 트랙별 태그 벡터를 만든다.

    같은 canonical_style을 여러 소스가 보고하면 가중치를 합산한다(더 확실한 신호로 취급).
    Discogs 공식 genre/style은 weight가 없으므로 최대 가중치(100)로 취급한다.
    """
    rows = conn.execute(
        "SELECT track_id, canonical_style, weight FROM track_tags WHERE canonical_style IS NOT NULL"
    ).fetchall()

    vocabulary = sorted({row[1] for row in rows})
    index = {style: i for i, style in enumerate(vocabulary)}

    tag_vecs = {tid: [0.0] * len(vocabulary) for tid in track_ids}
    for track_id, canonical_style, weight in rows:
        if track_id not in tag_vecs:
            continue
        capped_weight = min(weight, 100.0) if weight is not None else 100.0
        tag_vecs[track_id][index[canonical_style]] += capped_weight / 100.0

    names = [f"tag:{style}" for style in vocabulary]
    return names, tag_vecs


def build_feature_blocks(conn: sqlite3.Connection) -> FeatureBlocks:
    """DB의 모든 트랙에 대해 태그 벡터 블록을 만든다."""
    track_ids = [row[0] for row in conn.execute("SELECT id FROM tracks").fetchall()]

    tag_names, tag_vecs = _build_tag_block(conn, track_ids)
    tag_vectors = {tid: np.array(tag_vecs[tid], dtype=float) for tid in track_ids}

    return FeatureBlocks(tag_names=tag_names, tag_vectors=tag_vectors)
