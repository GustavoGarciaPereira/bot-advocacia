"""Extract text from PDF documents published by Official Gazettes (Diários
Oficiais / DJE).

Uses ``pdfplumber`` as primary engine (best table extraction) with
``PyPDF2`` as fallback for simple text-only PDFs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PDFParser:
    """Stateless parser — call ``extract`` with a file path."""

    # Common patterns in Brazilian judicial gazettes
    _PROCESSO_RE = re.compile(
        r"\b(\d{7}-?\d{2}\.?\d{4}\.?\d{1,3}\.?\d{2}\.?\d{4})\b"  # CNJ format
    )
    _ADVOGADO_RE = re.compile(
        r"(?:Advogad[oa]|Defensor[a]?|Procurador[a]?)\s*:\s*(.+?)(?:\n|$)",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def extract(cls, pdf_path: str | Path) -> list[dict[str, Any]]:
        """Parse a gazette PDF and return a list of raw intimation dicts.

        Each dict contains at minimum: ``texto``, ``pagina``, and any
        captured metadata (processo, advogado, etc.).
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        logger.info("Parsing PDF: %s", path.name)

        # Primary: pdfplumber (best for complex layouts)
        try:
            return cls._parse_with_pdfplumber(path)
        except ImportError:
            logger.debug("pdfplumber not available, trying PyPDF2")
        except Exception as exc:
            logger.warning("pdfplumber failed (%s), trying PyPDF2", exc)

        # Fallback: PyPDF2
        return cls._parse_with_pypdf2(path)

    # ------------------------------------------------------------------
    # Engines
    # ------------------------------------------------------------------

    @classmethod
    def _parse_with_pdfplumber(cls, path: Path) -> list[dict[str, Any]]:
        import pdfplumber

        records: list[dict[str, Any]] = []

        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if not text:
                    continue

                # Split into blocks separated by blank lines
                blocks = cls._split_into_blocks(text)

                for block in blocks:
                    if not cls._looks_like_intimation(block):
                        continue

                    records.append(
                        {
                            "texto": block.strip(),
                            "pagina": page_num,
                            "processo": cls._extract_processo(block),
                            "advogado_ref": cls._extract_advogado(block),
                        }
                    )

        logger.info("pdfplumber extracted %d records from %s", len(records), path.name)
        return records

    @classmethod
    def _parse_with_pypdf2(cls, path: Path) -> list[dict[str, Any]]:
        from PyPDF2 import PdfReader

        records: list[dict[str, Any]] = []
        reader = PdfReader(str(path))

        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if not text:
                continue

            blocks = cls._split_into_blocks(text)

            for block in blocks:
                if not cls._looks_like_intimation(block):
                    continue

                records.append(
                    {
                        "texto": block.strip(),
                        "pagina": page_num,
                        "processo": cls._extract_processo(block),
                        "advogado_ref": cls._extract_advogado(block),
                    }
                )

        logger.info("PyPDF2 extracted %d records from %s", len(records), path.name)
        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_into_blocks(text: str) -> list[str]:
        """Split page text into logical blocks (separated by ≥2 newlines)."""
        return re.split(r"\n{2,}", text)

    @staticmethod
    def _looks_like_intimation(block: str) -> bool:
        """Heuristic: does this block contain intimation-like keywords?"""
        keywords = [
            "intimação",
            "intimado",
            "citação",
            "notificação",
            "despacho",
            "prazo",
            "processo",
            "edital",
            "ciência",
        ]
        lowered = block.lower()
        return any(kw in lowered for kw in keywords)

    @classmethod
    def _extract_processo(cls, text: str) -> str | None:
        m = cls._PROCESSO_RE.search(text)
        return m.group(1) if m else None

    @classmethod
    def _extract_advogado(cls, text: str) -> str | None:
        m = cls._ADVOGADO_RE.search(text)
        return m.group(1).strip() if m else None
