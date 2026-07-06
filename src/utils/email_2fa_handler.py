"""IMAP-based 2FA code capture for portals that send verification codes
via email.

Polls the INBOX every 3 seconds looking for unseen messages whose subject
contains "código" (or a configurable keyword).  Extracts a 6-digit numeric
code via regex.
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import os
import re
import time
from typing import ClassVar

from src.utils.logger import get_logger

logger = get_logger(__name__)


class Email2FAHandler:
    """Stateless helper — call ``wait_for_code`` with an email address."""

    _CODE_RE: ClassVar[re.Pattern] = re.compile(r"\b(\d{4,8})\b")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    async def wait_for_code(
        cls,
        email_address: str,
        *,
        timeout: int = 120,
        poll_interval: float = 3.0,
        subject_keyword: str = "código",
        imap_host: str = "imap.gmail.com",
        imap_port: int = 993,
    ) -> str:
        """Block until a 2FA code arrives or *timeout* seconds elapse.

        Returns the extracted numeric code as a string.

        Raises ``TimeoutError`` if no code is found within *timeout*.
        """
        password = os.getenv("EMAIL_APP_PASSWORD") or os.getenv("EMAIL_PASSWORD")
        if not password:
            raise ValueError(
                "EMAIL_APP_PASSWORD (or EMAIL_PASSWORD) environment variable is not set. "
                "For Gmail, generate an App Password at https://myaccount.google.com/apppasswords"
            )

        logger.info(
            "Waiting for 2FA code from %s (timeout=%ds, poll=%.1fs)",
            email_address,
            timeout,
            poll_interval,
        )

        loop = asyncio.get_running_loop()

        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        try:
            mail.login(email_address, password)
            mail.select("inbox")

            start = time.monotonic()

            while (time.monotonic() - start) < timeout:
                code = await loop.run_in_executor(
                    None, cls._scan_inbox, mail, subject_keyword
                )
                if code is not None:
                    logger.info("2FA code captured (%d chars)", len(code))
                    return code

                await asyncio.sleep(poll_interval)

            raise TimeoutError(
                f"2FA code not found after {timeout}s for {email_address}"
            )

        finally:
            try:
                mail.logout()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _scan_inbox(
        cls, mail: imaplib.IMAP4_SSL, subject_keyword: str
    ) -> str | None:
        """Scan unseen messages for a 2FA code.  Called in executor thread."""
        search_criteria = f'(UNSEEN SUBJECT "{subject_keyword}")'

        status, messages = mail.search(None, search_criteria)
        if status != "OK" or not messages[0]:
            return None

        for num in messages[0].split():
            status, data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(data[0][1])  # type: ignore[index]

            # Walk all text parts
            body_parts: list[str] = []
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype in ("text/plain", "text/html"):
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_parts.append(
                                payload.decode("utf-8", errors="replace")
                            )
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_parts.append(payload.decode("utf-8", errors="replace"))

            full_text = " ".join(body_parts)
            match = cls._CODE_RE.search(full_text)
            if match:
                return match.group(1)

        return None
