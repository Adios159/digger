"""디렉토리 내 오디오 파일을 일괄 분석해 DB에 적재하는 CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import crosswalk
from .analysis import analyze_track
from .db import connect, upsert_track, upsert_track_tags
from .metadata import discogs, lastfm, musicbrainz

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


def _discogs_tags(artist: str, title: str) -> list[dict]:
    release = discogs.search_release(artist, title)
    if not release:
        return []
    tags = [
        {"source": "discogs", "tag_type": "genre", "raw_tag": g, "canonical_style": g}
        for g in release.get("genre", [])
    ]
    tags += [
        {"source": "discogs", "tag_type": "style", "raw_tag": s, "canonical_style": s}
        for s in release.get("style", [])
    ]
    return tags


def _lastfm_tags(artist: str, title: str) -> list[dict]:
    tags = lastfm.get_top_tags(artist, title)
    return [
        {
            "source": "lastfm",
            "tag_type": "freeform",
            "raw_tag": t["name"],
            "weight": float(t.get("count", 0)),
            "canonical_style": crosswalk.normalize(t["name"]),
        }
        for t in tags
    ]


def _musicbrainz_tags(artist: str, title: str) -> list[dict]:
    recording = musicbrainz.search_recording(artist, title)
    if not recording:
        return []
    tags = musicbrainz.get_tags(recording["id"])
    return [
        {
            "source": "musicbrainz",
            "tag_type": "freeform",
            "raw_tag": t["name"],
            "weight": float(t.get("count", 0)),
            "canonical_style": crosswalk.normalize(t["name"]),
        }
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="digger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="디렉토리 내 오디오 파일 분석 후 DB 적재")
    analyze_parser.add_argument("directory")
    analyze_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    enrich_parser = subparsers.add_parser("enrich", help="DB의 트랙에 Last.fm/MusicBrainz/Discogs 태그 적재")
    enrich_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    args = parser.parse_args()

    if args.command == "analyze":
        analyze_directory(args.directory, args.db)
    elif args.command == "enrich":
        enrich_tracks(args.db)


if __name__ == "__main__":
    main()
