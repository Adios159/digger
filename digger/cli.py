"""디렉토리 내 오디오 파일을 일괄 분석해 DB에 적재하는 CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import crosswalk
from .analysis import analyze_track
from .boredom import compute_boredom_scores
from .db import (
    connect,
    replace_top_tracks,
    update_track_mbid,
    upsert_listening_history,
    upsert_relations,
    upsert_track,
    upsert_track_tags,
)
from .graph import dig_relations
from .metadata import discogs, lastfm, musicbrainz, spotify
from .relations import CATEGORIES, COLLAB_KEYWORDS, INFLUENCE_KEYWORDS, SAMPLE_KEYWORDS
from .similarity import (
    DEFAULT_AUDIO_WEIGHT,
    DEFAULT_KEY_WEIGHT,
    DEFAULT_TAG_WEIGHT,
    DEFAULT_ZONE_HIGH,
    DEFAULT_ZONE_LOW,
    find_digging_zone,
    find_similar,
)

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


def _relation_attributes(rel: dict) -> list:
    attributes = list(rel.get("attributes") or [])
    if rel.get("direction"):
        attributes.append(f"direction:{rel['direction']}")
    return attributes


def _normalize_recording_relations(
    mb_recording_id: str, track_artist: str, track_title: str, raw_relations: list[dict]
) -> list[dict]:
    """레코딩 관계 원본에서 프로듀서·작곡가·엔지니어 협업(recording->artist)과
    샘플링(recording->recording) 관계만 골라 relations 테이블 형식으로 변환한다."""
    relations = []
    from_name = f"{track_artist} - {track_title}"
    for rel in raw_relations:
        rel_type = (rel.get("type") or "").lower()
        target_type = rel.get("target-type")
        if target_type == "artist" and any(k in rel_type for k in COLLAB_KEYWORDS):
            artist = rel.get("artist") or {}
            relations.append(
                {
                    "source": "musicbrainz",
                    "relation_type": rel.get("type"),
                    "from_entity_type": "recording",
                    "from_entity_id": mb_recording_id,
                    "from_entity_name": from_name,
                    "to_entity_type": "artist",
                    "to_entity_id": artist.get("id"),
                    "to_entity_name": artist.get("name"),
                    "attributes": _relation_attributes(rel),
                }
            )
        elif target_type == "recording" and any(k in rel_type for k in SAMPLE_KEYWORDS):
            recording = rel.get("recording") or {}
            relations.append(
                {
                    "source": "musicbrainz",
                    "relation_type": rel.get("type"),
                    "from_entity_type": "recording",
                    "from_entity_id": mb_recording_id,
                    "from_entity_name": from_name,
                    "to_entity_type": "recording",
                    "to_entity_id": recording.get("id"),
                    "to_entity_name": recording.get("title"),
                    "attributes": _relation_attributes(rel),
                }
            )
    return relations


def _normalize_artist_relations(artist_mbid: str, artist_name: str, raw_relations: list[dict]) -> list[dict]:
    """아티스트 관계 원본에서 레이블 소속(artist->label)과 영향 관계(artist->artist)만
    골라 relations 테이블 형식으로 변환한다."""
    relations = []
    for rel in raw_relations:
        rel_type = (rel.get("type") or "").lower()
        target_type = rel.get("target-type")
        if target_type == "label":
            label = rel.get("label") or {}
            relations.append(
                {
                    "source": "musicbrainz",
                    "relation_type": rel.get("type"),
                    "from_entity_type": "artist",
                    "from_entity_id": artist_mbid,
                    "from_entity_name": artist_name,
                    "to_entity_type": "label",
                    "to_entity_id": label.get("id"),
                    "to_entity_name": label.get("name"),
                    "attributes": _relation_attributes(rel),
                }
            )
        elif target_type == "artist" and any(k in rel_type for k in INFLUENCE_KEYWORDS):
            artist = rel.get("artist") or {}
            relations.append(
                {
                    "source": "musicbrainz",
                    "relation_type": rel.get("type"),
                    "from_entity_type": "artist",
                    "from_entity_id": artist_mbid,
                    "from_entity_name": artist_name,
                    "to_entity_type": "artist",
                    "to_entity_id": artist.get("id"),
                    "to_entity_name": artist.get("name"),
                    "attributes": _relation_attributes(rel),
                }
            )
    return relations


def _musicbrainz_relations(conn, track_id: int, artist: str, title: str) -> list[dict]:
    """레코딩을 찾아 mbid를 저장하고, 협업(프로듀서·작곡가·엔지니어)·샘플·레이블·영향 관계를 조회한다."""
    recording = musicbrainz.search_recording(artist, title)
    if not recording:
        print("    MusicBrainz에서 레코딩을 찾지 못함, 건너뜀", file=sys.stderr)
        return []
    mb_recording_id = recording["id"]
    update_track_mbid(conn, track_id, mb_recording_id)

    relations = _normalize_recording_relations(
        mb_recording_id, artist, title, musicbrainz.get_recording_relations(mb_recording_id)
    )

    credits = recording.get("artist-credit") or []
    if credits:
        credit_artist = credits[0].get("artist") or {}
        artist_mbid = credit_artist.get("id")
        if artist_mbid:
            relations += _normalize_artist_relations(
                artist_mbid,
                credit_artist.get("name", artist),
                musicbrainz.get_artist_relations(artist_mbid),
            )
    return relations


def _discogs_label_relations(track_id: int, artist: str, title: str) -> list[dict]:
    """Discogs 릴리즈 검색 결과의 label 필드에서 소속 레이블 관계를 뽑는다.

    "Not On Label(...)"은 Discogs가 자체발매/레이블 없음을 표기하는 관례적 문자열이라
    관계로 남기지 않고 정직하게 공백 처리한다.
    """
    release = discogs.search_release(artist, title)
    if not release:
        return []
    return [
        {
            "source": "discogs",
            "relation_type": "released_on_label",
            "from_entity_type": "track",
            "from_entity_id": str(track_id),
            "from_entity_name": f"{artist} - {title}",
            "to_entity_type": "label",
            "to_entity_id": None,
            "to_entity_name": label_name,
            "attributes": [],
        }
        for label_name in release.get("label", [])
        if label_name and not label_name.lower().startswith("not on label")
    ]


def collect_relations(db_path: str = DEFAULT_DB_PATH) -> None:
    """DB의 모든 트랙에 대해 MusicBrainz 협업/레이블/샘플/영향 관계 + Discogs 레이블 관계를 적재한다."""
    conn = connect(db_path)
    rows = conn.execute("SELECT id, artist, title FROM tracks").fetchall()
    if not rows:
        print("DB에 트랙이 없음. 먼저 analyze를 실행할 것", file=sys.stderr)
        return

    for i, (track_id, artist, title) in enumerate(rows, start=1):
        print(f"[{i}/{len(rows)}] 관계 조회 중: {artist} - {title}")
        if not artist:
            print("    아티스트 정보 없음, 건너뜀", file=sys.stderr)
            continue

        relations: list[dict] = []
        try:
            fetched = _musicbrainz_relations(conn, track_id, artist, title)
            relations += fetched
            print(f"    musicbrainz: {len(fetched)}개 관계")
        except Exception as e:
            print(f"    musicbrainz 조회 실패: {e}", file=sys.stderr)

        try:
            fetched = _discogs_label_relations(track_id, artist, title)
            relations += fetched
            print(f"    discogs: {len(fetched)}개 관계")
        except Exception as e:
            print(f"    discogs 조회 실패: {e}", file=sys.stderr)

        upsert_relations(conn, relations)
    print(f"완료: {len(rows)}곡의 관계를 {db_path}에 저장함")


SPOTIFY_TOP_TRACK_RANGES = ["short_term", "medium_term", "long_term"]


def _match_local_track(conn, artist: str, title: str) -> int | None:
    """아티스트+제목 완전일치(대소문자 무시)로 로컬 트랙을 찾는다.

    모호하게 여러 개가 걸리거나 하나도 없으면 억지로 추측하지 않고 None으로 남긴다.
    """
    rows = conn.execute(
        "SELECT id FROM tracks WHERE LOWER(artist) = LOWER(?) AND LOWER(title) = LOWER(?)",
        (artist, title),
    ).fetchall()
    return rows[0][0] if len(rows) == 1 else None


def sync_listening_history(db_path: str = DEFAULT_DB_PATH) -> None:
    """Spotify 최근 재생 + 상위 청취곡(short/medium/long_term)을 동기화한다."""
    conn = connect(db_path)

    print("최근 재생 이력 조회 중...")
    recently_played = spotify.get_recently_played()
    history_rows = []
    for item in recently_played:
        track = item.get("track") or {}
        artist = ", ".join(a["name"] for a in track.get("artists", []))
        title = track.get("name")
        history_rows.append(
            {
                "spotify_track_id": track.get("id"),
                "artist": artist,
                "title": title,
                "played_at": item["played_at"],
                "track_id": _match_local_track(conn, artist, title) if artist and title else None,
            }
        )
    upsert_listening_history(conn, history_rows)
    print(f"    {len(history_rows)}건 저장")

    for time_range in SPOTIFY_TOP_TRACK_RANGES:
        print(f"상위 청취곡({time_range}) 조회 중...")
        top_tracks = spotify.get_top_tracks(time_range=time_range)
        top_rows = []
        for rank, track in enumerate(top_tracks, start=1):
            artist = ", ".join(a["name"] for a in track.get("artists", []))
            title = track.get("name")
            top_rows.append(
                {
                    "spotify_track_id": track.get("id"),
                    "artist": artist,
                    "title": title,
                    "rank": rank,
                    "track_id": _match_local_track(conn, artist, title) if artist and title else None,
                }
            )
        replace_top_tracks(conn, time_range, top_rows)
        print(f"    {len(top_rows)}건 저장")

    print(f"완료: 청취 이력을 {db_path}에 저장함")


def boredom_ranking(top_n: int = 10, db_path: str = DEFAULT_DB_PATH) -> None:
    """청취 이력 기반 질림 스코어를 계산해 높은 순으로 출력한다."""
    conn = connect(db_path)
    scores = compute_boredom_scores(conn)
    if not scores:
        print("청취 이력이 없음. 먼저 sync-listening을 실행할 것", file=sys.stderr)
        return

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    for rank, (track_id, score) in enumerate(ranked, start=1):
        row = conn.execute("SELECT artist, title FROM tracks WHERE id = ?", (track_id,)).fetchone()
        artist, title = row if row else ("?", "?")
        print(f"{rank}. {artist} - {title} (질림 스코어={score:.2f})")


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


def similar_tracks(
    seed: str,
    top_n: int = 5,
    db_path: str = DEFAULT_DB_PATH,
    tag_weight: float = DEFAULT_TAG_WEIGHT,
    audio_weight: float = DEFAULT_AUDIO_WEIGHT,
    key_weight: float = DEFAULT_KEY_WEIGHT,
    dig: bool = False,
    zone_low: float = DEFAULT_ZONE_LOW,
    zone_high: float = DEFAULT_ZONE_HIGH,
    boredom_weight: float = 0.0,
    exclude_tired_above: float | None = None,
) -> None:
    """태그/오디오/키 가중합 유사도 기준으로 시드 트랙과 가까운 트랙을 찾아 출력한다.

    dig=True면 최근접 이웃 대신 [zone_low, zone_high] 구간의 "디깅 존" 후보를 찾는다.
    boredom_weight > 0이면 질림 스코어가 높은 후보의 순위를 낮추고,
    exclude_tired_above가 주어지면 그 값을 넘는 후보는 아예 제외한다.
    """
    conn = connect(db_path)
    seed_track_id = _resolve_seed_track_id(conn, seed)
    if seed_track_id is None:
        return

    seed_artist, seed_title = conn.execute(
        "SELECT artist, title FROM tracks WHERE id = ?", (seed_track_id,)
    ).fetchone()
    print(f"시드 트랙: {seed_artist} - {seed_title} (id={seed_track_id})")

    boredom_scores = compute_boredom_scores(conn) if (boredom_weight > 0 or exclude_tired_above is not None) else None

    try:
        if dig:
            print(f"디깅 존({zone_low:.2f}~{zone_high:.2f}) 탐색 중...")
            results = find_digging_zone(
                conn,
                seed_track_id,
                top_n=top_n,
                zone_low=zone_low,
                zone_high=zone_high,
                tag_weight=tag_weight,
                audio_weight=audio_weight,
                key_weight=key_weight,
                boredom_scores=boredom_scores,
                boredom_weight=boredom_weight,
                exclude_tired_above=exclude_tired_above,
            )
        else:
            results = find_similar(
                conn,
                seed_track_id,
                top_n=top_n,
                tag_weight=tag_weight,
                audio_weight=audio_weight,
                key_weight=key_weight,
                boredom_scores=boredom_scores,
                boredom_weight=boredom_weight,
                exclude_tired_above=exclude_tired_above,
            )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return

    if not results:
        reason = "디깅 존 구간에 해당하는 트랙이 없음. --zone-low/--zone-high로 범위를 넓혀볼 것" if dig else "비교할 다른 트랙이 없음"
        print(reason, file=sys.stderr)
        return

    for rank, r in enumerate(results, start=1):
        reason = ", ".join(r.top_features) if r.top_features else "공통 특성 없음"
        boredom_note = f", 질림={r.boredom_score:.2f}" if boredom_scores is not None else ""
        print(f"{rank}. {r.artist} - {r.title} (유사도={r.similarity:.3f}{boredom_note}) — {reason}")


def dig_relations_command(
    seed: str,
    category: str,
    top_n: int = 10,
    db_path: str = DEFAULT_DB_PATH,
    include_known: bool = False,
    exclude_tired_above: float | None = None,
) -> None:
    """시드 트랙에서 관계(협업/레이블/샘플/영향) 축을 따라가 발견 후보를 찾아 출력한다.

    exclude_tired_above가 주어지면, 이미 아는 곡/아티스트 중 질림 스코어가 그 값을
    넘는 결과는 제외한다(include_known과 별개 — 알고 있어도 안 질렸으면 남는다).
    """
    conn = connect(db_path)
    seed_track_id = _resolve_seed_track_id(conn, seed)
    if seed_track_id is None:
        return

    seed_artist, seed_title, mb_recording_id = conn.execute(
        "SELECT artist, title, mb_recording_id FROM tracks WHERE id = ?", (seed_track_id,)
    ).fetchone()
    print(f"시드 트랙: {seed_artist} - {seed_title} (id={seed_track_id}, 카테고리={category})")
    if not mb_recording_id:
        print("주의: collect-relations를 먼저 실행하지 않은 트랙이라 결과가 없을 수 있음", file=sys.stderr)

    boredom_scores = compute_boredom_scores(conn) if exclude_tired_above is not None else None

    results = dig_relations(
        conn,
        seed_track_id,
        seed_artist,
        seed_title,
        mb_recording_id,
        category,
        top_n=top_n,
        include_known=include_known,
        boredom_scores=boredom_scores,
        exclude_tired_above=exclude_tired_above,
    )
    if not results:
        print("연결된 관계를 찾지 못함. collect-relations를 먼저 실행했는지 확인할 것", file=sys.stderr)
        return

    for rank, r in enumerate(results, start=1):
        known_mark = " (이미 아는 곡/아티스트)" if r["already_known"] else ""
        boredom_note = f", 질림={r['boredom_score']:.2f}" if boredom_scores is not None else ""
        print(f"{rank}. {r['entity_name']}{known_mark}{boredom_note} — {r['path']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="digger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="디렉토리 내 오디오 파일 분석 후 DB 적재")
    analyze_parser.add_argument("directory")
    analyze_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    enrich_parser = subparsers.add_parser("enrich", help="DB의 트랙에 Last.fm/MusicBrainz/Discogs 태그 적재")
    enrich_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    collect_relations_parser = subparsers.add_parser(
        "collect-relations", help="DB의 트랙에 MusicBrainz 협업/레이블/샘플/영향 관계 적재"
    )
    collect_relations_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    similar_parser = subparsers.add_parser("similar", help="태그/오디오/키 가중합 기반 유사곡 탐색")
    similar_parser.add_argument("seed", help="시드 트랙의 id 또는 아티스트/제목 일부")
    similar_parser.add_argument("--top", type=int, default=5, dest="top_n")
    similar_parser.add_argument("--db", default=DEFAULT_DB_PATH)
    similar_parser.add_argument(
        "--tag-weight", type=float, default=DEFAULT_TAG_WEIGHT, help=f"장르/태그 가중치 (기본 {DEFAULT_TAG_WEIGHT})"
    )
    similar_parser.add_argument(
        "--audio-weight", type=float, default=DEFAULT_AUDIO_WEIGHT, help=f"bpm/energy 가중치 (기본 {DEFAULT_AUDIO_WEIGHT})"
    )
    similar_parser.add_argument(
        "--key-weight", type=float, default=DEFAULT_KEY_WEIGHT, help=f"화성 키 가중치 (기본 {DEFAULT_KEY_WEIGHT})"
    )
    similar_parser.add_argument(
        "--dig",
        action="store_true",
        help="최근접 이웃 대신 '디깅 존'(적당히 먼 유사도 구간)에서 후보를 찾음 (필터버블 방지)",
    )
    similar_parser.add_argument(
        "--zone-low", type=float, default=DEFAULT_ZONE_LOW, help=f"디깅 존 하한 (기본 {DEFAULT_ZONE_LOW})"
    )
    similar_parser.add_argument(
        "--zone-high", type=float, default=DEFAULT_ZONE_HIGH, help=f"디깅 존 상한 (기본 {DEFAULT_ZONE_HIGH})"
    )
    similar_parser.add_argument(
        "--boredom-weight",
        type=float,
        default=0.0,
        help="질림 스코어로 순위를 낮추는 비율(0~1). sync-listening으로 청취 이력을 먼저 동기화해야 의미 있음",
    )
    similar_parser.add_argument(
        "--exclude-tired-above", type=float, default=None, help="이 질림 스코어를 넘는 후보는 아예 제외"
    )

    sync_listening_parser = subparsers.add_parser(
        "sync-listening", help="Spotify 최근 재생/상위 청취곡 동기화(최초 실행 시 브라우저 인증)"
    )
    sync_listening_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    boredom_parser = subparsers.add_parser("boredom", help="청취 이력 기반 질림 스코어 랭킹 출력")
    boredom_parser.add_argument("--top", type=int, default=10, dest="top_n")
    boredom_parser.add_argument("--db", default=DEFAULT_DB_PATH)

    dig_relations_parser = subparsers.add_parser(
        "dig-relations", help="협업/레이블/샘플/영향 관계를 따라 아직 모르는 곡·아티스트 탐색"
    )
    dig_relations_parser.add_argument("seed", help="시드 트랙의 id 또는 아티스트/제목 일부")
    dig_relations_parser.add_argument(
        "--relation", choices=list(CATEGORIES), required=True, dest="category", help="탐색할 관계 축"
    )
    dig_relations_parser.add_argument("--top", type=int, default=10, dest="top_n")
    dig_relations_parser.add_argument("--db", default=DEFAULT_DB_PATH)
    dig_relations_parser.add_argument(
        "--include-known", action="store_true", help="이미 로컬 DB에 있는 곡/아티스트도 결과에 포함"
    )
    dig_relations_parser.add_argument(
        "--exclude-tired-above",
        type=float,
        default=None,
        help="이미 아는 곡/아티스트 중 이 질림 스코어를 넘는 결과는 제외 (--include-known과 독립적으로 적용)",
    )

    args = parser.parse_args()

    if args.command == "analyze":
        analyze_directory(args.directory, args.db)
    elif args.command == "enrich":
        enrich_tracks(args.db)
    elif args.command == "collect-relations":
        collect_relations(args.db)
    elif args.command == "similar":
        similar_tracks(
            args.seed,
            args.top_n,
            args.db,
            args.tag_weight,
            args.audio_weight,
            args.key_weight,
            args.dig,
            args.zone_low,
            args.zone_high,
            args.boredom_weight,
            args.exclude_tired_above,
        )
    elif args.command == "sync-listening":
        sync_listening_history(args.db)
    elif args.command == "boredom":
        boredom_ranking(args.top_n, args.db)
    elif args.command == "dig-relations":
        dig_relations_command(
            args.seed, args.category, args.top_n, args.db, args.include_known, args.exclude_tired_above
        )


if __name__ == "__main__":
    main()
