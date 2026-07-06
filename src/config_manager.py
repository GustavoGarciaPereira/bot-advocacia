"""Load and cache client configuration from JSON files under ``src/configs/``.

Typical usage::

    config = ConfigManager.get_client_config("escritorio_alpha")
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from src.models import ClienteConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """Static helper that loads ``ClienteConfig`` with in-memory caching."""

    _cache: ClassVar[dict[str, ClienteConfig]] = {}

    @classmethod
    def get_client_config(
        cls, client_id: str, configs_dir: str = "src/configs"
    ) -> ClienteConfig:
        """Load (with caching) a client's configuration.

        Raises ``FileNotFoundError`` if the JSON file doesn't exist.
        Raises ``pydantic.ValidationError`` if the JSON is malformed.
        """
        if client_id in cls._cache:
            return cls._cache[client_id]

        path = Path(configs_dir) / f"{client_id}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Client config not found: {path}\n"
                f"Create a JSON file at src/configs/{client_id}.json "
                f"(see cliente_exemplo.json for the template)."
            )

        cfg = ClienteConfig.load(client_id, configs_dir=configs_dir)
        cls._cache[client_id] = cfg
        logger.info("Loaded config for client %r (%s)", client_id, cfg.nome_escritorio)
        return cfg

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()

    @classmethod
    def list_clients(cls, configs_dir: str = "src/configs") -> list[str]:
        """Return available client IDs by scanning the configs directory."""
        cfg_dir = Path(configs_dir)
        if not cfg_dir.exists():
            return []

        return sorted(
            p.stem
            for p in cfg_dir.glob("*.json")
            if not p.name.startswith(".") and not p.name.startswith("_")
        )
