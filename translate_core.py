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

LIST_LINE_PATTERN = re.compile(
    r"^\s*(\d+[\.\)]|[-•—*]|[A-Za-zА-Яа-я]\))\s+",
    re.MULTILINE,
)

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

THRESHOLD_STT = 3
STRONG_TERMS_STT = [
    # EN
    "porn*",
    "xxx",
    "onlyfans",
    "nude*",
    "nsfw",
    "blow job",
    "blowjob",
    "hand job",
    "handjob",
    "anal",
    "rimjob",
    "pussy",
    "dick",
    "cock",
    "cum",
    "cumming",
    "orgasm*",
    "dildo",
    "tits",
    "boobs",
    "breasts",
    # RU
    "порно*",
    "онлифанс",
    "нюд*",
    "анал*",
    "минет*",
    "оральн*",
    "дроч*",
    "мастурб*",
    "оргазм*",
    "пизд*",
    "киск*",
    "хуй*",
    "член*",
    "пенис*",
    "сос*",
    "дилдо*",
    "сиськ*",
    "титьк*",
    "груд*",
    "конч*",
    "трах*",
    # ES
    "porno*",
    "xxx",
    "onlyfans",
    "desnud*",
    "mamada",
    "anal",
    "polla*",
    "coñ*",
    "corrid*",
    "venirse",
    "orgasm*",
    "dildo",
    "tetas",
    "pechos",
    # PT
    "porno*",
    "xxx",
    "onlyfans",
    "nua*",
    "pelad*",
    "boquete",
    "anal",
    "bucet*",
    "pau",
    "caralh*",
    "gozad*",
    "goz*",
    "orgasm*",
    "dildo",
    "tetas",
    "peit*",
    "seio*",
]
WEAK_TERMS_STT = [
    # EN
    "sex",
    "sext*",
    "sexchat",
    "oral",
    # RU
    "секс",
    # ES
    "sexo*",
    "oral",
    # PT
    "sexo*",
    "oral",
]


def _normalize_router_text(text: str) -> str:
    normalized = text.lower().replace("ё", "е")
    return re.sub(r"[^\w\s]", " ", normalized)


def _letters_ratio(text: str) -> float:
    total = sum(1 for char in text if not char.isspace())
    if total == 0:
        return 0.0
    letters = sum(1 for char in text if char.isalpha())
    return letters / total


def _compile_term_pattern(term: str) -> re.Pattern:
    words = term.split()
    last_word = words[-1]
    has_wildcard = last_word.endswith("*")
    if has_wildcard:
        words[-1] = last_word[:-1]
    escaped_words = [re.escape(word) for word in words]
    pattern = r"\b" + r"\s+".join(escaped_words)
    if has_wildcard:
        pattern += r"\w*"
    pattern += r"\b"
    return re.compile(pattern, re.IGNORECASE)


STRONG_PATTERNS_STT = [(_term, _compile_term_pattern(_term)) for _term in STRONG_TERMS_STT]
WEAK_PATTERNS_STT = [(_term, _compile_term_pattern(_term)) for _term in WEAK_TERMS_STT]


def should_use_deepl(text: str, source: str) -> bool:
    if not text:
        return False
    if source == "stt":
        # self-check:
        # - "one two three" -> False (short transcript)
        # - neutral ES/PT/EN -> False unless 2+ confident matches
        # - explicit NSFW transcript -> True
        if len(text.strip()) < 20:
            if os.getenv("DEBUG_ROUTER") == "1":
                print(
                    f"router_source=stt router_score=0 router_threshold={THRESHOLD_STT} "
                    "router_hits=[] strong=[] weak=[]"
                )
            return False
        if _letters_ratio(text) < 0.4:
            if os.getenv("DEBUG_ROUTER") == "1":
                print(
                    f"router_source=stt router_score=0 router_threshold={THRESHOLD_STT} "
                    "router_hits=[] strong=[] weak=[]"
                )
            return False

        normalized = _normalize_router_text(text)
        strong_hits = []
        weak_hits = []
        matched_terms = []

        for term, pattern in STRONG_PATTERNS_STT:
            if pattern.search(normalized):
                strong_hits.append(term)
                matched_terms.append(term)

        for term, pattern in WEAK_PATTERNS_STT:
            if pattern.search(normalized):
                weak_hits.append(term)
                matched_terms.append(term)

        strong_hits = sorted(set(strong_hits))
        weak_hits = sorted(set(weak_hits))
        matched_terms = sorted(set(matched_terms))
        score = len(strong_hits) * 2 + len(weak_hits)

        should_route = score >= THRESHOLD_STT or (
            len(strong_hits) >= 1 and (len(strong_hits) + len(weak_hits)) >= 2
        )
        if should_route:
            print(
                "router_source=stt "
                f"router_score={score} router_threshold={THRESHOLD_STT} "
                f"router_hits={matched_terms} strong={strong_hits} weak={weak_hits}"
            )
        elif os.getenv("DEBUG_ROUTER") == "1":
            print(
                "router_source=stt "
                f"router_score={score} router_threshold={THRESHOLD_STT} "
                f"router_hits={matched_terms} strong={strong_hits} weak={weak_hits}"
            )
        return should_route
    return bool(NSFW_PATTERN.search(text))


def is_structured_text(text: str) -> bool:
    if text.count("\n") >= 3:
        return True
    if "\t" in text:
        return True
    return bool(LIST_LINE_PATTERN.search(text))


def _count_nonempty_lines(lines: list[str]) -> int:
    return sum(1 for line in lines if line.strip())


def deepl_translate(text: str, target_lang: str) -> dict:
    try:
        deepl_response = DEEPL_SESSION.post(
            "https://api-free.deepl.com/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
            data={
                "text": text,
                "target_lang": target_lang,
                "preserve_formatting": "1",
                "split_sentences": "nonewlines",
            },
            timeout=(3, 20),
        )
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status_code": 502,
            "error": "DeepL error",
            "status": 0,
            "details": str(exc),
        }

    if deepl_response.status_code != 200:
        return {
            "ok": False,
            "status_code": 502,
            "error": "DeepL error",
            "status": deepl_response.status_code,
            "details": deepl_response.text[:1000],
        }

    try:
        deepl_data = deepl_response.json()
        deepl_translated = deepl_data["translations"][0]["text"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        deepl_translated = ""

    if not deepl_translated:
        return {
            "ok": False,
            "status_code": 502,
            "error": "DeepL error",
            "status": deepl_response.status_code,
        }

    return {
        "ok": True,
        "status_code": 200,
        "text": deepl_translated,
    }


def deepl_translate_structured(text: str, target_lang: str) -> dict:
    lines = text.splitlines(keepends=False)
    translated_lines = []
    for line in lines:
        if not line.strip():
            translated_lines.append(line)
            continue
        result = deepl_translate(line, target_lang)
        if not result["ok"]:
            return result
        translated_lines.append(result["text"])

    return {
        "ok": True,
        "status_code": 200,
        "text": "\n".join(translated_lines),
    }


def translate_core(text: str, target: str, source: str = "text") -> dict:
    if target not in TARGET_PROMPTS:
        return {
            "ok": False,
            "status_code": 400,
            "error": "Unsupported target",
            "details": "unsupported_target",
            "provider_used": None,
        }
    deepl_target = {
        "en": "EN",
        "ru": "RU",
        "es-es": "ES",
        "es-latam": "ES",
        "pt-br": "PT-BR",
        "pt-pt": "PT-PT",
    }.get(target)
    if deepl_target is None:
        return {
            "ok": False,
            "status_code": 400,
            "error": "Unsupported target",
            "details": "unsupported_deepl_target",
            "provider_used": None,
        }

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
    use_deepl_only = should_use_deepl(text, source)
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

    lines = text.splitlines()
    nonempty_lines = _count_nonempty_lines(lines)
    use_structured = is_structured_text(text) and nonempty_lines <= 60
    if use_structured:
        deepl_result = deepl_translate_structured(text, deepl_target)
    else:
        deepl_result = deepl_translate(text, deepl_target)

    if not deepl_result["ok"]:
        return {
            "ok": False,
            "status_code": deepl_result.get("status_code", 502),
            "error": deepl_result.get("error", "DeepL error"),
            "status": deepl_result.get("status", 0),
            "details": deepl_result.get("details", ""),
            "provider_used": "deepl",
            "fallback_reason": fallback_reason,
            "openai_finish_reason": finish_reason,
        }

    deepl_translated = deepl_result["text"]

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
