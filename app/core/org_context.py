"""Request-scoped org context used by middleware and DB session setup."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

_current_org_id: ContextVar[Optional[str]] = ContextVar("current_org_id", default=None)


def set_current_org_id(org_id: Optional[str]) -> Token:
    return _current_org_id.set(org_id)


def get_current_org_id() -> Optional[str]:
    return _current_org_id.get()


def reset_current_org_id(token: Token) -> None:
    _current_org_id.reset(token)
