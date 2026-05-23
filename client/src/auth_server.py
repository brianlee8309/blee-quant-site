"""
auth_server.py
--------------
Local HTTPS Flask app that handles the weekly Schwab re-authentication.

Run this once a week (or whenever your refresh token expires):

    python auth_server.py

It will:
  1. Start an HTTPS server on https://127.0.0.1:8182 (or whatever
     SCHWAB_AUTH_PORT is in your .env).
  2. Open your browser to a small landing page with a "Sign in with
     Schwab" button.
  3. After you click it and complete Schwab's 2FA, Schwab redirects
     back here with an authorization code.
  4. We exchange the code for access + refresh tokens, encrypt them via
     TokenManager, and save them to schwab_token.enc.
  5. Show a success page.  You can close the tab.

After that, your trading scripts will pick up the saved tokens
automatically until the 7-day refresh window expires.

Note: the browser will warn about the self-signed certificate.  That's
expected.  Click through ("Advanced" -> "Proceed").  This is purely
local - nothing leaves your machine over that connection.
"""

from __future__ import annotations

import base64
import logging
import secrets
import sys
import threading
import time
import webbrowser
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, session

from config import settings
from token_manager import TokenManager

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("auth_server")

# Schwab OAuth endpoints
SCHWAB_AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

cfg = settings()
tm = TokenManager(cfg.TOKEN_PATH, cfg.TOKEN_PASSPHRASE)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # ephemeral, lasts for this run only


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

LANDING_PAGE = """
<!doctype html>
<html><head>
  <title>Schwab Weekly Re-Auth</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; max-width: 540px;
           margin: 80px auto; padding: 0 24px; color: #222; }
    h1 { font-size: 22px; }
    p  { line-height: 1.55; color: #444; }
    a.button { display: inline-block; padding: 12px 22px; margin-top: 12px;
               background: #00a0df; color: white; text-decoration: none;
               border-radius: 6px; font-weight: 600; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
    .meta { color: #888; font-size: 13px; margin-top: 36px; }
  </style>
</head><body>
  <h1>Schwab Weekly Re-Auth</h1>
  <p>Click the button to sign in with Schwab. You'll be redirected to
  Schwab's login page, asked for your 2FA code, and then sent back here.
  Your new tokens will be saved (encrypted) and your trading scripts will
  work for the next 7 days.</p>
  <a class="button" href="/login">Sign in with Schwab &rarr;</a>
  <div class="meta">
    Token file: <code>{{TOKEN_PATH}}</code><br/>
    Current token age: {{AGE}}
  </div>
</body></html>
"""

SUCCESS_PAGE = """
<!doctype html>
<html><head>
  <title>Schwab Auth - Success</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; max-width: 540px;
           margin: 80px auto; padding: 0 24px; color: #222; }
    h1 { color: #1c7c3a; font-size: 22px; }
    p  { line-height: 1.55; color: #444; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
  </style>
</head><body>
  <h1>&#10003; Authenticated successfully</h1>
  <p>Your encrypted token has been saved to <code>{{TOKEN_PATH}}</code>.</p>
  <p>You can close this tab. Trading scripts will work for the next
  ~7 days.</p>
  <p>Stop the local server with <code>Ctrl+C</code> in the terminal when
  you're done.</p>
</body></html>
"""

ERROR_PAGE = """
<!doctype html>
<html><head>
  <title>Schwab Auth - Error</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; max-width: 540px;
           margin: 80px auto; padding: 0 24px; color: #222; }
    h1 { color: #b00020; font-size: 22px; }
    pre { background: #f4f4f4; padding: 12px; border-radius: 6px;
          white-space: pre-wrap; word-break: break-all; }
  </style>
</head><body>
  <h1>Authentication failed</h1>
  <pre>{{DETAIL}}</pre>
  <p><a href="/">Try again</a></p>
</body></html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _render(template: str, **subs: str) -> str:
    """Tiny .replace()-based templating so CSS curly braces don't break."""
    out = template
    for key, val in subs.items():
        out = out.replace("{{" + key + "}}", str(val))
    return out


@app.route("/")
def index():
    # If Schwab redirected back here with ?code=... (because the
    # registered callback URL has no path), dispatch to the same logic
    # as /callback.
    if request.args.get("code") or request.args.get("error"):
        return callback()

    age = tm.token_age_days()
    age_str = ("none on disk" if age is None
               else "{:.2f} days".format(age))
    return _render(LANDING_PAGE, TOKEN_PATH=cfg.TOKEN_PATH, AGE=age_str)


@app.route("/login")
def login():
    """Redirect the browser to Schwab's authorize endpoint."""
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    params = {
        "response_type": "code",
        "client_id":     cfg.API_KEY,
        "redirect_uri":  cfg.CALLBACK_URL,
        "state":         state,
    }
    url = SCHWAB_AUTHORIZE_URL + "?" + urlencode(params)
    log.info("Redirecting to Schwab authorize URL.")
    return redirect(url)


@app.route("/callback")
def callback():
    """Schwab redirects here after the user completes 2FA + consent."""
    error = request.args.get("error")
    if error:
        return _render(ERROR_PAGE,
            DETAIL="Schwab returned error: " + error +
                   "\n" + (request.args.get("error_description") or "")
        ), 400

    code = request.args.get("code")
    state = request.args.get("state")
    if not code:
        return _render(ERROR_PAGE, DETAIL="No 'code' in callback URL."), 400
    if state != session.get("oauth_state"):
        return _render(ERROR_PAGE,
            DETAIL="State mismatch.  Possible CSRF.  Try /login again."
        ), 400

    # --- exchange authorization code for tokens ---
    basic = base64.b64encode(
        (cfg.API_KEY + ":" + cfg.APP_SECRET).encode()
    ).decode()
    headers = {
        "Authorization": "Basic " + basic,
        "Content-Type":  "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": cfg.CALLBACK_URL,
    }

    log.info("Exchanging authorization code for tokens...")
    resp = requests.post(SCHWAB_TOKEN_URL, headers=headers, data=data, timeout=30)
    if resp.status_code != 200:
        return _render(ERROR_PAGE,
            DETAIL="Token exchange failed: " + str(resp.status_code) +
                   "\n" + resp.text
        ), 502

    token_body = resp.json()
    # Schwab returns 'expires_in' (seconds-from-now).  authlib auto-refresh
    # needs 'expires_at' (absolute epoch).  Compute it now so subsequent
    # loads of this token can correctly detect expiry of the access token.
    now = int(time.time())
    if "expires_in" in token_body and "expires_at" not in token_body:
        token_body["expires_at"] = now + int(token_body["expires_in"])

    record = {
        "creation_timestamp": now,
        "token": token_body,
    }
    tm.write_token(record)
    log.info("Token saved (encrypted) to %s", cfg.TOKEN_PATH)

    return _render(SUCCESS_PAGE, TOKEN_PATH=cfg.TOKEN_PATH)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _open_browser_after_startup(url: str, delay: float = 1.5) -> None:
    def go():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception as e:
            log.warning("Could not auto-open browser: %s", e)
    threading.Thread(target=go, daemon=True).start()


def main() -> None:
    if cfg.CALLBACK_URL.startswith("http://"):
        log.error("CALLBACK_URL must be https:// for Schwab.")
        sys.exit(1)

    landing = "https://127.0.0.1:" + str(cfg.AUTH_PORT) + "/"
    log.info("Starting auth server at %s", landing)
    log.info("Browser will pop up shortly.  Accept the self-signed cert warning.")
    _open_browser_after_startup(landing)

    # ssl_context='adhoc' uses cryptography to generate an ephemeral
    # self-signed cert each run.  Fine for localhost.
    app.run(
        host="127.0.0.1",
        port=cfg.AUTH_PORT,
        ssl_context="adhoc",
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
