"""Credential resolution with fallback chain.

Priority:
1. Windows Credential Manager (via ``keyring``) — recommended for production.
2. Environment variables (``.env`` via ``python-dotenv``) — fallback / local dev.

Secret references are passed as ``"VAULT:<name>"`` or bare ``"<name>"``.
The ``VAULT:`` prefix is optional — the vault tries keyring first, then
``os.getenv``.
"""

from __future__ import annotations

import os
import sys
from typing import ClassVar

from src.utils.logger import get_logger

logger = get_logger(__name__)


class CredentialVault:
    """Static helper — never instantiated."""

    _keyring_available: ClassVar[bool | None] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def get_secret(cls, ref: str) -> str:
        """Resolve a secret reference to its plain-text value.

        ``ref`` may be a bare key name or prefixed with ``VAULT:``.
        Resolution order: keyring → os.environ → error.
        """
        key = ref.removeprefix("VAULT:").strip()

        # 1. Windows Credential Manager / macOS Keychain / Linux Secret Service
        if cls._keyring_available is None:
            cls._probe_keyring()

        if cls._keyring_available:
            try:
                import keyring

                value = keyring.get_password("rpa_core", key)
                if value:
                    logger.debug("Resolved %r via keyring", key)
                    return value
            except Exception as exc:
                logger.warning("keyring.get_password(%r) failed: %s", key, exc)

        # 2. Environment variable
        env_value = os.getenv(key)
        if env_value is not None:
            logger.debug("Resolved %r via environment", key)
            return env_value

        # 3. Not found
        raise KeyError(
            f"Secret {key!r} not found in keyring or environment variables. "
            f"Ensure it is stored in Windows Credential Manager (target=rpa_core, "
            f"username={key!r}) or exported as an env var."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _probe_keyring(cls) -> None:
        """Check whether keyring is importable and functional."""
        try:
            import keyring  # noqa: F401

            # Light smoke test — try listing backends (doesn't need creds)
            _ = keyring.get_keyring()
            cls._keyring_available = True
            logger.info("keyring backend available: %s", type(_).__name__)
        except ImportError:
            cls._keyring_available = False
            logger.info("keyring not installed — falling back to env vars")
        except Exception as exc:
            cls._keyring_available = False
            logger.warning("keyring probe failed (%s) — falling back to env vars", exc)
