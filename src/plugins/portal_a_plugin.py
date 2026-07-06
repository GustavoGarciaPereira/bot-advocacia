"""Example portal plugin — State-level Judicial Portal (Portal A).

This is a **template** for portals like Tucujuris, E-SAJ, etc.
Replace the selectors marked with ``TODO`` with the actual DOM structure
of the target portal.

Key characteristics demonstrated:
- Login with username + password + optional 2FA via email.
- Navigation through menus to reach the intimation list.
- Table row extraction.
- "Tomar Ciência" / acknowledge action.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.base_selenium_plugin import SeleniumWaits, selenium_driver, retry_on_transient
from src.security.credential_vault import CredentialVault
from src.utils.email_2fa_handler import Email2FAHandler
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Selectors — update these for the real portal!
# ---------------------------------------------------------------------------

SELECTORS = {
    # Login page
    "login_url": "https://www.portal-exemplo-estadual.jus.br/login",
    "username_input": ("id", "usuario"),
    "password_input": ("id", "senha"),
    "login_button": ("id", "btn-entrar"),
    # 2FA
    "mfa_code_input": ("id", "codigo-autenticacao"),
    "mfa_validate_button": ("id", "btn-validar"),
    "mfa_skip_link": ("xpath", '//a[contains(text(),"Pular")]'),
    # Navigation
    "menu_intimacoes": ("xpath", '//a[contains(text(),"Intimações")]'),
    "submenu_pendentes": ("xpath", '//a[contains(text(),"Pendentes")]'),
    # Filters
    "filter_data_inicio": ("id", "data-inicio"),
    "filter_data_fim": ("id", "data-fim"),
    "filter_aplicar_button": ("id", "btn-filtrar"),
    # Results
    "result_table": ("xpath", '//table[@class="tabela-intimacoes"]'),
    "result_rows": ("xpath", './/tbody/tr'),
    "result_next_page": ("xpath", '//a[@class="proxima-pagina"]'),
    # Action
    "btn_tomar_ciencia": ("xpath", './/button[contains(text(),"Ciência")]'),
    "btn_ignorar": ("xpath", './/button[contains(text(),"Ignorar")]'),
    "confirm_modal_ok": ("xpath", '//div[@class="modal"]//button[text()="Sim"]'),
    # Post-action
    "success_toast": ("xpath", '//div[contains(@class,"alert-success")]'),
}


class PortalAPlugin(PortalPlugin):
    """State-level judicial portal plugin (template)."""

    @property
    def portal_type(self) -> PortalType:
        return PortalType.PORTAL_A

    @property
    def portal_name(self) -> str:
        return "Portal A (Estadual)"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self._headless = headless
        self._remote_url = remote_url
        self._driver = None
        self._wait: SeleniumWaits | None = None
        self._authenticated = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def authenticate(self, advogado: Advogado, config: dict[str, Any]) -> bool:
        """Log into the portal with username/password and optional 2FA."""
        async with selenium_driver(
            headless=self._headless, remote_url=self._remote_url
        ) as driver:
            self._driver = driver
            self._wait = SeleniumWaits(driver)

            # -- Login page ------------------------------------------------
            driver.get(SELECTORS["login_url"])
            self._wait.until_url_contains("login")

            self._wait.for_visible(*SELECTORS["username_input"]).send_keys(
                advogado.usuario or ""
            )

            senha = CredentialVault.get_secret(advogado.senha_ref)
            self._wait.for_visible(*SELECTORS["password_input"]).send_keys(senha)

            self._wait.for_clickable(*SELECTORS["login_button"]).click()

            # -- Optional 2FA ---------------------------------------------
            if advogado.email_2fa:
                try:
                    # Check if MFA page appeared
                    mfa_input = self._wait.for_present(
                        *SELECTORS["mfa_code_input"]
                    )
                    logger.info("2FA required for %s", advogado.nome)

                    codigo = await Email2FAHandler.wait_for_code(advogado.email_2fa)
                    mfa_input.send_keys(codigo)
                    self._wait.for_clickable(
                        *SELECTORS["mfa_validate_button"]
                    ).click()
                except Exception:
                    logger.warning("2FA page not detected or skipped")

            # -- Verify logged in -----------------------------------------
            self._wait.until_url_contains("home")
            self._authenticated = True
            logger.info("Authenticated: %s @ %s", advogado.nome, self.portal_name)

            return True

    @retry_on_transient
    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Navigate to the intimation list and extract raw rows."""
        assert self._driver is not None
        assert self._wait is not None

        raw_records: list[dict[str, Any]] = []

        # -- Navigate to intimation list ----------------------------------
        self._wait.for_clickable(*SELECTORS["menu_intimacoes"]).click()
        self._wait.for_clickable(*SELECTORS["submenu_pendentes"]).click()

        # -- Apply date filter (today) ------------------------------------
        self._wait.for_visible(*SELECTORS["filter_data_inicio"]).send_keys(
            data_referencia
        )
        self._wait.for_visible(*SELECTORS["filter_data_fim"]).send_keys(
            data_referencia
        )
        self._wait.for_clickable(*SELECTORS["filter_aplicar_button"]).click()

        # -- Paginate and extract -----------------------------------------
        while True:
            try:
                table = self._wait.for_present(*SELECTORS["result_table"])
            except Exception:
                logger.info("No results table found — probably zero intimations")
                break

            rows = table.find_elements(*SELECTORS["result_rows"])

            for row in rows:
                record = self._parse_row(row)
                if record:
                    raw_records.append(record)

            # Next page?
            try:
                next_btn = self._driver.find_element(*SELECTORS["result_next_page"])
                next_btn.click()
            except Exception:
                break

        logger.info(
            "Fetched %d raw intimations for %s", len(raw_records), advogado.nome
        )
        return raw_records

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        """Map raw row dict → canonical model."""
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
            raw_data=raw_data,
        )

    @retry_on_transient
    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        """Click 'Tomar Ciência' on a specific intimation row."""
        assert self._driver is not None
        assert self._wait is not None

        # Locate the row matching this record and click the action button
        btn = self._driver.find_element(*SELECTORS["btn_tomar_ciencia"])
        btn.click()

        # Confirm modal if present
        try:
            self._wait.for_clickable(*SELECTORS["confirm_modal_ok"]).click()
        except Exception:
            pass  # no modal — fine

        # Wait for success feedback
        self._wait.for_present(*SELECTORS["success_toast"])

        record.status_registro = "Sucesso"
        logger.debug("Acknowledged: proc=%s", record.numero_processo)

    async def cleanup(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
            self._wait = None

    # ------------------------------------------------------------------
    # Row parser (portal-specific)
    # ------------------------------------------------------------------

    def _parse_row(self, row: Any) -> dict[str, Any] | None:
        """Extract fields from a single ``<tr>`` element.

        Update this method to match the real portal's column layout.
        """
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
            }
        except Exception as exc:
            logger.warning("Failed to parse row: %s", exc)
            return None
