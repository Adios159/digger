"""환경변수(.env) 기반 설정 로더."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY", "")
DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
MB_CONTACT = os.environ.get("MB_CONTACT", "")
