# Telegram Mini App Translator Backend (Cloud Run)

Simple FastAPI backend for a Telegram Mini App translator.

## Requirements
- Docker
- Google Cloud Run

## Environment Variables
- OPENAI_API_KEY: required OpenAI key
- OPENAI_MODEL: optional model name (default: gpt-4o-mini)
- TG_ALLOWED_USERNAMES: optional CSV allowlist of Telegram usernames
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
  -e TG_ALLOWED_USERNAMES="alice,bob" \
  translator-backend

## Endpoints
- GET /health
- GET /debug/env
- POST /api/translate
- GET /app

The Mini App frontend is served from `/app`.
