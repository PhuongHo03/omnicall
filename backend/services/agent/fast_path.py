"""Fast path handler for queries that don't require RAG retrieval.

Uses a single LLM call to detect whether a question needs meeting context
and, if not, generates a direct answer.  This replaces the previous
pattern-matching approach with semantic understanding.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.error import URLError

from backend.providers.llm_provider import LLMProvider, LLMProviderError

logger = logging.getLogger(__name__)

_FAST_PATH_TEMPERATURE = 0.5

_FAST_PATH_SYSTEM_PROMPT = (
    "You are a meeting intelligence assistant.  Determine whether the user's "
    "question requires meeting data or can be answered directly.\n\n"
    "Answer directly (needsRag=false) for:\n"
    "- Greetings, farewells, thanks, acknowledgments\n"
    "- Questions about who you are or what you can do\n"
    "- Usage guidance, example requests\n"
    "- Positive/negative feedback, small talk\n"
    "- Clarification requests\n"
    "- System commands (clear, reset, logout)\n"
    "- Questions completely unrelated to meetings (weather, code, math, recipes)\n\n"
    "Signal needsRag=true for ANY question that could benefit from meeting "
    "content — even vaguely meeting-related questions.\n\n"
    "Return JSON:\n"
    '{"needsRag": false, "answer": "Your helpful response here"}\n'
    "or\n"
    '{"needsRag": true}\n\n'
    "Rules:\n"
    "- Match the user's language (Vietnamese or English).\n"
    "- Keep direct answers concise and friendly.\n"
    "- When in doubt, set needsRag=true.\n"
)


@dataclass(frozen=True)
class FastPathResponse:
    """Response returned for a fast path query."""

    answer: str
    evidence_state: str = "fast_path"


class FastPathHandler:
    """Detects non-RAG questions and generates direct answers via LLM.

    Sends the question to the LLM with a system prompt that distinguishes
    between questions answerable without meeting context and questions
    that require retrieval.  Returns ``None`` when the question needs RAG.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def handle(self, query: str) -> FastPathResponse | None:
        """Handle a query if it does not require RAG retrieval.

        Parameters
        ----------
        query : str
            The user's question.

        Returns
        -------
        FastPathResponse or None
            A response when the question can be answered without meeting
            context, or ``None`` when RAG retrieval is needed.
        """
        try:
            response = self._llm.generate_json(
                system_prompt=_FAST_PATH_SYSTEM_PROMPT,
                user_prompt=query,
                temperature=_FAST_PATH_TEMPERATURE,
            )
        except (LLMProviderError, TimeoutError, json.JSONDecodeError, URLError, KeyError) as exc:
            logger.debug("fast_path.llm_failed error=%s — falling through to RAG", str(exc))
            return None
        except Exception as exc:
            logger.debug("fast_path.llm_failed unexpected error=%s — falling through to RAG", str(exc))
            return None

        needs_rag = response.get("needsRag", True)
        if needs_rag:
            return None

        answer = response.get("answer", "")
        if not isinstance(answer, str) or not answer.strip():
            return None

        return FastPathResponse(answer=answer.strip())
