#!/usr/bin/env python3
"""
alert_sender.py
---------------
Sends daily allocation alerts to BLEE subscribers at 3:51 PM ET.

  Email  → SendGrid   (free up to 100/day)
  SMS    → Twilio     (~$0.008 per message)

Setup (one-time):
  pip install sendgrid twilio firebase-admin --break-system-packages

  1. SendGrid:
       https://app.sendgrid.com → Settings → API Keys → Create key (Full Access)
       Sender Authentication → verify your sender email

  2. Twilio:
       https://console.twilio.com → get Account SID + Auth Token
       Buy a phone number (~$1/mo) for sending SMS

  3. Firebase service account:
       console.firebase.google.com → Project Settings → Service accounts
       → Generate new private key → save as firebase-service-account.json
       in C:\\Kei\\ComposerInvest\\

  4. Fill in ALERT_CONFIG below (or use environment variables).

Runs automatically via run_alerts.bat → Windows Task Scheduler at 3:51 PM.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
SIGNAL_FILE  = SCRIPT_DIR / "signal_latest.json"
SERVICE_ACCT = SCRIPT_DIR / "firebase-service-account.json"
LOG_FILE     = SCRIPT_DIR / "alert_sender.log"

# ── Configuration (override with env vars) ─────────────────────────────────
ALERT_CONFIG = {
    # SendGrid
    "SENDGRID_API_KEY":    os.environ.get("SENDGRID_API_KEY",    "PASTE_YOUR_SENDGRID_KEY"),
    "FROM_EMAIL":          os.environ.get("BLEE_FROM_EMAIL",     "alerts@yourdomain.com"),
    "FROM_NAME":           os.environ.get("BLEE_FROM_NAME",      "BLEE Quant Analytics"),

    # Twilio
    "TWILIO_ACCOUNT_SID":  os.environ.get("TWILIO_ACCOUNT_SID",  "PASTE_YOUR_TWILIO_SID"),
    "TWILIO_AUTH_TOKEN":   os.environ.get("TWILIO_AUTH_TOKEN",   "PASTE_YOUR_TWILIO_TOKEN"),
    "TWILIO_FROM_NUMBER":  os.environ.get("TWILIO_FROM_NUMBER",  "+1XXXXXXXXXX"),

    # Who gets alerts: "premium" = only Pro, "basic" = all paid members
    "ALERT_TIER":          os.environ.get("BLEE_ALERT_TIER",     "premium"),
}

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("alert_sender")


# ═══════════════════════════════════════════════════════════════════════════
# Signal loader
# ═══════════════════════════════════════════════════════════════════════════

def load_signal() -> dict:
    if not SIGNAL_FILE.exists():
        raise FileNotFoundError(f"signal_latest.json not found at {SIGNAL_FILE}")
    with SIGNAL_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def format_signal_text(signal: dict) -> tuple[str, str]:
    """Return (subject, plain_text_body) for the alert email/SMS."""
    date      = signal.get("date", "today")
    symphony  = signal.get("symphony_name", "BLEE Symphony")
    positions = signal.get("positions", [])

    lines = [f"  {p['ticker']:<8} {p['weight_pct']:.2f}%" for p in positions]
    alloc_text = "\n".join(lines) if lines else "  (no positions)"

    subject = f"📊 BLEE Daily Signal — {date}"

    body = f"""BLEE Quant Analytics — Daily Allocation Signal
{'='*48}
Date      : {date}
Symphony  : {symphony}
{'─'*48}
TODAY'S ALLOCATION:
{alloc_text}
{'─'*48}
Action: Review your positions and rebalance if needed.
Pro members: BLEETrader will auto-execute at 3:52 PM ET.

View full signal → https://brianlee8309.github.io/blee-quant-site/index2.html
Manage account  → https://brianlee8309.github.io/blee-quant-site/subscribe.html

BLEE Quant Analytics | Unsubscribe via your member portal
"""
    return subject, body


def format_sms(signal: dict) -> str:
    date      = signal.get("date", "today")
    positions = signal.get("positions", [])
    top       = [f"{p['ticker']} {p['weight_pct']:.1f}%" for p in positions[:4]]
    alloc     = " | ".join(top)
    return (f"BLEE Signal {date}: {alloc}. "
            f"Pro: auto-trade fires at 3:52 PM ET. "
            f"View: brianlee8309.github.io/blee-quant-site/index2.html")


# ═══════════════════════════════════════════════════════════════════════════
# Subscriber loader (Firebase Firestore)
# ═══════════════════════════════════════════════════════════════════════════

def get_subscribers(required_tier: str) -> list[dict]:
    """
    Fetch subscribers from Firebase Firestore.
    Returns list of {email, phone, tier} dicts.
    """
    if not SERVICE_ACCT.exists():
        log.warning("firebase-service-account.json not found — using empty subscriber list.")
        log.warning("Download from Firebase Console → Project Settings → Service accounts.")
        return []

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore as fs

        if not firebase_admin._apps:
            cred = credentials.Certificate(str(SERVICE_ACCT))
            firebase_admin.initialize_app(cred)

        db   = fs.client()
        tier_map = {"basic": ["basic", "premium"], "premium": ["premium"]}
        allowed  = tier_map.get(required_tier, ["premium"])

        subs = []
        for tier_val in allowed:
            docs = (db.collection("users")
                      .where("tier", "==", tier_val)
                      .where("subscriptionStatus", "==", "active")
                      .stream())
            for doc in docs:
                d = doc.to_dict()
                subs.append({
                    "email": d.get("email", ""),
                    "phone": d.get("phone", ""),
                    "tier":  d.get("tier", ""),
                    "name":  d.get("displayName", ""),
                })
        # Deduplicate
        seen  = set()
        dedup = []
        for s in subs:
            if s["email"] and s["email"] not in seen:
                seen.add(s["email"])
                dedup.append(s)
        log.info("Loaded %d active subscriber(s) (tier filter: %s)", len(dedup), required_tier)
        return dedup

    except ImportError:
        log.error("firebase-admin not installed. Run: pip install firebase-admin --break-system-packages")
        return []
    except Exception as e:
        log.error("Failed to load subscribers: %s", e)
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Email sender (SendGrid)
# ═══════════════════════════════════════════════════════════════════════════

def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg  = sendgrid.SendGridAPIClient(api_key=ALERT_CONFIG["SENDGRID_API_KEY"])
        msg = Mail(
            from_email   =(ALERT_CONFIG["FROM_EMAIL"], ALERT_CONFIG["FROM_NAME"]),
            to_emails    = to_email,
            subject      = subject,
            plain_text_content = body,
        )
        resp = sg.send(msg)
        if resp.status_code in (200, 201, 202):
            log.info("  ✓ Email → %s", to_email)
            return True
        else:
            log.warning("  ✗ Email → %s  status=%d", to_email, resp.status_code)
            return False
    except ImportError:
        log.error("sendgrid not installed. Run: pip install sendgrid --break-system-packages")
        return False
    except Exception as e:
        log.error("  ✗ Email → %s  error=%s", to_email, e)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# SMS sender (Twilio)
# ═══════════════════════════════════════════════════════════════════════════

def send_sms(to_phone: str, body: str) -> bool:
    if not to_phone or not to_phone.startswith("+"):
        return False
    try:
        from twilio.rest import Client

        client = Client(ALERT_CONFIG["TWILIO_ACCOUNT_SID"],
                        ALERT_CONFIG["TWILIO_AUTH_TOKEN"])
        msg = client.messages.create(
            body = body,
            from_= ALERT_CONFIG["TWILIO_FROM_NUMBER"],
            to   = to_phone,
        )
        log.info("  ✓ SMS → %s  sid=%s", to_phone, msg.sid)
        return True
    except ImportError:
        log.error("twilio not installed. Run: pip install twilio --break-system-packages")
        return False
    except Exception as e:
        log.error("  ✗ SMS → %s  error=%s", to_phone, e)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    log.info("=" * 60)
    log.info("BLEE Alert Sender — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # ── Load signal ────────────────────────────────────────────────────────
    try:
        signal = load_signal()
        log.info("Signal: date=%s  positions=%d",
                 signal.get("date"), len(signal.get("positions", [])))
    except Exception as e:
        log.error("Cannot load signal: %s", e)
        return 1

    subject, email_body = format_signal_text(signal)
    sms_body            = format_sms(signal)

    # ── Load subscribers ───────────────────────────────────────────────────
    alert_tier  = ALERT_CONFIG["ALERT_TIER"]
    subscribers = get_subscribers(alert_tier)

    if not subscribers:
        log.warning("No subscribers found — nothing to send.")
        return 0

    # ── Send alerts ────────────────────────────────────────────────────────
    email_ok = email_fail = sms_ok = sms_fail = 0

    for sub in subscribers:
        # Email
        if sub.get("email"):
            if send_email(sub["email"], subject, email_body):
                email_ok += 1
            else:
                email_fail += 1

        # SMS (Pro only)
        if sub.get("tier") == "premium" and sub.get("phone"):
            if send_sms(sub["phone"], sms_body):
                sms_ok += 1
            else:
                sms_fail += 1

    log.info("")
    log.info("═" * 60)
    log.info("DONE  Email: ✓%d ✗%d  |  SMS: ✓%d ✗%d",
             email_ok, email_fail, sms_ok, sms_fail)
    log.info("Log: %s", LOG_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
