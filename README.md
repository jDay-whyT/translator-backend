# Telegram Mini App Translator Backend (Cloud Run)

Simple FastAPI backend for a Telegram Mini App translator.

## Requirements
- Docker
- Google Cloud Run

## Environment Variables
- APP_SHARED_SECRET: required shared secret for X-APP-KEY
- OPENAI_API_KEY: required OpenAI key
- OPENAI_MODEL: optional model name (default: gpt-4o-mini)
- PORT: Cloud Run provides this (default 8080)

## Build
docker build -t translator-backend .

## Run locally
docker run --rm -p 8080:8080 \
  -e APP_SHARED_SECRET="your-secret" \
  -e OPENAI_API_KEY="your-openai-key" \
  -e OPENAI_MODEL="gpt-4o-mini" \
  translator-backend

## Endpoints
- GET /health
- GET /debug/env
- POST /api/translate
- GET /app
