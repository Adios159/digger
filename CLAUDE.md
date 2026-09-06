# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

내가 실제로 좋아하는 곡의 음향적·맥락적 특성을 분석해 아직 모르는 인접곡/아티스트를 찾아주는 개인용 음악 디깅 도구. Python CLI 프로토타입에 FastAPI 레이어(`digger/api.py`)를 얹은 단계이며, DB는 아직 SQLite를 그대로 씀 — 데이터 규모가 실제로 커지면 PostgreSQL(+pgvector)로 옮겨갈 계획이다 (자세한 배경은 `AI_음악_디깅_앱_기획서 (1).md` 참고).

## 실행 환경 / 명령어

- Python 3.12, 의존성은 `requirements.txt`로 관리 (`pip install -r requirements.txt`). 별도 lint/test 설정은 없음.
- 환경변수는 `.env`에서 로드 (`digger/config.py`, `python-dotenv`). `.env.example`을 복사해 `LASTFM_API_KEY`, `DISCOGS_TOKEN`, `MB_CONTACT`를 채워야 메타데이터 조회가 동작함.
- CLI 진입점: `python -m digger.cli`
  - `analyze <디렉토리> [--db digger.db]`: 디렉토리 내 오디오 파일(.flac/.mp3/.wav)을 Essentia로 분석해 `tracks` 테이블에 upsert.
  - `enrich [--db digger.db]`: DB에 있는 모든 트랙에 대해 Discogs → Last.fm → MusicBrainz 순으로 태그를 조회해 `track_tags`에 upsert. 소스 하나가 실패해도 나머지는 계속 진행됨(개별 try/except).
  - `import-liked [--db digger.db] [--max 2000]`: Spotify "좋아요" 곡을 `tracks`에 메타데이터만으로 적재(`spotify_track_id`가 식별자, bpm/key/energy는 NULL). 이어서 `enrich`를 태워야 태그가 채워져 탐색에 반영됨.
- API 서버: `uvicorn digger.api:app --reload` — CLI와 같은 SQLite DB(`digger.db`)를 그대로 쓰는 두 번째 인터페이스. `/docs`에서 전체 엔드포인트 확인 가능. `frontend/`가 같은 앱에 정적 파일로 마운트되어 있어서, 이 명령 하나로 `http://127.0.0.1:8000/`에서 UI+API가 함께 뜸(프론트엔드는 이제 이 서버가 떠 있어야 동작함 — mock-data.js 제거됨). UI의 '파이프라인' 탭에서 analyze/enrich/collect-relations/sync-listening/import-liked를 그대로 트리거할 수 있음 — 전부 동기 실행이라 브라우저가 끝날 때까지 기다리고, 한 번에 하나만 돌게 막아둠(외부 소스 rate limit이 모듈 전역이라 병렬 실행하면 정책을 어김). Spotify 최초 인증은 서버 콘솔에서 해야 함.
- DB 파일(`digger.db`)과 원본 음원(`music/`)은 `.gitignore`에 포함되어 커밋 대상이 아님.

## 아키텍처

두 단계 파이프라인: **분석(analyze) → 보강(enrich)**, 둘 다 같은 SQLite DB(`digger.db`)를 공유한다.

- `digger/analysis.py`: `analyze_track()`이 파일 태그(mutagen, 없으면 파일명 `아티스트 - 앨범 - 트랙제목`에서 유추)와 Essentia `MusicExtractor` 음향 특성(bpm/key/energy 등)을 합쳐 dict로 반환. 원본 `raw_features` 전체도 함께 저장해 나중에 필요한 특성을 다시 뽑을 수 있게 함.
- `digger/db.py`: SQLite 스키마와 upsert 함수. `tracks`(음향 특성)와 `track_tags`(외부 소스 태그, `UNIQUE(track_id, source, tag_type, raw_tag)`로 소스별 중복 방지)로 분리되어 있음. `tracks`에는 출처가 다른 두 종류가 섞여 있음 — 로컬 음원 분석분(`file_path` 기준)과 Spotify 좋아요 임포트분(`spotify_track_id` 기준, bpm/key/energy는 NULL). 유사도는 태그 벡터만 쓰기 때문에 둘이 같은 방식으로 탐색에 참여함. 컬럼 추가는 `CREATE TABLE IF NOT EXISTS` + `_migrate()`로 관리하고, 제약 변경은 SQLite 한계상 테이블을 새로 만들어 옮겨야 함(`_rebuild_tracks_for_non_local_sources` 참고 — id 보존이 핵심).
- `digger/metadata/`: 외부 메타데이터 소스별 클라이언트 (`discogs.py`, `lastfm.py`, `musicbrainz.py`). 각각 자체 rate limit을 모듈 전역 `_last_request_time`으로 구현하고 있음 (Discogs 1.1초, MusicBrainz 1초 — 정책상 필수). 새 소스를 추가할 때도 이 패턴을 따를 것.
  - Discogs는 릴리즈 검색 결과에 공식 `genre`/`style` 필드가 바로 포함되어 있어 크로스워크 없이 canonical 태그로 사용 가능. `artist`/`track` 필드로 엄격 검색하면 컴필레이션(릴리즈 아티스트가 "Various")을 놓치므로 통합 텍스트 쿼리(`q`)를 사용함.
  - Last.fm/MusicBrainz는 자유형(folksonomy) 태그라 `digger/crosswalk.py` + `digger/data/tag_crosswalk.yaml`로 canonical style에 정규화. 매핑이 없는 태그는 `canonical_style=NULL`로 정직하게 남겨두고, `enrich` 실행 결과를 보며 점진적으로 YAML을 채워나가는 방식(전체를 미리 큐레이션하지 않음).
- `digger/cli.py`: 위 모듈들을 엮는 argparse 기반 서브커맨드. 새 메타데이터 소스를 추가하려면 `_xxx_tags()` 헬퍼를 만들고 `enrich_tracks()`의 `(label, fetch)` 튜플 목록에 추가하면 됨.
- `digger/api.py`: CLI와 같은 SQLite DB를 그대로 쓰는 FastAPI 레이어. cli.py는 print 중심이라 그대로 재사용하지 않고 db.py/similarity.py/graph.py/boredom.py 등 저수준 함수를 직접 호출해 JSON으로 반환함(단, analyze/enrich/collect-relations/sync-listening 같은 배치 파이프라인은 예외적으로 cli.py 함수를 그대로 호출). CLI를 대체하는 게 아니라 나란히 쓰는 두 번째 인터페이스.

## 협업 워크플로 (필수 준수)

- 한국어로, 반말로 답변할 것.
- 작업을 수행하기 전 먼저 계획을 세우고, 사용자가 요청하지 않아도 알아서 계획을 세울 것.
- 계획의 기본 단위는 커밋 단위로 세울 것. 계획은 시행 전 무조건 사용자에게 검사를 받을 것.
- 세 개 이상의 커밋이 소요되는 작업 → `develop`에서 새 브랜치를 파서 작업.
- 1~2개 커밋이면 새 브랜치 없이 기존 `develop`에서 바로 작업.
- `main` 브랜치에는 절대 직접 커밋하지 말 것.
- 커밋 하나가 끝날 때마다 git commit + push까지 진행할 것. 커밋 메시지는 한국어로 작성.
