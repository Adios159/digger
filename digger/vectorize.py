"""트랙별 장르 태그 특성 벡터 빌더.

bpm/key/energy 등 음향 특성은 유사도 계산에서 취향과의 상관성이 낮다고 판단해
제외했다 — analyze는 여전히 Essentia로 이 값들을 계산해 tracks 테이블에
저장하지만(추후 Discogs-EffNet 기반 장르 추론 등에 재사용할 여지), 유사도는
태그(장르) 벡터만으로 계산한다.

태그는 출처 간 합의 정도로 가중치를 차등한다: Discogs와 자유형 태그가 같은 style을
말하면 확증(1.0), 대조군이 없는 단독 태그는 절반(0.5), 자유형 태그가 정면으로
다른 얘기를 하는 Discogs 태그는 릴리즈 오매칭으로 보고 버린다.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import NamedTuple

import numpy as np

from . import crosswalk


class FeatureBlocks(NamedTuple):
    tag_names: list[str]
    tag_vectors: dict[int, np.ndarray]


CONFIRMED_WEIGHT = 1.0  # Discogs와 자유형 태그가 같은 style을 말함
UNCONTESTED_WEIGHT = 0.5  # 한쪽만 말했고, 반대쪽에는 반증할 데이터가 없음


def resolve_styles_by_source(
    conn: sqlite3.Connection,
) -> tuple[dict[int, dict[str, float]], dict[int, dict[str, float]]]:
    """트랙별 태그를 canonical style로 해석해 Discogs / 자유형(Last.fm·MusicBrainz)으로 나눈다.

    저장된 canonical_style 대신 지금 시점의 리졸버로 다시 해석한다 — Discogs 어휘가
    자라거나 YAML을 채우면 enrich를 다시 돌리지 않아도 바로 반영되기 때문.
    """
    resolve = crosswalk.build_resolver(conn)

    discogs: dict[int, dict[str, float]] = defaultdict(dict)
    freeform: dict[int, dict[str, float]] = defaultdict(dict)
    for track_id, source, raw_tag, weight in conn.execute(
        "SELECT track_id, source, raw_tag, weight FROM track_tags"
    ):
        style = resolve(raw_tag)
        if style is None:
            continue
        # Discogs genre/style은 weight가 없어 최대치로 본다. 자유형 태그의 count는
        # "그 곡에서 이 태그가 얼마나 우세한가"의 상대 지표라 1위만 100에 붙고 나머지는
        # 한 자리로 떨어진다 — 선형으로 쓰면 2위 이하가 사실상 소멸해서 제곱근으로 완만하게 편다.
        strength = 1.0 if weight is None else math.sqrt(min(weight, 100.0) / 100.0)
        bucket = discogs if source == "discogs" else freeform
        bucket[track_id][style] = max(bucket[track_id].get(style, 0.0), strength)

    return discogs, freeform


def agreement_weights(
    discogs_styles: dict[str, float], freeform_styles: dict[str, float]
) -> dict[str, float]:
    """두 출처의 합의 상태에 따라 style별 최종 가중치를 정한다.

    Discogs 신뢰 여부는 태그 하나하나가 아니라 트랙 단위로 판단한다 — Discogs의 실패
    방식은 "릴리즈를 통째로 잘못 잡는 것"이라(한국 랩 곡에 "Polka"가 붙는 식) 하나라도
    겹치면 릴리즈는 제대로 잡힌 것이고, 나머지 태그도 그 릴리즈의 정보라 함께 믿는다.
    반대로 자유형 태그가 있는데 하나도 안 겹치면 릴리즈 자체를 의심해 통째로 버린다.

    자유형 태그는 곡 자체에는 맞되 어휘가 지저분한 쪽이라, 겹치지 않아도 버리지 않고
    신호 세기에 비례해 낮은 가중치로 살린다.

    한계: 세부 장르 어휘만 다른 경우(Discogs "Deep House" vs Last.fm "Tech House")도
    불일치로 보고 버린다. 장르 계열까지 보면 살릴 수 있지만 실측상 오탐이 4곡 중
    1곡이라, 계열 지도를 들이는 대신 "의심스러우면 버린다"는 보수적인 쪽을 택했다.
    """
    confirmed = set(discogs_styles) & set(freeform_styles)
    discogs_trusted = bool(confirmed) or not freeform_styles

    weights = {style: CONFIRMED_WEIGHT for style in confirmed}

    if discogs_trusted:
        for style in discogs_styles:
            weights.setdefault(style, UNCONTESTED_WEIGHT)

    for style, strength in freeform_styles.items():
        if style not in confirmed:
            weights[style] = UNCONTESTED_WEIGHT * strength

    return weights


def _build_tag_block(
    conn: sqlite3.Connection, track_ids: list[int]
) -> tuple[list[str], dict[int, list[float]]]:
    """출처 간 합의 등급을 반영한 트랙별 태그 벡터를 만든다."""
    discogs, freeform = resolve_styles_by_source(conn)

    weights_by_track = {
        track_id: agreement_weights(discogs.get(track_id, {}), freeform.get(track_id, {}))
        for track_id in track_ids
    }

    vocabulary = sorted({style for weights in weights_by_track.values() for style in weights})
    index = {style: i for i, style in enumerate(vocabulary)}

    tag_vecs = {tid: [0.0] * len(vocabulary) for tid in track_ids}
    for track_id, weights in weights_by_track.items():
        for style, weight in weights.items():
            tag_vecs[track_id][index[style]] = weight

    names = [f"tag:{style}" for style in vocabulary]
    return names, tag_vecs


def build_feature_blocks(conn: sqlite3.Connection) -> FeatureBlocks:
    """DB의 모든 트랙에 대해 태그 벡터 블록을 만든다."""
    track_ids = [row[0] for row in conn.execute("SELECT id FROM tracks").fetchall()]

    tag_names, tag_vecs = _build_tag_block(conn, track_ids)
    tag_vectors = {tid: np.array(tag_vecs[tid], dtype=float) for tid in track_ids}

    return FeatureBlocks(tag_names=tag_names, tag_vectors=tag_vectors)
