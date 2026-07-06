#!/usr/bin/env python3
"""Quick smoke test for the DeepSeek (or OpenAI-compatible) LLM connection.

Usage::

    python test_deepseek.py

Prerequisites:
    - ``LLM_API_KEY`` (or ``OPENAI_API_KEY``) set in ``.env``.
    - ``langchain-openai`` installed (``pip install langchain-openai``).

Exit code 0 = success, 1 = failure.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    from src.services.llm_client import LLMClient

    print("🔍 Testando conexão com a LLM …")

    try:
        client = LLMClient.from_env()
    except ValueError as exc:
        print(f"❌ Configuração inválida: {exc}")
        sys.exit(1)

    if client is None:
        print("❌ Nenhuma API key configurada no .env")
        print("   Defina LLM_API_KEY ou OPENAI_API_KEY e tente novamente.")
        sys.exit(1)

    try:
        resposta = await client.generate("Responda APENAS com a palavra: OK")
        if "OK" in resposta.upper():
            print(f"✅ Conexão bem-sucedida! Resposta: {resposta}")
            sys.exit(0)
        else:
            print(f"⚠️  Resposta inesperada (esperado 'OK'): {resposta}")
            sys.exit(1)
    except Exception as exc:
        print(f"❌ Falha na chamada: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
