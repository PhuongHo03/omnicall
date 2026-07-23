"""Resolve chat language from an explicit client locale or deployment default."""

from __future__ import annotations

from backend.configs.settings import Settings, get_settings


_SUPPORTED = frozenset({"en", "vi"})


class ChatLanguageService:
    """A locale boundary; it never infers language from question text."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def resolve(self, locale: str | None) -> str:
        candidate = (locale or self.settings.default_chat_language).strip().replace("_", "-").split("-", 1)[0].casefold()
        return candidate if candidate in _SUPPORTED else self.settings.default_chat_language
