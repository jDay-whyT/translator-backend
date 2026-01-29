# Telegram Mini App Translator Backend (Cloud Run)

Simple FastAPI backend for a Telegram Mini App translator.

## Requirements
- Docker
- Google Cloud Run

## Environment Variables
- OPENAI_API_KEY: required OpenAI key
- OPENAI_MODEL: optional model name (default: gpt-4o-mini)
- OPENAI_STT_MODEL: optional model name for speech-to-text (default: gpt-4o-mini-transcribe)
- DEEPL_API_KEY: required for DeepL fallback and NSFW routing
- TG_ALLOWED_USERNAMES: optional CSV allowlist of Telegram usernames
- TELEGRAM_BOT_TOKEN: required to run the Telegram bot service
- PORT: Cloud Run provides this (default 8080)

## Authorization
- Client must send `X-TG-INITDATA` header; otherwise the API returns `401`.
- If `TG_ALLOWED_USERNAMES` is set, the API returns `403` when the Telegram username
  is not in the allowlist.

## Build
docker build -t translator-backend .

## Run locally
docker run --rm -p 8080:8080 \
  -e OPENAI_API_KEY="your-openai-key" \
  -e OPENAI_MODEL="gpt-4o-mini" \
  -e DEEPL_API_KEY="your-deepl-key" \
  -e TG_ALLOWED_USERNAMES="alice,bob" \
  translator-backend

## Cloud Run: separate services
Deploy two Cloud Run services from the same repo/image:

### Service: miniapp (FastAPI)
Command:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```
Environment variables:
- OPENAI_API_KEY
- OPENAI_MODEL (optional)
- DEEPL_API_KEY
- TG_ALLOWED_USERNAMES (optional)
- PORT (provided by Cloud Run)

### Service: bot (polling)
Command:
```bash
python bot_chat.py
```
Environment variables:
- TELEGRAM_BOT_TOKEN
- OPENAI_API_KEY
- OPENAI_MODEL (optional)
- OPENAI_STT_MODEL (optional)
- DEEPL_API_KEY
- TG_ALLOWED_USERNAMES (optional)

## Endpoints
- GET /health
- GET /debug/env
- POST /api/translate
- GET /app

The Mini App frontend is served from `/app`.

## Bot (chat + voice)
Install dependencies and run the bot:

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your-bot-token"
export OPENAI_API_KEY="your-openai-key"
export DEEPL_API_KEY="your-deepl-key"
export TG_ALLOWED_USERNAMES="alice,bob"
python bot_chat.py
```

The bot checks `TG_ALLOWED_USERNAMES` against `message.from_user.username` and does not require `X-TG-INITDATA`.
