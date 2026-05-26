"""
config.py
---------
Centralized configuration for BLEE Quant Pro Trader.

Loads settings from a local .env file (kept out of source control).
Copy .env.example to .env and fill in your Schwab API credentials.

Usage:
    from config import settings
    print(settings().API_KEY)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False


PROJECT_DIR = Path(__file__).resolve().parent
ENV_PATH = PROJECT_DIR / ".env"

if _DOTENV_AVAILABLE and ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill in your values."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    API_KEY: str
    APP_SECRET: str
    CALLBACK_URL: str
    ACCOUNT_NUMBER: str
    TOKEN_PATH: str
    TOKEN_PASSPHRASE: str
    AUTH_PORT: int
    PORTFOLIO_VALUE: float


def load_settings() -> Settings:
    return Settings(
        API_KEY=_require("SCHWAB_API_KEY"),
        APP_SECRET=_require("SCHWAB_APP_SECRET"),
        CALLBACK_URL=_optional("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"),
        ACCOUNT_NUMBER=_optional("SCHWAB_ACCOUNT_NUMBER", ""),
        TOKEN_PATH=str(PROJECT_DIR / _optional("SCHWAB_TOKEN_FILE", "schwab_token.enc")),
        TOKEN_PASSPHRASE=_require("SCHWAB_TOKEN_PASSPHRASE"),
        AUTH_PORT=int(_optional("SCHWAB_AUTH_PORT", "8182")),
        PORTFOLIO_VALUE=float(_optional("PORTFOLIO_VALUE", "10000.00")),
    )


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
