"""디렉토리 내 오디오 파일을 일괄 분석해 DB에 적재하는 CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import crosswalk
from .analysis import analyze_track
from .db import connect, upsert_track, upsert_track_tags
from .metadata import discogs, lastfm, musicbrainz
from .similarity import find_similar

AUDIO_EXTENSIONS = {".flac", ".mp3", ".wav"}
DEFAULT_DB_PATH = "digger.db"


def analyze_directory(directory: str, db_path: str = DEFAULT_DB_PATH) -> None:
    files = sorted(
        p for p in Path(directory).iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not files:
        print(f"{directory}에 분석할 오디오 파일이 없음", file=sys.stderr)
        return

    conn = connect(db_path)
    for i, path in enumerate(files, start=1):
        print(f"[{i}/{len(files)}] 분석 중: {path.name}")
        track = analyze_track(str(path))
        upsert_track(conn, track)
        print(f"    -> artist={track['artist']!r} bpm={track['bpm']:.1f} key={track['key']} {track['key_scale']}")
    print(f"완료: {len(files)}곡을 {db_path}에 저장함")


def _make_tag(
    source: str,
    tag_type: str,
    raw_tag: str,
    weight: float | None = None,
    canonical_style: str | None = None,
) -> dict:
    return {
        "source": source,
        "tag_type": tag_type,
        "raw_tag": raw_tag,
        "weight": weight,
        "canonical_style": canonical_style,
    }


def _discogs_tags(artist: str, title: str) -> list[dict]:
    release = discogs.search_release(artist, title)
    if not release:
        return []
    tags = [_make_tag("discogs", "genre", g, canonical_style=g) for g in release.get("genre", [])]
    tags += [_make_tag("discogs", "style", s, canonical_style=s) for s in release.get("style", [])]
    return tags


def _lastfm_tags(artist: str, title: str) -> list[dict]:
    tags = lastfm.get_top_tags(artist, title)
    return [
        _make_tag(
            "lastfm",
            "freeform",
            t["name"],
            weight=float(t.get("count") or 0),
            canonical_style=crosswalk.normalize(t["name"]),
        )
        for t in tags
    ]


def _musicbrainz_tags(artist: str, title: str) -> list[dict]:
    recording = musicbrainz.search_recording(artist, title)
    if not recording:
        return []
    tags = musicbrainz.get_tags(recording["id"])
    return [
        _make_tag(
            "musicbrainz",
            "freeform",
            t["name"],
            weight=float(t.get("count") or 0),
            canonical_style=crosswalk.normalize(t["name"]),
        )
        for t in tags
    ]


def enrich_tracks(db_path: str = DEFAULT_DB_PATH) -> None:
    """DB의 모든 트랙에 대해 Last.fm/MusicBrainz/Discogs 태그를 조회해 적재한다."""
    conn = connect(db_path)
    rows = conn.execute("SELECT id, artist, title FROM tracks").fetchall()
    if not rows:
        print("DB에 트랙이 없음. 먼저 analyze를 실행할 것", file=sys.stderr)
        return

    for i, (track_id, artist, title) in enumerate(rows, start=1):
        print(f"[{i}/{len(rows)}] 태그 조회 중: {artist} - {title}")
        if not artist:
            print("    아티스트 정보 없음, 건너뜀", file=sys.stderr)
            continue
        tags: list[dict] = []
        for label, fetch in (
            ("discogs", _discogs_tags),
            ("lastfm", _lastfm_tags),
            ("musicbrainz", _musicbrainz_tags),
        ):
            try:
                fetched = fetch(artist, title)
                tags += fetched
                print(f"    {label}: {len(fetched)}개 태그")
            except Exception as e:
                print(f"    {label} 조회 실패: {e}", file=sys.stderr)

        upsert_track_tags(conn, track_id, tags)
    print(f"완료: {len(rows)}곡의 태그를 {db_path}에 저장함")


def _resolve_seed_track_id(conn, query: str) -> int | None:
    """`query`를 track id로 우선 해석하고, 숫자가 아니면 artist/title 부분일치로 찾는다."""
    if query.isdigit():
        row = conn.execute("SELECT id FROM tracks WHERE id = ?", (int(query),)).fetchone()
        if row:
            return row[0]
        print(f"id={query}인 트랙이 없음", file=sys.stderr)
        return None

    rows = conn.execute(
        "SELECT id, artist, title FROM tracks WHERE artist LIKE ? OR title LIKE ?",
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
    if not rows:
        print(f"'{query}'와 일치하는 트랙이 없음", file=sys.stderr)
        return None
    if len(rows) > 1:
        print(f"'{query}'와 일치하는 트랙이 여러 개임, 더 구체적으로 입력할 것:", file=sys.stderr)
        for track_id, artist, title in rows:
            print(f"  id={track_id}: {artist} - {title}", file=sys.stderr)
        return None
    return rows[0][0]


def similar_tracks(seed: str, top_n: int = 5, db_path: str = DEFAULT_DB_PATH) -> None:
    """코사인 유사도 기준으로 시드 트랙과 가까운 트랙을 찾아 출력한다."""
    conn = connect(db_path)
    seed_track_id = _resolve_seed_track_id(conn, seed)
    if seed_track_id is None:
        return

    seed_artist, seed_title = conn.execute(
        "SELECT artist, title FROM tracks WHERE id = ?", (seed_track_id,)
    ).fetchone()
    print(f"시드 트랙: {seed_artist} - {seed_title} (id={seed_track_id})")

    try:
        results = find_similar(conn, seed_track_id, top_n=top_n)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return

    if not results:
        print("비교할 다른 트랙이 없음", file=sys.stderr)
        return

    for rank, r in enumerate(results, start=1):
        reason = ", ".join(r.top_features) if r.top_features else "공통 특성 없음"
        print(f"{rank}. {r.artist} - {r.title} (유사도={r.similarity:.3f}) — {reason}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="digger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="디렉토리 내 오디오 파일 분석 후 DB 적재")
    analyze_parser.add_argument("directory")
    analyze_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    enrich_parser = subparsers.add_parser("enrich", help="DB의 트랙에 Last.fm/MusicBrainz/Discogs 태그 적재")
    enrich_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    similar_parser = subparsers.add_parser("similar", help="코사인 유사도 기반 유사곡 탐색")
    similar_parser.add_argument("seed", help="시드 트랙의 id 또는 아티스트/제목 일부")
    similar_parser.add_argument("--top", type=int, default=5, dest="top_n")
    similar_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    args = parser.parse_args()

    if args.command == "analyze":
        analyze_directory(args.directory, args.db)
    elif args.command == "enrich":
        enrich_tracks(args.db)
    elif args.command == "similar":
        similar_tracks(args.seed, args.top_n, args.db)


if __name__ == "__main__":
    main()
