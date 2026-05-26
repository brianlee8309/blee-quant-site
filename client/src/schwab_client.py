"""
schwab_client.py
----------------
One-stop factory for getting a fully-authenticated schwab-py client.

Use it like this everywhere else in the project:

    from schwab_client import get_client, get_account_hash
    client = get_client()
    print(client.get_quote("GLD").json())

Under the hood it:
  - loads credentials from .env via config.settings()
  - loads encrypted tokens via TokenManager
  - hands schwab-py our custom read/write functions so the saved token
    file stays encrypted at rest, even after schwab-py auto-refreshes
    the access token.

If no token file exists yet, it prints a clear instruction to run
auth_server.py instead of trying to open a browser from a headless
script - that keeps the trading scripts robust when run from a
scheduler.
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache

import schwab
from schwab.auth import client_from_access_functions

from config import settings
from token_manager import TokenManager

log = logging.getLogger(__name__)


def _build_token_manager() -> TokenManager:
    cfg = settings()
    return TokenManager(cfg.TOKEN_PATH, cfg.TOKEN_PASSPHRASE)


@lru_cache(maxsize=1)
def get_client():
    """Return an authenticated schwab-py Client (cached for the process)."""
    cfg = settings()
    tm = _build_token_manager()

    if not tm.has_token():
        msg = (
            "\nNo Schwab token found at " + cfg.TOKEN_PATH + ".\n"
            "Run the one-time login flow first:\n\n"
            "    python auth_server.py\n\n"
            "Click the 'Sign in with Schwab' button in your browser.\n"
        )
        print(msg, file=sys.stderr)
        raise FileNotFoundError(msg)

    read_func, write_func = tm.as_access_functions()

    client = client_from_access_functions(
        api_key=cfg.API_KEY,
        app_secret=cfg.APP_SECRET,
        token_read_func=read_func,
        token_write_func=write_func,
    )
    log.debug("Schwab client constructed.")
    return client


def get_account_hash(client=None, account_number: str | None = None) -> str:
    """Resolve an account number to the hash schwab-py needs for trade calls.

    If no account_number is passed, uses the one from .env.
    """
    cfg = settings()
    client = client or get_client()
    account_number = account_number or cfg.ACCOUNT_NUMBER
    if not account_number:
        raise ValueError(
            "No account number provided and SCHWAB_ACCOUNT_NUMBER not set in .env"
        )

    resp = client.get_account_numbers()
    resp.raise_for_status()
    for acct in resp.json():
        if acct.get("accountNumber") == account_number:
            return acct["hashValue"]
    raise ValueError(
        "Account " + account_number + " not found on this Schwab login. "
        "Check SCHWAB_ACCOUNT_NUMBER in .env."
    )


def token_status() -> str:
    """Human-friendly summary - useful for `python -m` style debugging."""
    tm = _build_token_manager()
    if not tm.has_token():
        return "No token on disk. Run `python auth_server.py`."
    age = tm.token_age_days()
    if age is None:
        return "Token exists but creation timestamp is missing."
    days_left = 7.0 - age
    return (
        "Token age: {:.2f} days. ".format(age) +
        ("Refresh expires in {:.2f} days.".format(days_left)
         if days_left > 0
         else "Refresh token has likely EXPIRED - re-run auth_server.py.")
    )


if __name__ == "__main__":
    # Quick CLI: `python schwab_client.py` prints token status.
    print(token_status())
