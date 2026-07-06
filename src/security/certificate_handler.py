"""Load and manage A1/A3 digital certificates (.pfx/.p12).

For Selenium-based portals the certificate is installed by configuring
the browser profile or clicking through the portal's certificate UI.
This module provides the low-level crypto primitives needed by plugins.
"""

from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path
from typing import ClassVar

from src.security.credential_vault import CredentialVault
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CertificateHandler:
    """Load a .pfx certificate and expose its components.

    Typical usage inside a plugin::

        cert = CertificateHandler.load("certs/advogado.pfx", password_ref="VAULT:CERT_PASSWORD")
        # Use cert.path for Selenium profile, cert.ssl_context for requests, etc.
    """

    def __init__(
        self, pfx_path: str, password: str, temp_dir: str | None = None
    ) -> None:
        self.pfx_path = Path(pfx_path).resolve()
        self._password = password
        self._temp_dir = temp_dir

        if not self.pfx_path.exists():
            raise FileNotFoundError(f"Certificate not found: {self.pfx_path}")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        pfx_path: str,
        password_ref: str | None = None,
        password: str | None = None,
    ) -> CertificateHandler:
        """Load a .pfx file.

        Password is resolved via *password_ref* (CredentialVault key) or
        supplied directly via *password*.
        """
        resolved = password or (
            CredentialVault.get_secret(password_ref) if password_ref else ""
        )
        return cls(pfx_path, resolved)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Absolute filesystem path to the .pfx file."""
        return self.pfx_path

    @property
    def password(self) -> str:
        """The resolved certificate password."""
        return self._password

    def create_ssl_context(self) -> ssl.SSLContext:
        """Return an ``ssl.SSLContext`` loaded with this certificate.

        Useful for ``requests`` or ``httpx`` sessions that require client
        certificate authentication.
        """
        ctx = ssl.create_default_context()
        ctx.load_cert_chain(
            str(self.pfx_path),
            password=self._password,
        )
        return ctx

    def extract_to_pem(self, output_dir: str | None = None) -> tuple[Path, Path]:
        """Extract cert + key to temporary PEM files.

        Returns ``(cert_pem_path, key_pem_path)``.
        Requires ``cryptography`` library.
        """
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            pkcs12,
        )

        p12_data = self.pfx_path.read_bytes()
        private_key, certificate, _ = pkcs12.load_key_and_certificates(
            p12_data, self._password.encode()
        )

        if private_key is None or certificate is None:
            raise ValueError("Failed to extract key/cert from .pfx")

        out = Path(output_dir or tempfile.mkdtemp(prefix="rpa_cert_"))

        cert_pem = out / "cert.pem"
        key_pem = out / "key.pem"

        cert_pem.write_bytes(certificate.public_bytes(Encoding.PEM))
        key_pem.write_bytes(
            private_key.private_bytes(
                Encoding.PEM,
                PrivateFormat.PKCS8,
                NoEncryption(),
            )
        )

        # Restrictive perms on the key file
        os.chmod(key_pem, 0o600)

        logger.debug("Extracted PEM files → %s", out)
        return cert_pem, key_pem
