import json
import os
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gpt_prompts import BASE_SYSTEM_PROMPT, TARGET_PROMPTS


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")


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
    r"(?ix)"
    r"(?:^|[^\w])"
    r"("

    # ---------------- EN ----------------
    r"sex\b|sext\w*|sexchat\b|"
    r"porn\w*|xxx\b|onlyfans\b|"
    r"nude\w*|nsfw\b|"
    r"blow\s*job|blowjob\b|"
    r"hand\s*job|handjob\b|"
    r"anal\b|rimjob\b|"
    r"pussy\b|dick\b|cock\b|"
    r"cum\b|cumming\b|orgasm\w*|"
    r"dildo\b|"
    r"tits?\b|boobs?\b|breasts?\b|"

    # ---------------- RU ----------------
    r"|секс\w*|порно\w*|онлифанс\w*|"
    r"нюд\w*|nsfw\b|"
    r"анал\w*|минет\w*|оральн\w*|"
    r"дроч\w*|мастурб\w*|оргазм\w*|"
    r"пизд\w*|киск\w*|"
    r"хуй\w*|член\w*|пенис\w*|"
    r"сос\w*|"
    r"дилдо\w*|"
    r"сиськ\w*|титьк\w*|груд\w*|"
    r"конч\w*|"
    r"трах\w*|"

    # ---------------- ES ----------------
    r"|sexo\w*|porno\w*|nsfw\b|xxx\b|onlyfans\b|"
    r"desn?ud\w*|"
    r"mamada\w*|oral\b|"
    r"anal\b|"
    r"polla\w*|coñ\w*|"
    r"corrid\w*|venirse\b|orgasm\w*|"
    r"dildo\b|"
    r"tetas?\b|pechos?\b|"

    # ---------------- PT ----------------
    r"|sexo\w*|porno\w*|nsfw\b|xxx\b|onlyfans\b|"
    r"nua?\w*|pelad\w*|"
    r"boquete\w*|oral\b|"
    r"anal\b|"
    r"bucet\w*|pau\b|caralh\w*|"
    r"gozad\w*|goz\w*|orgasm\w*|"
    r"dildo\b|"
    r"tetas?\b|peitos?\b|seios?\b|"

    r")"
    r"(?:$|[^\w])"
)


def should_use_deepl(text: str) -> bool:
    if not text:
        return False
    return bool(NSFW_PATTERN.search(text))


def translate_core(text: str, target: str) -> dict:
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
            fallback_reason = "missing_openai_api_key"
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
                                openai_error = {
                                    "status": response.status_code,
                                    "details": "content_filter",
                                }
                                fallback_reason = "content_filter"
                            elif not translated:
                                fallback_reason = "empty"
            except requests.RequestException as exc:
                openai_error = {"status": 0, "details": str(exc)}

    if translated:
        if len(text) > 80 and len(translated) < 12:
            fallback_reason = "too_short"
            translated = ""
        elif len(text) > 120 and len(translated) < int(len(text) * 0.08):
            fallback_reason = "too_short"
            translated = ""
        else:
            print("provider_used=openai fallback_reason=None")
            return {
                "ok": True,
                "status_code": 200,
                "text": translated,
                "translation": translated,
                "provider": "openai",
                "provider_used": "openai",
                "fallback_reason": None,
                "openai_finish_reason": finish_reason,
            }

    if not translated and not fallback_reason:
        fallback_reason = "openai_error"

    if not translated:
        print(f"provider_used=deepl fallback_reason={fallback_reason}")

    if not DEEPL_API_KEY:
        return {
            "ok": False,
            "status_code": 502,
            "error": "DEEPL_API_KEY is missing",
            "status": (openai_error or {}).get("status", 0),
            "details": (openai_error or {}).get("details", ""),
            "provider_used": "deepl",
            "fallback_reason": fallback_reason,
            "openai_finish_reason": finish_reason,
        }

    try:
        deepl_response = DEEPL_SESSION.post(
            "https://api-free.deepl.com/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
            data={"text": text, "target_lang": deepl_target},
            timeout=(3, 20),
        )
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status_code": 502,
            "error": "DeepL error",
            "status": 0,
            "details": str(exc),
            "provider_used": "deepl",
            "fallback_reason": fallback_reason,
            "openai_finish_reason": finish_reason,
        }

    if deepl_response.status_code != 200:
        return {
            "ok": False,
            "status_code": 502,
            "error": "DeepL error",
            "status": deepl_response.status_code,
            "details": deepl_response.text[:1000],
            "provider_used": "deepl",
            "fallback_reason": fallback_reason,
            "openai_finish_reason": finish_reason,
        }

    try:
        deepl_data = deepl_response.json()
        deepl_translated = deepl_data["translations"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        deepl_translated = ""

    if not deepl_translated:
        return {
            "ok": False,
            "status_code": 502,
            "error": "DeepL error",
            "status": deepl_response.status_code,
            "provider_used": "deepl",
            "fallback_reason": fallback_reason,
            "openai_finish_reason": finish_reason,
        }

    return {
        "ok": True,
        "status_code": 200,
        "text": deepl_translated,
        "translation": deepl_translated,
        "provider": "deepl",
        "provider_used": "deepl",
        "fallback_reason": fallback_reason,
        "openai_finish_reason": finish_reason,
    }
