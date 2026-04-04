from __future__ import annotations

import os

import pytest

os.environ.setdefault("BACKUP_DIR", "./backups")
os.environ.setdefault("DEPLOY_HOST", "http://localhost:8000")
os.environ.setdefault("ADMIN_DEFAULT_EMAIL", "admin@company.local")

import api.chat as chat_module


class _FailingAssistant:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, *, message: str, system_data: dict):
        self.calls += 1
        raise RuntimeError("gemini down")


class _SuccessAssistant:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, *, message: str, system_data: dict):
        self.calls += 1
        return {"response": f"ok:{message}", "source": "gemini"}


@pytest.mark.asyncio
async def test_chat_impl_returns_fallback_when_ai_fails(monkeypatch):
    state = chat_module.ChatState()
    assistant = _FailingAssistant()
    monkeypatch.setattr(chat_module, "get_gemini_assistant", lambda: assistant)

    result = await chat_module._chat_impl("hello", state)

    assert result["source"] == "fallback"
    assert result["error"] == "AI unavailable"
    assert result["cache"] == "miss"


@pytest.mark.asyncio
async def test_chat_impl_does_not_cache_fallback(monkeypatch):
    state = chat_module.ChatState()
    assistant = _FailingAssistant()
    monkeypatch.setattr(chat_module, "get_gemini_assistant", lambda: assistant)

    first = await chat_module._chat_impl("hello", state)
    second = await chat_module._chat_impl("hello", state)

    assert first["source"] == "fallback"
    assert second["source"] == "fallback"
    assert assistant.calls == 2


@pytest.mark.asyncio
async def test_chat_impl_caches_successful_response(monkeypatch):
    state = chat_module.ChatState()
    assistant = _SuccessAssistant()
    monkeypatch.setattr(chat_module, "get_gemini_assistant", lambda: assistant)

    first = await chat_module._chat_impl("cached", state)
    second = await chat_module._chat_impl("cached", state)

    assert first["source"] == "gemini"
    assert first["cache"] == "miss"
    assert second["cache"] == "hit"
    assert assistant.calls == 1
