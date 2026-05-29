"""
composer_balance_live.py
------------------------
Polls Composer API every 5 minutes during market hours (Mon-Fri 9:30-16:00 ET)
and writes the total account balance to Firebase Firestore.

The CurrentWatchSymphony.html page listens to Firestore in real time and
updates the displayed total without a page reload.

Setup (one-time):
  1. In Firebase Console → Firestore → Rules, allow writes to /account/balance:
       match /account/balance {
         allow read: if true;
         allow write: if true;   // only your local machine writes here
       }
  2. Schedule this script with Windows Task Scheduler every 5 minutes:
       Action: python C:\\Kei\\ComposerInvest\\composer_balance_live.py

Run manually:
    python composer_balance_live.py
"""

from __future__ import annotations

import json
import sys
import time
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path

# ── Paths / constants ─────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "composer_config.json"
API_BASE    = "https://api.composer.trade"

# Firebase project info (from firebase-config.js)
FIREBASE_PROJECT = "blee-quant"
FIREBASE_API_KEY = "AIzaSyBRppmBgkdFUWx2raZi9K593843XaCxXso"
FIRESTORE_DOC    = f"projects/{FIREBASE_PROJECT}/databases/(default)/documents/account/balance"
FIRESTORE_URL    = (
    f"https://firestore.googleapis.com/v1/{FIRESTORE_DOC}"
    f"?key={FIREBASE_API_KEY}"
)

# ── Helpers ───────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def is_market_open() -> bool:
    """True if current time is Mon-Fri 09:30-16:00 US/Eastern."""
    import zoneinfo
    now_et = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:   # Saturday=5, Sunday=6
        return False
    t = now_et.time()
    return dt.time(9, 30) <= t < dt.time(16, 0)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log(f"ERROR: {CONFIG_PATH} not found")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    for k in ("api_key", "api_secret"):
        if not cfg.get(k):
            log(f"ERROR: '{k}' missing from composer_config.json")
            sys.exit(1)
    return cfg


def api_get(cfg: dict, path: str) -> dict | list:
    headers = {
        "x-api-key-id":  cfg["api_key"],
        "authorization": f"Bearer {cfg['api_secret']}",
        "Accept":        "application/json",
    }
    req = urllib.request.Request(
        f"{API_BASE}{path}", method="GET", headers=headers
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_account_total(cfg: dict) -> float | None:
    """
    Fetch /symphony-stats-meta for all accounts and sum every symphony's value.
    Falls back to /accounts/list to discover the account UUID if not in config.
    """
    account_uuid = cfg.get("account_uuid")
    if not account_uuid:
        try:
            accts = api_get(cfg, "/api/v0.1/accounts/list")
            if isinstance(accts, dict):
                for k in ("accounts", "data", "items"):
                    if isinstance(accts.get(k), list):
                        accts = accts[k]
                        break
                else:
                    accts = [accts] if "account_uuid" in accts else []
            account_uuid = (
                accts[0].get("account_uuid")
                or accts[0].get("uuid")
                or accts[0].get("id")
            ) if accts else None
        except Exception as e:
            log(f"Could not discover account UUID: {e}")
            return None

    if not account_uuid:
        log("No account_uuid found")
        return None

    path = f"/api/v0.1/portfolio/accounts/{account_uuid}/symphony-stats-meta"
    log(f"GET {path}")
    data = api_get(cfg, path)

    # Normalise to list of symphony entries
    if isinstance(data, dict):
        data = data.get("symphonies", [])
    if not isinstance(data, list):
        return None

    total = sum(
        float(s["value"])
        for s in data
        if isinstance(s.get("value"), (int, float)) and s["value"] > 0
    )
    return round(total, 2)


def write_to_firestore(total: float) -> bool:
    """
    PATCH the Firestore document account/balance with the new total.
    Requires the Firestore rule:
        match /account/balance { allow read, write: if true; }
    """
    now_iso = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "fields": {
            "total":      {"doubleValue": total},
            "updated_at": {"stringValue": now_iso},
        }
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        FIRESTORE_URL,
        data=body,
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="ignore")
        log(f"Firestore write failed (HTTP {e.code}): {body_txt[:300]}")
        if e.code == 403:
            log("  → Add this rule in Firebase Console → Firestore → Rules:")
            log('      match /account/balance { allow read, write: if true; }')
        return False
    except Exception as e:
        log(f"Firestore write error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    log("=== Composer Balance Live Updater ===")
    cfg = load_config()

    if not is_market_open():
        log("Market is closed — running once then exiting")
        # Still run once so the value is fresh when market opens
        try:
            total = fetch_account_total(cfg)
            if total is not None:
                ok = write_to_firestore(total)
                log(f"Balance: ${total:,.2f}  Firestore: {'OK' if ok else 'FAILED'}")
            else:
                log("Could not fetch balance")
        except Exception as e:
            log(f"Error: {e}")
        return

    log("Market open — polling every 5 minutes until close")
    INTERVAL = 5 * 60   # 5 minutes

    while is_market_open():
        try:
            total = fetch_account_total(cfg)
            if total is not None:
                ok = write_to_firestore(total)
                log(f"Balance: ${total:,.2f}  Firestore: {'OK' if ok else 'FAILED'}")
            else:
                log("Could not fetch balance — will retry next interval")
        except Exception as e:
            log(f"Error fetching balance: {e}")

        # Sleep in 30-second chunks so we can detect market close promptly
        for _ in range(INTERVAL // 30):
            if not is_market_open():
                break
            time.sleep(30)

    log("Market closed — exiting")


if __name__ == "__main__":
    main()
