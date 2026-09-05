"""디렉토리 내 오디오 파일을 일괄 분석해 DB에 적재하는 CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis import analyze_track
from .db import connect, upsert_track

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


def main() -> None:
    parser = argparse.ArgumentParser(prog="digger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="디렉토리 내 오디오 파일 분석 후 DB 적재")
    analyze_parser.add_argument("directory")
    analyze_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    args = parser.parse_args()

    if args.command == "analyze":
        analyze_directory(args.directory, args.db)


if __name__ == "__main__":
    main()
