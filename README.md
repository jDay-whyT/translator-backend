# Telegram Mini App Translator Backend (Cloud Run)

Simple FastAPI backend for a Telegram Mini App translator.

## Requirements
- Docker
- Google Cloud Run

## Environment Variables
- `OPENAI_API_KEY`: required — OpenAI key
- `OPENAI_MODEL`: optional — translation model (default: `gpt-4o-mini`)
- `OPENAI_STT_MODEL`: optional — speech-to-text model (default: `whisper-1`)
- `DEEPL_API_KEY`: required — DeepL fallback translation
- `TELEGRAM_BOT_TOKEN`: required — Telegram bot token; also used to verify Mini App `initData` HMAC
- `TG_WEBHOOK_SECRET`: required — random 32+ character secret for Telegram webhook
- `TG_ALLOWED_USERNAMES`: optional — CSV allowlist of Telegram usernames
- `INITDATA_MAX_AGE_SECONDS`: optional — max age of `auth_date` in `initData` (default: `3600`)
- `PORT`: Cloud Run provides this (default `8080`)

## Authorization
Every `/api/translate` request must include an `X-TG-INITDATA` header containing a valid
Telegram Mini App `initData` string. The backend verifies the HMAC-SHA256 signature using
`TELEGRAM_BOT_TOKEN` (per the [Telegram Mini App spec](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app))
and rejects tokens older than `INITDATA_MAX_AGE_SECONDS`.

- Missing or invalid signature → `401`
- Valid signature but username not in `TG_ALLOWED_USERNAMES` → `403`

## Build
docker build -t translator-backend .

## Run locally
docker run --rm -p 8080:8080 \
  -e OPENAI_API_KEY="your-openai-key" \
  -e OPENAI_MODEL="gpt-4o-mini" \
  -e DEEPL_API_KEY="your-deepl-key" \
  -e TG_ALLOWED_USERNAMES="alice,bob" \
  translator-backend

## Cloud Run: single service
Run FastAPI and the Telegram bot webhook in the same Cloud Run service:

Command:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```
Environment variables:
- OPENAI_API_KEY
- OPENAI_MODEL (optional)
- OPENAI_STT_MODEL (optional)
- DEEPL_API_KEY
- TG_ALLOWED_USERNAMES (optional)
- TELEGRAM_BOT_TOKEN
- TG_WEBHOOK_SECRET
- PORT (provided by Cloud Run)

## Endpoints
- GET /health
- GET /debug/env
- POST /api/translate
- GET /app

The Mini App frontend is served from `/app`.

## Telegram bot (webhook in same service)
- Cloud Run service must be **allow-unauthenticated** so Telegram can reach the webhook.
- Webhook URL: `https://<cloud-run-domain>/tg/webhook`
- The webhook requires `TG_WEBHOOK_SECRET` and expects header
  `X-Telegram-Bot-Api-Secret-Token` from Telegram.

PowerShell examples:
```powershell
$BOT_TOKEN="..."
$URL="https://<domain>/tg/webhook"
$SECRET="..."
irm "https://api.telegram.org/bot$BOT_TOKEN/setWebhook?url=$([uri]::EscapeDataString($URL))&secret_token=$SECRET"
irm "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
irm "https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
```

The bot checks `TG_ALLOWED_USERNAMES` against `message.from_user.username` and does not require `X-TG-INITDATA`.
