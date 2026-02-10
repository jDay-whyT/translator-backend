import json
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", "whisper-1")


def _create_session() -> requests.Session:
    retry = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"POST"},
        backoff_factor=0.6,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


OPENAI_SESSION = _create_session()


def _parse_text(response: requests.Response) -> str:
    if response.status_code != 200:
        return ""
    try:
        data = response.json()
    except json.JSONDecodeError:
        return ""
    text = data.get("text")
    if not text:
        return ""
    return str(text).strip()


def transcribe(audio_bytes: bytes) -> str:
    if not OPENAI_API_KEY:
        return ""
    if not audio_bytes:
        return ""
    files = {
        "file": ("audio.ogg", audio_bytes, "audio/ogg"),
    }
    data = {
        "model": OPENAI_STT_MODEL,
        "prompt": (
            "Transcribe exactly. Language may be Russian, Spanish, or English. "
            "Do not add extra words. Do not translate."
        ),
        "temperature": 0,
    }
    try:
        response = OPENAI_SESSION.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files=files,
            data=data,
            timeout=(5, 30),
        )
    except requests.RequestException:
        return ""
    return _parse_text(response)
