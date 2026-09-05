"""트랙별 오디오 특성 + 태그를 결합한 특성 벡터 빌더."""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

import numpy as np

# Essentia key_edma는 곡에 따라 샵/플랫 표기를 섞어서 반환하므로 둘 다 같은 pitch class로 매핑한다.
_PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_KEY_TO_PITCH_CLASS = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


class FeatureVectors(NamedTuple):
    """트랙 id -> 특성 벡터, 그리고 각 벡터 차원이 무엇을 의미하는지."""

    feature_names: list[str]
    vectors: dict[int, np.ndarray]


def _normalize(values: list[float | None]) -> list[float]:
    """None은 0으로 채우고 min-max 정규화한다. 값이 모두 같으면 0으로 채운다."""
    filled = [v if v is not None else 0.0 for v in values]
    lo, hi = min(filled), max(filled)
    if hi == lo:
        return [0.0 for _ in filled]
    return [(v - lo) / (hi - lo) for v in filled]


def _key_vector(key: str | None, scale: str | None) -> list[float]:
    """12음 pitch class one-hot + major 여부(1차원)."""
    vec = [0.0] * (len(_PITCH_CLASSES) + 1)
    pitch_class = _KEY_TO_PITCH_CLASS.get(key or "")
    if pitch_class is not None:
        vec[pitch_class] = 1.0
    if scale == "major":
        vec[-1] = 1.0
    return vec


def _unit_normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def _build_audio_block(tracks: list[tuple]) -> tuple[list[str], list[list[float]]]:
    """tracks: (id, bpm, key, key_scale, energy) 튜플 목록."""
    bpm_norm = _normalize([row[1] for row in tracks])
    energy_norm = _normalize([row[4] for row in tracks])
    names = ["audio:bpm", "audio:energy"] + [f"audio:key:{k}" for k in _PITCH_CLASSES] + ["audio:scale:major"]

    rows = []
    for i, row in enumerate(tracks):
        _, _, key, key_scale, _ = row
        rows.append([bpm_norm[i], energy_norm[i], *_key_vector(key, key_scale)])
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


def build_feature_vectors(conn: sqlite3.Connection) -> FeatureVectors:
    """DB의 모든 트랙에 대해 오디오+태그 결합 특성 벡터를 만든다.

    오디오 블록과 태그 블록을 각각 단위 벡터로 정규화한 뒤 이어붙여서,
    태그 어휘 크기가 커져도 코사인 유사도에서 오디오 특성이 묻히지 않게 한다.
    """
    tracks = conn.execute("SELECT id, bpm, key, key_scale, energy FROM tracks").fetchall()
    track_ids = [row[0] for row in tracks]

    audio_names, audio_rows = _build_audio_block(tracks)
    tag_names, tag_vecs = _build_tag_block(conn, track_ids)

    feature_names = audio_names + tag_names
    vectors: dict[int, np.ndarray] = {}
    for i, track_id in enumerate(track_ids):
        audio_vec = _unit_normalize(np.array(audio_rows[i], dtype=float))
        tag_vec = _unit_normalize(np.array(tag_vecs[track_id], dtype=float))
        vectors[track_id] = np.concatenate([audio_vec, tag_vec])

    return FeatureVectors(feature_names=feature_names, vectors=vectors)
