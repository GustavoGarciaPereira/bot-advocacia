"""Example portal plugin — CNJ / PJE-style Federal portal (Portal B).

This template handles portals that:
- Require a digital certificate (.pfx) for authentication.
- Use iframes to embed the list views.
- Have a two-step process: search → select → acknowledge.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.base_selenium_plugin import SeleniumWaits, selenium_driver
from src.security.certificate_handler import CertificateHandler
from src.security.credential_vault import CredentialVault
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Selectors — update for the real CNJ/PJE portal
# ---------------------------------------------------------------------------

SELECTORS = {
    "login_url": "https://www.portal-exemplo-cnj.jus.br/pje/login.seam",
    # Certificate
    "cert_button": ("id", "btn-certificado-digital"),
    # Dashboard
    "menu_intimacoes": ("xpath", '//a[contains(@title,"Intimações")]'),
    # Search
    "search_input": ("id", "frm:numeroProcesso"),
    "search_button": ("id", "frm:btnPesquisar"),
    # Results (inside iframe)
    "result_iframe": ("id", "iframe-processos"),
    "result_rows": ("xpath", './/tr[contains(@class,"rich-table-row")]'),
    # Action panel
    "btn_ciencia": ("id", "frm:btnCiencia"),
    "btn_confirmar": ("id", "frm:btnConfirmar"),
    # Pagination
    "next_page": ("xpath", '//a[contains(@class,"rich-datascr-button-next")]'),
}


class PortalBPlugin(PortalPlugin):
    """CNJ/PJE-style federal portal plugin (template)."""

    @property
    def portal_type(self) -> PortalType:
        return PortalType.PORTAL_B

    @property
    def portal_name(self) -> str:
        return "Portal B (PJE/CNJ)"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self._headless = headless
        self._remote_url = remote_url
        self._driver = None
        self._wait: SeleniumWaits | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def authenticate(self, advogado: Advogado, config: dict[str, Any]) -> bool:
        """Authenticate using digital certificate."""
        async with selenium_driver(
            headless=self._headless, remote_url=self._remote_url
        ) as driver:
            self._driver = driver
            self._wait = SeleniumWaits(driver)

            driver.get(SELECTORS["login_url"])

            # -- Certificate login ----------------------------------------
            if advogado.certificado_path:
                cert = CertificateHandler.load(
                    advogado.certificado_path,
                    password_ref=advogado.senha_ref,
                )
                logger.info(
                    "Certificate loaded: %s", advogado.certificado_path
                )

            # Click certificate button — browser prompts for cert selection
            self._wait.for_clickable(*SELECTORS["cert_button"]).click()

            # Wait for dashboard to appear
            self._wait.until_url_contains("dashboard")
            logger.info("Authenticated (cert): %s @ %s", advogado.nome, self.portal_name)

            return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Search and extract intimations from the PJE interface."""
        assert self._driver is not None
        assert self._wait is not None

        raw_records: list[dict[str, Any]] = []

        # Navigate to intimation panel
        self._wait.for_clickable(*SELECTORS["menu_intimacoes"]).click()

        # Switch to iframe if present
        try:
            iframe = self._wait.for_present(*SELECTORS["result_iframe"])
            self._driver.switch_to.frame(iframe)
        except Exception:
            pass  # no iframe

        # Paginate
        while True:
            rows = self._driver.find_elements(*SELECTORS["result_rows"])

            for row in rows:
                record = self._parse_row(row)
                if record:
                    raw_records.append(record)

            # Next page
            try:
                self._driver.find_element(*SELECTORS["next_page"]).click()
            except Exception:
                break

        self._driver.switch_to.default_content()

        logger.info(
            "Fetched %d raw intimations for %s", len(raw_records), advogado.nome
        )
        return raw_records

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name,
            advogado=advogado.nome,
            sequencia=raw_data.get("sequencia", ""),
            numero_processo=raw_data.get("numero_processo"),
            objeto_comunicacao=raw_data.get("objeto"),
            tipo_comunicacao=raw_data.get("tipo"),
            data_comunicacao=raw_data.get("data"),
            data_prazo_fatal=raw_data.get("prazo"),
            instancia=raw_data.get("instancia"),
            comarca=raw_data.get("comarca"),
            raw_data=raw_data,
        )

    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        assert self._driver is not None
        assert self._wait is not None

        # Open the process detail
        # (in PJE you typically need to enter the process first)
        self._wait.for_clickable(*SELECTORS["btn_ciencia"]).click()
        self._wait.for_clickable(*SELECTORS["btn_confirmar"]).click()

        record.status_registro = "Sucesso"
        logger.debug("Acknowledged (PJE): proc=%s", record.numero_processo)

    async def cleanup(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
            self._wait = None

    # ------------------------------------------------------------------
    # Row parser
    # ------------------------------------------------------------------

    def _parse_row(self, row: Any) -> dict[str, Any] | None:
        try:
            cells = row.find_elements("tag name", "td")
            if len(cells) < 3:
                return None

            return {
                "sequencia": cells[0].text.strip() if len(cells) > 0 else "",
                "numero_processo": cells[1].text.strip() if len(cells) > 1 else "",
                "objeto": cells[2].text.strip() if len(cells) > 2 else "",
                "tipo": cells[3].text.strip() if len(cells) > 3 else "",
                "data": cells[4].text.strip() if len(cells) > 4 else "",
                "prazo": cells[5].text.strip() if len(cells) > 5 else "",
                "instancia": cells[6].text.strip() if len(cells) > 6 else "",
                "comarca": cells[7].text.strip() if len(cells) > 7 else "",
            }
        except Exception as exc:
            logger.warning("Failed to parse row: %s", exc)
            return None
