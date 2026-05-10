import asyncio
import hashlib
import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from telegram import Update
from telegram.ext import Application

from bot_handlers import build_application
from gpt_prompts import TARGET_PROMPTS
from translate_core import translate_core


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
INITDATA_MAX_AGE_SECONDS = int(os.getenv("INITDATA_MAX_AGE_SECONDS", "3600"))
TG_ALLOWED_USERNAMES = {
    value.strip().lower()
    for value in os.getenv("TG_ALLOWED_USERNAMES", "").split(",")
    if value.strip()
}

BASE_DIR = Path(__file__).resolve().parent
APP_HTML_PATH = BASE_DIR / "app.html"
APP_CSS_PATH = BASE_DIR / "app.css"

telegram_application: Optional[Application] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_application
    if not TG_WEBHOOK_SECRET:
        raise RuntimeError("TG_WEBHOOK_SECRET is missing")
    telegram_application = build_application()
    await telegram_application.initialize()
    await telegram_application.start()
    yield
    if telegram_application:
        await telegram_application.stop()
        await telegram_application.shutdown()


app = FastAPI(lifespan=lifespan)

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


def _verify_tg_initdata(init_data: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not init_data:
        return False
    received_hash = None
    auth_date = None
    check_pairs: list[str] = []
    for pair in init_data.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        if key == "hash":
            received_hash = value
        else:
            check_pairs.append(pair)
            if key == "auth_date":
                try:
                    auth_date = int(value)
                except ValueError:
                    return False
    if not received_hash or auth_date is None:
        return False
    if time.time() - auth_date > INITDATA_MAX_AGE_SECONDS:
        return False
    check_pairs.sort()
    data_check_string = "\n".join(check_pairs)
    secret_key = hmac.new(b"WebAppData", TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, received_hash)


def require_access(x_tg_initdata: Optional[str] = Header(None)) -> None:
    if not x_tg_initdata:
        raise HTTPException(status_code=401, detail="Unauthorized")
    print(f"initdata_raw={x_tg_initdata[:300]!r}", flush=True)
    if not _verify_tg_initdata(x_tg_initdata):
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
async def translate(
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

    result = await asyncio.to_thread(translate_core, text, target)
    status_code = result.pop("status_code", 200)
    result.pop("ok", None)
    return JSONResponse(status_code=status_code, content=result)


@app.post("/tg/webhook")
async def telegram_webhook(
    payload: dict,
    x_telegram_bot_api_secret_token: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> Response:
    if x_telegram_bot_api_secret_token != TG_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not telegram_application:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    update = Update.de_json(payload, telegram_application.bot)
    if update is None:
        return Response(status_code=200)
    asyncio.create_task(telegram_application.process_update(update))
    return Response(status_code=200)


@app.get("/app", response_class=HTMLResponse)
def app_page() -> HTMLResponse:
    html = APP_HTML_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/app.css", response_class=Response)
def app_css() -> Response:
    css = APP_CSS_PATH.read_text(encoding="utf-8")
    return Response(content=css, media_type="text/css")
