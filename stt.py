import json
import os

import requests

from http_session import create_session


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", "whisper-1")

OPENAI_SESSION = create_session()


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
