import json
import os
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from gpt_prompts import TARGET_PROMPTS
from translate_core import translate_core


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
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

    result = translate_core(text, target)
    status_code = result.pop("status_code", 200)
    result.pop("ok", None)
    return JSONResponse(status_code=status_code, content=result)


@app.get("/app", response_class=HTMLResponse)
def app_page() -> HTMLResponse:
    html = APP_HTML_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/app.css", response_class=Response)
def app_css() -> Response:
    css = APP_CSS_PATH.read_text(encoding="utf-8")
    return Response(content=css, media_type="text/css")
