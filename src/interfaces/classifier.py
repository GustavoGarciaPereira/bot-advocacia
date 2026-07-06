"""Abstract contract for intimation classifiers.

The default implementation is `HybridClassifier` which runs regex rules
first (zero cost) and falls back to an LLM when configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import IntimacaoRecord


class Classifier(ABC):
    """Classify an `IntimacaoRecord` into a destination category.

    Returns ``(category_label, confidence)`` where confidence is in [0, 1].
    """

    @abstractmethod
    async def classify(self, record: IntimacaoRecord) -> tuple[str, float]:
        ...
