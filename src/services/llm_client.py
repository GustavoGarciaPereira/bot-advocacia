"""Thin wrapper around LangChain + OpenAI / Azure OpenAI for classification.

Supports:
- OpenAI (default — ``OPENAI_API_KEY``)
- Azure OpenAI (when ``AZURE_OPENAI_API_KEY`` is set)
- Any LangChain-compatible chat model via ``ChatOpenAI`` base class.

The client is optional — if no API key is configured the orchestrator
skips AI classification and uses regex-only mode.
"""

from __future__ import annotations

import os
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Async wrapper around LangChain's ``ChatOpenAI``.

    Instantiate once and inject into ``HybridClassifier``.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: int = 64,
        **kwargs: Any,
    ) -> None:
        self._model_name = model_name
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._extra_kwargs = kwargs

        self._llm = self._build_llm()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(self, prompt: str) -> str:
        """Send *prompt* to the LLM and return the trimmed response text."""
        from langchain_core.messages import HumanMessage

        response = await self._llm.ainvoke([HumanMessage(content=prompt)])
        content: str = response.content  # type: ignore[assignment]
        return content.strip()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> LLMClient | None:
        """Create an ``LLMClient`` from environment variables.

        Returns ``None`` when no API key is configured (the caller should
        skip AI classification).
        """
        if os.getenv("AZURE_OPENAI_API_KEY"):
            return cls(
                model_name=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                openai_api_version=os.getenv(
                    "AZURE_OPENAI_API_VERSION", "2024-08-01-preview"
                ),
            )

        if os.getenv("OPENAI_API_KEY"):
            return cls(model_name=os.getenv("LLM_MODEL", "gpt-4o-mini"))

        logger.info("No LLM API key found — AI classification disabled")
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_llm(self) -> Any:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        # Azure path
        if os.getenv("AZURE_OPENAI_API_KEY"):
            kwargs["azure_endpoint"] = self._extra_kwargs.get("azure_endpoint") or os.getenv(
                "AZURE_OPENAI_ENDPOINT"
            )
            kwargs["openai_api_version"] = self._extra_kwargs.get(
                "openai_api_version"
            ) or os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            logger.info("LLM: Azure OpenAI (deployment=%s)", self._model_name)
        else:
            logger.info("LLM: OpenAI (model=%s)", self._model_name)

        kwargs.update(
            {k: v for k, v in self._extra_kwargs.items() if k not in kwargs}
        )

        return ChatOpenAI(**kwargs)
