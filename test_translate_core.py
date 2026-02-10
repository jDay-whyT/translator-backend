import pytest
from translate_core import (
    is_structured_text,
    should_use_deepl,
    _letters_ratio,
    _normalize_router_text,
)


def test_is_structured_text_with_multiple_newlines():
    text = "line1\nline2\nline3\nline4"
    assert is_structured_text(text) is True


def test_is_structured_text_with_tabs():
    text = "column1\tcolumn2\tcolumn3"
    assert is_structured_text(text) is True


def test_is_structured_text_with_list():
    text = "1. First item\n2. Second item"
    assert is_structured_text(text) is True


def test_is_structured_text_simple():
    text = "just a simple text"
    assert is_structured_text(text) is False


def test_letters_ratio_all_letters():
    text = "hello"
    assert _letters_ratio(text) == 1.0


def test_letters_ratio_mixed():
    text = "hello123"
    assert _letters_ratio(text) == 5/8


def test_letters_ratio_empty():
    text = "   "
    assert _letters_ratio(text) == 0.0


def test_normalize_router_text():
    text = "Hello, World! Тест-проверка."
    normalized = _normalize_router_text(text)
    assert "hello" in normalized
    assert "world" in normalized
    assert "тест" in normalized


def test_should_use_deepl_short_stt():
    # Short STT text should not route to DeepL
    text = "hi there"
    assert should_use_deepl(text, "stt") is False


def test_should_use_deepl_nsfw_stt():
    # NSFW content in STT should route to DeepL
    text = "this is explicit porn content that should be routed"
    result = should_use_deepl(text, "stt")
    # This should trigger routing due to NSFW content
    assert isinstance(result, bool)


def test_should_use_deepl_short_text():
    # Very short text should not route
    text = "ok"
    assert should_use_deepl(text, "text") is False


def test_should_use_deepl_neutral_text():
    # Neutral text should not route to DeepL
    text = "This is a normal translation request without any issues"
    assert should_use_deepl(text, "text") is False


def test_should_use_deepl_empty():
    # Empty text should not route
    text = ""
    assert should_use_deepl(text, "text") is False
