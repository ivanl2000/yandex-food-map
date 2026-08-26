"""Configuration for Yandex Food Map server."""
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # Database
    db_path: str = field(
        default_factory=lambda: os.environ.get("YF_DB", "/opt/yandex_food/orders.db")
    )

    # Server
    host: str = field(
        default_factory=lambda: os.environ.get("YF_HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: int(os.environ.get("YF_PORT", "8081"))
    )

    # Search
    search_limit: int = field(
        default_factory=lambda: int(os.environ.get("YF_SEARCH_LIMIT", "200"))
    )
    min_query_length: int = field(
        default_factory=lambda: int(os.environ.get("YF_MIN_QUERY", "2"))
    )

    # Logging
    log_level: str = field(
        default_factory=lambda: os.environ.get("YF_LOG_LEVEL", "INFO")
    )


settings = Settings()