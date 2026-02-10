import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# Set environment variables before importing
os.environ["TG_WEBHOOK_SECRET"] = "test_secret_token_for_testing_purposes"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
os.environ["OPENAI_API_KEY"] = "sk-test"
os.environ["DEEPL_API_KEY"] = "test-deepl-key"

# Mock telegram module before any imports
mock_telegram = MagicMock()
mock_telegram.Update = MagicMock()
mock_telegram.ext = MagicMock()
mock_telegram.ext.Application = MagicMock()
sys.modules['telegram'] = mock_telegram
sys.modules['telegram.ext'] = mock_telegram.ext

# Mock bot_handlers module
mock_bot_handlers = MagicMock()
mock_app_instance = MagicMock()
mock_app_instance.initialize = AsyncMock()
mock_app_instance.start = AsyncMock()
mock_app_instance.stop = AsyncMock()
mock_app_instance.shutdown = AsyncMock()
mock_app_instance.bot = MagicMock()
mock_bot_handlers.build_application = MagicMock(return_value=mock_app_instance)
sys.modules['bot_handlers'] = mock_bot_handlers

# Now safe to import
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_debug_env_endpoint(client):
    response = client.get("/debug/env")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    assert "openai_key_present" in data
    assert "openai_key_prefix" in data


def test_app_endpoint(client):
    response = client.get("/app")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_app_css_endpoint(client):
    response = client.get("/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_translate_without_auth(client):
    response = client.post(
        "/api/translate",
        json={"text": "hello", "target": "ru"}
    )
    assert response.status_code == 401


def test_translate_with_auth_missing_text(client):
    response = client.post(
        "/api/translate",
        json={"target": "ru"},
        headers={"X-TG-INITDATA": "user=%7B%22id%22%3A123%2C%22username%22%3A%22testuser%22%7D"}
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_translate_with_auth_text_too_long(client):
    long_text = "a" * 10001
    response = client.post(
        "/api/translate",
        json={"text": long_text, "target": "ru"},
        headers={"X-TG-INITDATA": "user=%7B%22id%22%3A123%2C%22username%22%3A%22testuser%22%7D"}
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_translate_with_unsupported_target(client):
    response = client.post(
        "/api/translate",
        json={"text": "hello", "target": "unsupported"},
        headers={"X-TG-INITDATA": "user=%7B%22id%22%3A123%2C%22username%22%3A%22testuser%22%7D"}
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_telegram_webhook_without_secret(client):
    response = client.post(
        "/tg/webhook",
        json={"update_id": 123},
    )
    assert response.status_code == 401


def test_telegram_webhook_with_wrong_secret(client):
    response = client.post(
        "/tg/webhook",
        json={"update_id": 123},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}
    )
    assert response.status_code == 401
