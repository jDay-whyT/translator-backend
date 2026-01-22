import json
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from gpt_prompts import BASE_SYSTEM_PROMPT, TARGET_PROMPTS


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")
TG_ALLOWED_USERNAMES = {
    value.strip().lower()
    for value in os.getenv("TG_ALLOWED_USERNAMES", "").split(",")
    if value.strip()
}

BASE_DIR = Path(__file__).resolve().parent
APP_HTML_PATH = BASE_DIR / "app.html"
APP_CSS_PATH = BASE_DIR / "app.css"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
DEEPL_SESSION = _create_session()

NSFW_PATTERN = re.compile(
    r"\b("
    r"sex|fuck\w*|blowjob|anal|porn\w*|nude\w*|pussy|dick|cock|cum"
    r"|секс|трах\w*|еб\w*|минет|анал|порн\w*"
    r"|sexo|follar\w*|mamada\w*|polla|coño|anal|porno"
    r"|sexo|foder\w*|boquete|buceta|pau|caralho|anal|porno"
    r")\b",
    re.IGNORECASE,
)

def _key_prefix(key: str) -> Optional[str]:
    if not key:
        return None
    return key[:8]


def _parse_username_from_init_data(init_data: str) -> Optional[str]:
    if not init_data:
        return None
    parsed = parse_qs(init_data, keep_blank_values=True)
    user_json = parsed.get("user", [""])[0]
    if not user_json:
        return None
    try:
        user = json.loads(user_json)
    except json.JSONDecodeError:
        return None
    username = user.get("username")
    if not username:
        return None
    return str(username)


def should_use_deepl(text: str) -> bool:
    if not text:
        return False
    return bool(NSFW_PATTERN.search(text))


def require_access(x_tg_initdata: Optional[str] = Header(None)) -> None:
    if not x_tg_initdata:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if TG_ALLOWED_USERNAMES:
        username = _parse_username_from_init_data(x_tg_initdata)
        if not username or username.lower() not in TG_ALLOWED_USERNAMES:
            raise HTTPException(status_code=403, detail="Forbidden")


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
    _: None = Depends(require_access),
) -> JSONResponse:
    text = (payload.get("text") or "").strip()
    target = (payload.get("target") or "").strip()

    if not text:
        return JSONResponse(status_code=400, content={"error": "Text is required"})

    if len(text) > 10000:
        return JSONResponse(status_code=400, content={"error": "Text is too long"})

    if target not in TARGET_PROMPTS:
        return JSONResponse(status_code=400, content={"error": "Unsupported target"})

    deepl_target = {
        "en": "EN",
        "ru": "RU",
        "es-es": "ES",
        "es-latam": "ES",
        "pt-br": "PT-BR",
        "pt-pt": "PT-PT",
    }.get(target)

    system_prompt = f"{BASE_SYSTEM_PROMPT}\n{TARGET_PROMPTS[target]}"
    body = {
        "model": OPENAI_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    }

    translated = ""
    openai_error = None
    finish_reason = None
    fallback_reason = None
    use_deepl_only = should_use_deepl(text)
    if use_deepl_only:
        fallback_reason = "nsfw_router"
    else:
        if not OPENAI_API_KEY:
            openai_error = {"status": 0, "details": "missing_api_key"}
        else:
            try:
                response = OPENAI_SESSION.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=(3, 20),
                )
                if response.status_code != 200:
                    openai_error = {
                        "status": response.status_code,
                        "details": response.text[:1000],
                    }
                else:
                    try:
                        data = response.json()
                    except json.JSONDecodeError:
                        openai_error = {"status": response.status_code, "details": "json"}
                    else:
                        if data.get("error"):
                            openai_error = {
                                "status": response.status_code,
                                "details": str(data.get("error")),
                            }
                        else:
                            try:
                                choice = data["choices"][0]
                                translated = choice["message"]["content"].strip()
                                finish_reason = choice.get("finish_reason")
                            except (KeyError, IndexError, TypeError):
                                translated = ""
                                finish_reason = None
                                openai_error = {
                                    "status": response.status_code,
                                    "details": "malformed response",
                                }
                            if finish_reason == "content_filter":
                                translated = ""
                            elif not translated:
                                fallback_reason = "empty"
            except requests.RequestException as exc:
                openai_error = {"status": 0, "details": str(exc)}

    if finish_reason == "content_filter":
        fallback_reason = "content_filter"
    elif translated:
        if len(text) > 80 and len(translated) < 12:
            fallback_reason = "too_short"
            translated = ""
        elif len(text) > 120 and len(translated) < int(len(text) * 0.08):
            fallback_reason = "too_short"
            translated = ""
        else:
            print("provider_used=openai fallback_reason=None")
            return JSONResponse(
                status_code=200,
                content={
                    "text": translated,
                    "translation": translated,
                    "provider": "openai",
                    "provider_used": "openai",
                    "fallback_reason": None,
                    "openai_finish_reason": finish_reason,
                },
            )

    if not translated and not fallback_reason:
        fallback_reason = "openai_error"

    if not translated:
        print(f"provider_used=deepl fallback_reason={fallback_reason}")

    if not DEEPL_API_KEY:
        return JSONResponse(
            status_code=502,
            content={
                "error": "DEEPL_API_KEY is missing",
                "status": (openai_error or {}).get("status", 0),
                "details": (openai_error or {}).get("details", ""),
            },
        )

    try:
        deepl_response = DEEPL_SESSION.post(
            "https://api-free.deepl.com/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
            data={"text": text, "target_lang": deepl_target},
            timeout=(3, 20),
        )
    except requests.RequestException as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "DeepL error", "status": 0, "details": str(exc)},
        )

    if deepl_response.status_code != 200:
        return JSONResponse(
            status_code=502,
            content={
                "error": "DeepL error",
                "status": deepl_response.status_code,
                "details": deepl_response.text[:1000],
            },
        )

    try:
        deepl_data = deepl_response.json()
        deepl_translated = deepl_data["translations"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        deepl_translated = ""

    if not deepl_translated:
        return JSONResponse(
            status_code=502,
            content={"error": "DeepL error", "status": deepl_response.status_code},
        )

    return JSONResponse(
        status_code=200,
        content={
            "text": deepl_translated,
            "translation": deepl_translated,
            "provider": "deepl",
            "provider_used": "deepl",
            "fallback_reason": fallback_reason,
            "openai_finish_reason": finish_reason,
        },
    )


@app.get("/app", response_class=HTMLResponse)
def app_page() -> HTMLResponse:
    html = APP_HTML_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/app.css", response_class=Response)
def app_css() -> Response:
    css = APP_CSS_PATH.read_text(encoding="utf-8")
    return Response(content=css, media_type="text/css")
