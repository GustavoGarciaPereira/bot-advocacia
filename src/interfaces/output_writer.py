"""Abstract contract for persisting intimation records.

The built-in implementation writes an Excel workbook via pandas/openpyxl.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import IntimacaoRecord


class OutputWriter(ABC):
    """Persist a collection of `IntimacaoRecord` and return the output path."""

    @abstractmethod
    async def write_records(
        self, records: list[IntimacaoRecord], client_id: str, data_ref: str
    ) -> str:
        ...
