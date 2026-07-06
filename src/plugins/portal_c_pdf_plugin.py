"""Example plugin — PDF-based Official Gazette / DJE (Portal C).

This template handles portals where intimations are published as PDF
documents rather than interactive web pages.

Flow:
1. Navigate to the gazette download page.
2. Download today's PDF (or filter by date).
3. Parse the PDF with ``PDFParser``.
4. Cross-reference lawyer names to extract relevant records.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.base_selenium_plugin import SeleniumWaits, selenium_driver
from src.utils.logger import get_logger
from src.utils.pdf_parser import PDFParser

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

SELECTORS = {
    "gazette_url": "https://www.portal-exemplo-dje.jus.br/diario",
    "date_input": ("id", "data-edicao"),
    "download_button": ("id", "btn-baixar-pdf"),
    "download_link": ("xpath", '//a[contains(@href,".pdf")]'),
}


class PortalCPDFPlugin(PortalPlugin):
    """Official Gazette / DJE PDF portal plugin (template)."""

    @property
    def portal_type(self) -> PortalType:
        return PortalType.PORTAL_C

    @property
    def portal_name(self) -> str:
        return "Portal C (DJE PDF)"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self._headless = headless
        self._remote_url = remote_url
        self._driver = None
        self._wait: SeleniumWaits | None = None
        self._temp_dir: TemporaryDirectory | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def authenticate(self, advogado: Advogado, config: dict[str, Any]) -> bool:
        """No authentication needed for public gazettes (or simple captcha)."""
        # Many DJE portals are public — no login required.
        # Override if the target requires a login.
        logger.info("Portal C is public — no authentication required")

        self._driver = None  # driver will be created per-fetch
        return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Download and parse the PDF gazette for *data_referencia*."""
        raw_records: list[dict[str, Any]] = []

        self._temp_dir = TemporaryDirectory(prefix="rpa_dje_")

        async with selenium_driver(
            headless=self._headless, remote_url=self._remote_url
        ) as driver:
            self._driver = driver
            self._wait = SeleniumWaits(driver)

            # -- Navigate to gazette page --------------------------------
            driver.get(SELECTORS["gazette_url"])

            # -- Set date ------------------------------------------------
            date_input = self._wait.for_visible(*SELECTORS["date_input"])
            date_input.clear()
            date_input.send_keys(data_referencia)

            # -- Download PDF --------------------------------------------
            self._wait.for_clickable(*SELECTORS["download_button"]).click()

            # Wait for download link to appear and grab the href
            dl_link = self._wait.for_present(*SELECTORS["download_link"])
            pdf_url = dl_link.get_attribute("href")

            # Download via Selenium (navigate → save) or requests
            pdf_path = await self._download_pdf(pdf_url)

        # -- Parse -------------------------------------------------------
        if pdf_path:
            raw_records = PDFParser.extract(pdf_path)

        # -- Filter by lawyer name ---------------------------------------
        filtered: list[dict[str, Any]] = []
        nome_lower = advogado.nome.lower()
        for rec in raw_records:
            texto = rec.get("texto", "").lower()
            adv_ref = (rec.get("advogado_ref") or "").lower()

            if nome_lower in texto or nome_lower in adv_ref:
                filtered.append(rec)

        logger.info(
            "PDF: %d total blocks → %d matching %s",
            len(raw_records),
            len(filtered),
            advogado.nome,
        )
        return filtered

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name,
            advogado=advogado.nome,
            sequencia=str(raw_data.get("pagina", "")),
            numero_processo=raw_data.get("processo"),
            objeto_comunicacao=raw_data.get("texto"),
            raw_data=raw_data,
        )

    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        """PDF-based gazettes are read-only — no action to take."""
        record.status_registro = "Sucesso"
        logger.debug("PDF record noted (no action): proc=%s", record.numero_processo)

    async def cleanup(self) -> None:
        if self._temp_dir:
            try:
                self._temp_dir.cleanup()
            except Exception:
                pass
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
            self._wait = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _download_pdf(self, url: str) -> Path | None:
        """Download PDF to a temporary file and return its path."""
        assert self._temp_dir is not None

        import asyncio

        import requests

        loop = asyncio.get_running_loop()

        try:
            resp = await loop.run_in_executor(
                None, lambda: requests.get(url, timeout=60, stream=True)
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.error("PDF download failed: %s", exc)
            return None

        dest = Path(self._temp_dir.name) / "gazette.pdf"
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info("PDF downloaded: %s (%.1f KiB)", dest.name, dest.stat().st_size / 1024)
        return dest
