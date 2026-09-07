# Digger

내가 실제로 좋아하는 곡의 음향적·맥락적 특성을 분석해, 아직 모르는 인접곡/아티스트를 찾아주는 개인용 음악 디깅 도구.

## 왜 만들었나

Spotify Discover Weekly류 추천은 협업 필터링 기반이라 "이미 많이 들은 곡과 비슷한 대중적인 곡" 위주로 수렴하고, 왜 추천됐는지 설명도 없다. 게다가 2024년 11월 Spotify가 Audio Features/Recommendations API를 폐쇄하면서 외부 개발자는 이 데이터 계층에 아예 접근할 수 없게 됐다.

그래서 직접 확보한 음향 분석(Essentia)과 메타데이터(Discogs/Last.fm/MusicBrainz)를 조합해, "왜 이 곡을 추천했는지" 설명 가능한 콘텐츠 기반 디깅 로직을 만들었다.

## 디깅 축

- **음향/장르 기반**: 태그 벡터 기준 코사인 유사도로 인접곡 랭킹
- **관계 기반 (사람 축)**: 프로듀서·레이블·크레딧으로 연결된 곡/아티스트 탐색 (MusicBrainz + Discogs 크레딧)
- **청취 이력 기반 필터**: Spotify 재생 이력으로 "질림 스코어"를 계산해, 너무 자주 들은 곡·아티스트는 추천에서 하향/제외
- **결과 내보내기**: 탐색 결과를 Spotify 플레이리스트로 생성

자세한 배경과 전체 기획은 [`AI_음악_디깅_앱_기획서 (1).md`](<AI_음악_디깅_앱_기획서 (1).md>) 참고.

## 아키텍처

Python CLI 프로토타입에 FastAPI 레이어를 얹은 구조. CLI와 API 서버가 같은 SQLite DB(`digger.db`)를 공유하는 두 개의 나란한 인터페이스다. 데이터 규모가 커지면 PostgreSQL(+pgvector)로 옮겨갈 계획.

- `digger/analysis.py` — 파일 태그(mutagen) + Essentia 음향 분석(bpm/key/energy 등)을 합쳐 트랙 dict 생성
- `digger/db.py` — SQLite 스키마 및 upsert. `tracks`(음향 특성)와 `track_tags`(외부 소스 태그)로 분리
- `digger/metadata/` — Discogs/Last.fm/MusicBrainz/Spotify 클라이언트, 각자 rate limit 준수
- `digger/crosswalk.py` — Last.fm/MusicBrainz의 자유형 태그를 Discogs Genre/Style 체계로 정규화
- `digger/graph.py` — 프로듀서/레이블/크레딧 기반 관계 탐색
- `digger/boredom.py` — 청취 이력 기반 질림 스코어 계산
- `digger/cli.py` — 파이프라인을 엮는 CLI 서브커맨드
- `digger/api.py` — 같은 DB를 쓰는 FastAPI 레이어, `frontend/`를 정적 파일로 마운트

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env  # LASTFM_API_KEY, DISCOGS_TOKEN, MB_CONTACT, SPOTIFY_* 채우기
```

CLI:

```bash
python -m digger.cli analyze <디렉토리>     # 오디오 분석 → tracks 테이블 upsert
python -m digger.cli enrich                # Discogs → Last.fm → MusicBrainz 태그 조회
python -m digger.cli import-liked          # Spotify 좋아요 곡 메타데이터만 적재
```

API 서버 (프론트엔드 UI 포함):

```bash
uvicorn digger.api:app --reload
# http://127.0.0.1:8000/ 에서 UI+API 함께 실행
```

UI의 "파이프라인" 탭에서 analyze/enrich/collect-relations/sync-listening/import-liked를 직접 트리거할 수 있다.

## 현재 상태

기획서의 M1(음원 분석)~M9(FastAPI 이관) 마일스톤을 모두 마쳤고, 이후 태그 정규화 고도화·Discogs 크레딧 기반 관계 수집·프론트엔드 API 연동·피드백 기록·플레이리스트 내보내기까지 진행된 상태. 개인용 프로토타입이라 아직 실사용 데이터 규모는 작다.

## 참고

- 기획 배경, 데이터 전략, 마일스톤 전체: [`AI_음악_디깅_앱_기획서 (1).md`](<AI_음악_디깅_앱_기획서 (1).md>)
