import os
from pathlib import Path
from typing import Optional

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

APP_SHARED_SECRET = os.getenv("APP_SHARED_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

TARGET_SYSTEM_PROMPTS = {
    "ru": "Translate to Russian.",
    "en": "Translate to English.",
    "es-latam": "Translate to Spanish (Latin America). Use LATAM slang.",
    "es-es": "Translate to Spanish (Spain). Use Spain vocabulary.",
    "pt-br": "Translate to Portuguese (Brazil).",
    "pt-pt": "Translate to Portuguese (Portugal).",
}

BASE_DIR = Path(__file__).resolve().parent
APP_HTML_PATH = BASE_DIR / "app.html"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _key_prefix(key: str) -> Optional[str]:
    if not key:
        return None
    return key[:8]


def require_app_key(x_app_key: Optional[str] = Header(None)) -> None:
    if not APP_SHARED_SECRET or not x_app_key or x_app_key != APP_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/debug/env")
def debug_env() -> dict:
    return {
        "ok": True,
        "openai_key_present": bool(OPENAI_API_KEY),
        "openai_key_prefix": _key_prefix(OPENAI_API_KEY),
    }


@app.post("/api/translate")
def translate(
    payload: dict,
    _: None = Depends(require_app_key),
) -> JSONResponse:
    text = (payload.get("text") or "").strip()
    target = (payload.get("target") or "").strip()

    if not text:
        return JSONResponse(status_code=400, content={"error": "Text is required"})

    if target not in TARGET_SYSTEM_PROMPTS:
        return JSONResponse(status_code=400, content={"error": "Unsupported target"})

    if not OPENAI_API_KEY:
        return JSONResponse(
            status_code=500, content={"error": "OPENAI_API_KEY is missing"}
        )

    system_prompt = TARGET_SYSTEM_PROMPTS[target]
    body = {
        "model": OPENAI_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        return JSONResponse(
            status_code=502,
            content={
                "error": "OpenAI error",
                "status": 0,
                "details": str(exc),
            },
        )

    if response.status_code != 200:
        details = response.text[:1000]
        return JSONResponse(
            status_code=502,
            content={
                "error": "OpenAI error",
                "status": response.status_code,
                "details": details,
            },
        )

    data = response.json()
    translated = ""
    try:
        translated = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        translated = ""

    return JSONResponse(status_code=200, content={"text": translated})


@app.get("/app", response_class=HTMLResponse)
def app_page() -> HTMLResponse:
    html = APP_HTML_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)
