"""Essentia 기반 오디오 특성 분석."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import essentia.standard as es
import numpy as np
from mutagen import File as MutagenFile

_TRACK_NUM_PREFIX = re.compile(r"^\d+[\s.\-]*")


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def read_tags(file_path: str) -> dict[str, str | None]:
    """파일의 태그를 읽는다. 태그가 없으면 파일명(`아티스트 - 앨범 - 트랙 제목`)에서 유추한다."""
    artist = title = album = None
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio and audio.tags:
            artist = (audio.tags.get("artist") or [None])[0]
            title = (audio.tags.get("title") or [None])[0]
            album = (audio.tags.get("album") or [None])[0]
    except Exception:
        pass

    if not artist or not title:
        parts = [p.strip() for p in Path(file_path).stem.split(" - ")]
        if len(parts) >= 3:
            artist = artist or parts[0]
            album = album or parts[1]
            title = title or _TRACK_NUM_PREFIX.sub("", parts[-1])
        elif len(parts) == 2:
            artist = artist or parts[0]
            title = title or parts[1]
        else:
            title = title or parts[0]

    return {"artist": artist, "title": title, "album": album}


def analyze_track(file_path: str) -> dict[str, Any]:
    """오디오 파일 하나를 Essentia로 분석해 태그 + 음향 특성을 담은 딕셔너리로 반환한다."""
    tags = read_tags(file_path)

    extractor = es.MusicExtractor()
    pool, _ = extractor(file_path)
    raw_features = {name: _to_jsonable(pool[name]) for name in pool.descriptorNames()}

    return {
        **tags,
        "file_path": file_path,
        "bpm": raw_features.get("rhythm.bpm"),
        "key": raw_features.get("tonal.key_edma.key"),
        "key_scale": raw_features.get("tonal.key_edma.scale"),
        "energy": raw_features.get("lowlevel.average_loudness"),
        "duration_sec": raw_features.get("metadata.audio_properties.length"),
        "raw_features": raw_features,
    }
