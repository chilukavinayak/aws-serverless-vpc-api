"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    table_name: str
    project_name: str
    environment: str
    log_level: str
    allowed_vpc_cidr_prefix: str
    aws_region: str

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "prod"


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return value


def _present(name: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return os.environ[name]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        table_name=_required("TABLE_NAME"),
        project_name=_required("PROJECT_NAME"),
        environment=_required("ENVIRONMENT"),
        log_level=_required("LOG_LEVEL").upper(),
        allowed_vpc_cidr_prefix=_present("ALLOWED_VPC_CIDR_PREFIX"),
        aws_region=_required("AWS_REGION"),
    )


def reset_settings_cache() -> None:
    """Test-only hook."""
    get_settings.cache_clear()
