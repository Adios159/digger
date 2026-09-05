"""트랙별 오디오 특성 + 화성 키 + 태그를 블록별로 분리한 특성 벡터 빌더.

세 블록(tag/audio/key)을 하나로 합치지 않고 따로 반환한다. 블록을 분리해두면
similarity.py에서 블록별 코사인 유사도를 따로 계산해 가중합할 수 있고,
특히 화성 키 유사도를 태그(장르) 유사도로 게이팅하는 것도 가능해진다.
"""

from __future__ import annotations

import math
import sqlite3
from typing import NamedTuple

import numpy as np

# Essentia key_edma는 곡에 따라 샵/플랫 표기를 섞어서 반환하므로 둘 다 같은 pitch class로 매핑한다.
_KEY_TO_PITCH_CLASS = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}
_FIFTH_STEPS = 7  # 완전5도 = 반음 7개


class FeatureBlocks(NamedTuple):
    """트랙 id -> 블록별 특성 벡터. 각 블록은 정규화 전 원본 값을 담는다.

    (코사인 유사도는 스스로 벡터 크기를 정규화하므로 여기서 미리 단위벡터로
    만들어둘 필요는 없다.)
    """

    tag_names: list[str]
    audio_names: list[str]
    key_names: list[str]
    tag_vectors: dict[int, np.ndarray]
    audio_vectors: dict[int, np.ndarray]
    key_vectors: dict[int, np.ndarray]


def _normalize(values: list[float | None]) -> list[float]:
    """None은 0으로 채우고 min-max 정규화한다. 값이 모두 같으면 0으로 채운다."""
    filled = [v if v is not None else 0.0 for v in values]
    lo, hi = min(filled), max(filled)
    if hi == lo:
        return [0.0 for _ in filled]
    return [(v - lo) / (hi - lo) for v in filled]


def _key_vector(key: str | None, scale: str | None) -> list[float]:
    """key를 circle of fifths 상의 각도(cos, sin) + major 여부로 인코딩한다.

    이진 일치 대신 그레이디드 값을 써서, 정확히 같은 키가 아니어도 완전5도처럼
    화성적으로 가까운 키는 부분점수를 받고 트라이톤처럼 먼 키는 낮은 점수를 받는다.
    """
    pitch_class = _KEY_TO_PITCH_CLASS.get(key or "")
    if pitch_class is None:
        return [0.0, 0.0, 0.0]
    fifths_position = (pitch_class * _FIFTH_STEPS) % 12
    angle = 2 * math.pi * fifths_position / 12
    major_flag = 1.0 if scale == "major" else 0.0
    return [math.cos(angle), math.sin(angle), major_flag]


def _build_audio_block(tracks: list[tuple]) -> tuple[list[str], list[list[float]]]:
    """tracks: (id, bpm, key, key_scale, energy) 튜플 목록. bpm/energy만 다룬다."""
    bpm_norm = _normalize([row[1] for row in tracks])
    energy_norm = _normalize([row[4] for row in tracks])
    names = ["audio:bpm", "audio:energy"]
    rows = [[bpm_norm[i], energy_norm[i]] for i in range(len(tracks))]
    return names, rows


def _build_key_block(tracks: list[tuple]) -> tuple[list[str], list[list[float]]]:
    names = ["key:fifths_cos", "key:fifths_sin", "key:scale_major"]
    rows = [_key_vector(row[2], row[3]) for row in tracks]
    return names, rows


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
    """DB의 모든 트랙에 대해 태그/오디오/키 블록을 각각 만든다."""
    tracks = conn.execute("SELECT id, bpm, key, key_scale, energy FROM tracks").fetchall()
    track_ids = [row[0] for row in tracks]

    audio_names, audio_rows = _build_audio_block(tracks)
    key_names, key_rows = _build_key_block(tracks)
    tag_names, tag_vecs = _build_tag_block(conn, track_ids)

    audio_vectors = {tid: np.array(audio_rows[i], dtype=float) for i, tid in enumerate(track_ids)}
    key_vectors = {tid: np.array(key_rows[i], dtype=float) for i, tid in enumerate(track_ids)}
    tag_vectors = {tid: np.array(tag_vecs[tid], dtype=float) for tid in track_ids}

    return FeatureBlocks(
        tag_names=tag_names,
        audio_names=audio_names,
        key_names=key_names,
        tag_vectors=tag_vectors,
        audio_vectors=audio_vectors,
        key_vectors=key_vectors,
    )
