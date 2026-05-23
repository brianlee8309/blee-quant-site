"""
trader_client.py
----------------
BLEE Quant Pro Subscriber — Schwab Trading Client
Requires a BLEE Quant Premium/Pro subscription on bleeanalytics.com.

Run:    python trader_client.py
Open:   http://127.0.0.1:5060

Auth:   Sign in with your BLEE Quant account (Premium tier or above).
        Schwab API credentials are configured in the Settings tab.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import secrets
import time
from functools import wraps
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, redirect, render_template_string, request, session

# ── Optional: Schwab trading (graceful fail if not yet configured) ─────────────
try:
    from config import settings as _get_settings
    from schwab_client import get_client, get_account_hash
    from schwab.orders.equities import (
        equity_buy_limit, equity_buy_market,
        equity_sell_limit, equity_sell_market,
    )
    from schwab.orders.common import Session as SchwabSession, Duration as SchwabDuration
    _SCHWAB_AVAILABLE = True
    _SCHWAB_ERR = ""
except Exception as _e:
    _SCHWAB_AVAILABLE = False
    _SCHWAB_ERR = str(_e)

# ── Firebase / BLEE constants ──────────────────────────────────────────────────
FIREBASE_API_KEY    = "AIzaSyBRppmBgkdFUWx2raZi9K593843XaCxXso"
FIREBASE_PROJECT_ID = "blee-quant"
BLEE_ADMIN_EMAIL    = "brianlee1004@gmail.com"
BLEE_MIN_TIER       = 2.0   # premium and above

TIER_RANKS: dict[str, float] = {
    "free": 0.5, "newsletter": 0.5,
    "basic": 1.0, "starter": 1.0,
    "premium": 2.0, "pro": 2.0,
    "ultimate": 2.5,
    "marketer": 3.0, "manager": 10.0, "admin": 99.0,
}

# ── Pro subscriber symphony (1 — shown on index2.html) ───────────────────────
PRO_SYMPHONIES: dict[str, dict] = {
    "qjmHJ3IR19kmaAlbgkNj": {
        "name": "BLEE-187 2026 SGOV Bond Min Dual Reversal",
        "stable_file": "composer_allocations_187.json",
    },
}

# ── Ultimate subscriber symphonies (2 total — superset of Pro) ───────────────
ULTIMATE_SYMPHONIES: dict[str, dict] = {
    "qjmHJ3IR19kmaAlbgkNj": {
        "name": "BLEE-187 2026 SGOV Bond Min Dual Reversal",
        "stable_file": "composer_allocations_187.json",
    },
    "iPifD8uTozTr0sbu9qiB": {
        "name": "BLEE-187 High Interest ALL in One",
        "stable_file": "composer_allocations_187hi.json",
    },
}
BLEE_WATCH_URL = "https://bleeanalytics.com/CurrentWatchSymphony.html"
_SKIP = {"$USD", "USD", "CASH", "$CASH", "$", ""}

# ── Flask app ─────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    if (_HERE / ".env").exists():
        load_dotenv(_HERE / ".env")
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("BLEE_CLIENT_SECRET") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("trader_client")

# ── Symphony data cache ───────────────────────────────────────────────────────
_symp_cache: list = []
_symp_ts: float = 0.0


def _fetch_symphonies() -> list[dict]:
    global _symp_cache, _symp_ts
    now = time.time()
    if now - _symp_ts < 300 and _symp_cache:
        return _symp_cache
    r = requests.get(BLEE_WATCH_URL, timeout=20)
    r.raise_for_status()
    marker = "/* __SYMPHONY_DATA__ */"
    idx = r.text.find(marker)
    if idx < 0:
        raise RuntimeError("Symphony data marker not found on bleeanalytics.com")
    start = r.text.index("[", idx)
    data, _ = json.JSONDecoder().raw_decode(r.text, start)
    _symp_cache = data
    _symp_ts = now
    return data


def _get_holdings(symphony_id: str) -> list[dict]:
    """Return [{ticker, weight_pct}, ...] for the given symphony."""
    for s in _fetch_symphonies():
        if s.get("id") == symphony_id:
            return [
                {"ticker": h["ticker"].upper(), "weight_pct": float(h["pct"])}
                for h in s.get("holdings", [])
                if h.get("ticker", "").upper() not in _SKIP
            ]
    raise ValueError(f"Symphony {symphony_id} not found on bleeanalytics.com")


# ── Firebase auth helpers ─────────────────────────────────────────────────────

def _verify_token(id_token: str) -> dict:
    """Verify Firebase ID token. Returns {uid, email} or raises."""
    url = (f"https://identitytoolkit.googleapis.com/v1/accounts:lookup"
           f"?key={FIREBASE_API_KEY}")
    r = requests.post(url, json={"idToken": id_token}, timeout=10)
    r.raise_for_status()
    users = r.json().get("users", [])
    if not users:
        raise ValueError("Token verification failed")
    u = users[0]
    return {"uid": u["localId"], "email": u.get("email", "")}


def _check_tier(uid: str, id_token: str) -> tuple[float, str]:
    """Return (tier_rank, tier_str). Admin email bypasses Firestore."""
    url = (f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
           f"/databases/(default)/documents/users/{uid}")
    r = requests.get(url, headers={"Authorization": f"Bearer {id_token}"}, timeout=10)
    if r.status_code == 404:
        raise PermissionError("no_subscription")
    r.raise_for_status()
    fields = r.json().get("fields", {})
    tier_str = (fields.get("tier", {}).get("stringValue") or "free").lower()
    return TIER_RANKS.get(tier_str, 0.0), tier_str


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("uid"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "not_authenticated"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


# ── Schwab helpers ────────────────────────────────────────────────────────────

def _schwab():
    if not _SCHWAB_AVAILABLE:
        raise RuntimeError(f"Schwab not configured. {_SCHWAB_ERR}")
    return get_client()


def _quote(symbol: str) -> dict:
    r = _schwab().get_quote(symbol)
    r.raise_for_status()
    d = r.json().get(symbol, {}).get("quote", {})
    return {
        "symbol": symbol,
        "ask":  float(d.get("askPrice") or d.get("lastPrice") or 0),
        "bid":  float(d.get("bidPrice") or 0),
        "last": float(d.get("lastPrice") or 0),
        "mark": float(d.get("mark") or 0),
    }


def _get_positions() -> dict[str, float]:
    client = _schwab()
    acct_hash = get_account_hash(client)
    r = client.get_account(acct_hash, fields=["positions"])
    r.raise_for_status()
    out: dict[str, float] = {}
    for p in r.json().get("securitiesAccount", {}).get("positions", []):
        sym = p.get("instrument", {}).get("symbol", "")
        qty = float(p.get("longQuantity", 0)) - float(p.get("shortQuantity", 0))
        if sym and qty:
            out[sym] = qty
    return out


def _get_balances() -> dict:
    client = _schwab()
    acct_hash = get_account_hash(client)
    r = client.get_account(acct_hash, fields=["positions"])
    r.raise_for_status()
    bal = r.json().get("securitiesAccount", {}).get("currentBalances", {})
    return {
        "cash":      float(bal.get("cashBalance", 0)),
        "portfolio": float(bal.get("liquidationValue", 0)),
    }


def _build_order(side: str, symbol: str, qty: int, order_type: str,
                 sess: str, dur: str, limit_price: float | None = None):
    side = side.upper()
    sess_map = {
        "NORMAL": SchwabSession.NORMAL, "AM": SchwabSession.AM,
        "PM": SchwabSession.PM, "SEAMLESS": SchwabSession.SEAMLESS,
    }
    dur_map = {
        "DAY": SchwabDuration.DAY,
        "GOOD_TILL_CANCEL": SchwabDuration.GOOD_TILL_CANCEL,
    }
    if order_type == "MARKET":
        o = equity_buy_market(symbol, qty) if side == "BUY" else equity_sell_market(symbol, qty)
    else:
        if limit_price is None:
            raise ValueError("limit_price required for LIMIT orders")
        o = (equity_buy_limit(symbol, qty, limit_price) if side == "BUY"
             else equity_sell_limit(symbol, qty, limit_price))
    o = o.set_session(sess_map.get(sess, SchwabSession.NORMAL))
    o = o.set_duration(dur_map.get(dur, SchwabDuration.DAY))
    return o.build()


# ── Plan computation ──────────────────────────────────────────────────────────

def _compute_plan(holdings: list[dict], portfolio_value: float,
                  current_pos: dict[str, float]) -> list[dict]:
    rows: list[dict] = []
    for h in holdings:
        ticker = h["ticker"]
        weight = float(h["weight_pct"])
        tgt_dollars = (weight / 100.0) * portfolio_value
        row: dict[str, Any] = {
            "symbol": ticker, "weight_pct": round(weight, 4),
            "target_value": round(tgt_dollars, 2), "ask_price": None,
            "target_shares": 0, "current_shares": float(current_pos.get(ticker, 0)),
            "delta": 0, "action": "hold",
            "limit_price": None, "est_cost": None, "error": None,
        }
        try:
            q = _quote(ticker)
            ask = float(q.get("ask") or 0) or float(q.get("last") or 0)
            if ask <= 0:
                row["error"] = "no quote"
                rows.append(row)
                continue
            row["ask_price"] = round(ask, 4)
            raw = tgt_dollars / ask
            tgt = round(raw)
            if tgt == 0 and raw >= 0.40 and weight > 0:
                tgt = 1
            row["target_shares"] = tgt
            row["delta"] = tgt - int(row["current_shares"])
            if row["delta"] > 0:
                row["action"] = "buy"
                row["limit_price"] = round(ask * 1.0008, 2)
                row["est_cost"] = round(ask * row["delta"], 2)
            elif row["delta"] < 0:
                row["action"] = "sell"
                row["limit_price"] = round(ask * 0.9992, 2)
                row["est_cost"] = round(ask * abs(row["delta"]), 2)
        except Exception as e:
            row["error"] = str(e)
        rows.append(row)

    # Orphan SELL ALL: positions not in the symphony
    syms = {r["symbol"] for r in rows}
    for sym, qty in current_pos.items():
        s = sym.upper()
        if s in syms or s in _SKIP or qty <= 0:
            continue
        try:
            q = _quote(sym)
            ask = float(q.get("ask") or 0) or float(q.get("last") or 0)
        except Exception:
            ask = 0.0
        rows.append({
            "symbol": s, "weight_pct": 0.0, "target_value": 0.0,
            "ask_price": round(ask, 4) if ask > 0 else None,
            "target_shares": 0, "current_shares": float(qty),
            "delta": -int(qty), "action": "sell",
            "limit_price": round(ask * 0.9992, 2) if ask > 0 else None,
            "est_cost": round(ask * 0.9992 * qty, 2) if ask > 0 else None,
            "error": None if ask > 0 else "no quote",
        })

    rows.sort(key=lambda r: r["weight_pct"] or 0, reverse=True)
    return rows


# ── .env helper ───────────────────────────────────────────────────────────────

def _read_env_file() -> dict[str, str]:
    path = _HERE / ".env"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _write_env_file(updates: dict[str, str]) -> None:
    existing = _read_env_file()
    existing.update({k: v for k, v in updates.items() if v is not None})
    path = _HERE / ".env"
    content = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
    path.write_text(content, encoding="utf-8")


# ── HTML Templates ────────────────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BLEE Quant Pro — Sign In</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b1120;color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:40px;width:100%;max-width:400px}
.logo{font-size:13px;font-weight:700;color:#3b82f6;letter-spacing:2px;text-transform:uppercase;margin-bottom:24px}
h1{font-size:22px;font-weight:700;margin-bottom:4px}
.sub{color:#94a3b8;font-size:14px;margin-bottom:28px}
label{font-size:12px;font-weight:600;color:#94a3b8;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px}
input[type=email],input[type=password]{width:100%;background:#0b1120;border:1px solid #1f2937;border-radius:6px;padding:10px 12px;color:#f1f5f9;font-size:14px;margin-bottom:16px;outline:none;transition:border .15s}
input:focus{border-color:#3b82f6}
.btn{width:100%;padding:11px;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer;border:none;margin-bottom:10px;transition:.15s}
.btn-primary{background:#3b82f6;color:#fff}.btn-primary:hover{background:#2563eb}
.btn-google{background:#1f2937;color:#f1f5f9;border:1px solid #374151}.btn-google:hover{background:#374151}
.divider{text-align:center;color:#4b5563;font-size:13px;margin:2px 0 10px}
.err{background:#450a0a;border:1px solid #ef444466;color:#fca5a5;border-radius:6px;padding:10px 12px;font-size:13px;margin-bottom:14px;display:none}
.note{color:#64748b;font-size:12px;text-align:center;margin-top:20px}
</style>
</head><body>
<div class="card">
  <div class="logo">&#x25A6; BLEE Quant Pro</div>
  <h1>Sign In</h1>
  <p class="sub">Premium or Pro subscription required</p>
  <div class="err" id="err"></div>
  <label>Email</label>
  <input type="email" id="email" placeholder="you@example.com" autocomplete="email">
  <label>Password</label>
  <input type="password" id="pw" placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;" autocomplete="current-password">
  <button class="btn btn-primary" id="signInBtn" onclick="signIn()">Sign In</button>
  <div class="divider">or</div>
  <button class="btn btn-google" onclick="signInGoogle()">Sign in with Google</button>
  <p class="note">Need a subscription? Visit <a href="https://bleeanalytics.com" target="_blank" style="color:#3b82f6">bleeanalytics.com</a></p>
</div>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-auth-compat.js"></script>
<script>
firebase.initializeApp({
  apiKey:"AIzaSyBRppmBgkdFUWx2raZi9K593843XaCxXso",
  authDomain:"blee-quant.firebaseapp.com",
  projectId:"blee-quant",
  appId:"1:924733444755:web:f1931828a0a91cca1cb366"
});
const auth = firebase.auth();

function showErr(msg){const e=document.getElementById('err');e.style.display='block';e.textContent=msg;}
function hideErr(){document.getElementById('err').style.display='none';}
function setBusy(b){document.getElementById('signInBtn').disabled=b;document.getElementById('signInBtn').textContent=b?'Signing in...':'Sign In';}

async function doAuth(user){
  try{
    const token=await user.getIdToken(true);
    const r=await fetch('/api/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idToken:token})});
    const d=await r.json();
    if(d.ok){window.location.href='/';}
    else{showErr(d.error||'Access denied. Pro subscription required.');auth.signOut();}
  }catch(e){showErr(e.message);}finally{setBusy(false);}
}

async function signIn(){
  hideErr();
  const email=document.getElementById('email').value.trim();
  const pw=document.getElementById('pw').value;
  if(!email||!pw){showErr('Enter your email and password.');return;}
  setBusy(true);
  try{
    const cred=await auth.signInWithEmailAndPassword(email,pw);
    await doAuth(cred.user);
  }catch(e){
    const m={'auth/user-not-found':'No account found.','auth/wrong-password':'Incorrect password.',
             'auth/invalid-credential':'Incorrect email or password.','auth/too-many-requests':'Too many attempts. Try later.'};
    showErr(m[e.code]||e.message);setBusy(false);
  }
}

async function signInGoogle(){
  hideErr();
  try{
    const cred=await auth.signInWithPopup(new firebase.auth.GoogleAuthProvider());
    await doAuth(cred.user);
  }catch(e){if(e.code!=='auth/popup-closed-by-user')showErr(e.message);}
}

document.addEventListener('keydown',e=>{if(e.key==='Enter')signIn();});
</script>
</body></html>"""


MAIN_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BLEE Quant Pro — Schwab Trader</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b1120;color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding-top:44px}
#mbar{position:fixed;top:0;left:0;right:0;height:44px;background:#0f172a;border-bottom:1px solid #1f2937;display:flex;align-items:center;padding:0 16px;font-size:13px;z-index:100;gap:12px}
#mbar .logo{font-weight:800;color:#3b82f6;font-size:14px}
#mbar .email{color:#94a3b8}
#mbar .tier{background:#1e3a5f;color:#60a5fa;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;text-transform:uppercase}
#mbar .ml{margin-left:auto}
#mbar a{color:#94a3b8;text-decoration:none;font-size:12px}.#mbar a:hover{color:#f1f5f9}
.tabs{display:flex;gap:1px;background:#111827;border-bottom:1px solid #1f2937;padding:0 16px}
.tab{background:none;border:none;color:#94a3b8;padding:12px 18px;cursor:pointer;font-size:14px;font-weight:500;border-bottom:2px solid transparent;transition:.15s}
.tab:hover{color:#f1f5f9}.tab.active{color:#3b82f6;border-bottom-color:#3b82f6}
.panel{display:none;padding:20px 16px;max-width:1100px;margin:0 auto}.panel.active{display:block}
h2{font-size:16px;font-weight:700;margin-bottom:16px;color:#e2e8f0}
label{font-size:12px;font-weight:600;color:#94a3b8;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:.4px}
input,select{background:#111827;border:1px solid #1f2937;border-radius:6px;padding:9px 12px;color:#f1f5f9;font-size:14px;outline:none;transition:border .15s;width:100%}
input:focus,select:focus{border-color:#3b82f6}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:14px}
.btn{padding:9px 18px;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;border:none;transition:.15s}
.btn-blue{background:#3b82f6;color:#fff}.btn-blue:hover{background:#2563eb}
.btn-green{background:#059669;color:#fff}.btn-green:hover{background:#047857}
.btn-red{background:#dc2626;color:#fff}.btn-red:hover{background:#b91c1c}
.btn-gray{background:#1f2937;color:#f1f5f9;border:1px solid #374151}.btn-gray:hover{background:#374151}
.btn-sm{padding:5px 12px;font-size:12px}
.tog-row{display:flex;gap:0;border:1px solid #1f2937;border-radius:6px;overflow:hidden;width:fit-content}
.tog{background:none;border:none;padding:8px 16px;color:#94a3b8;cursor:pointer;font-size:14px;font-weight:500;transition:.15s}
.tog.on{background:#1e3a5f;color:#60a5fa}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#111827;color:#94a3b8;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:8px 10px;text-align:left;border-bottom:1px solid #1f2937}
td{padding:8px 10px;border-bottom:1px solid #111827;vertical-align:middle}
tr:hover td{background:#111827}
.buy{color:#34d399}.sell{color:#f87171}.hold{color:#94a3b8}.excluded{color:#6b7280}
.card{background:#111827;border:1px solid #1f2937;border-radius:8px;padding:18px;margin-bottom:16px}
.quote-box{background:#0f172a;border:1px solid #1f2937;border-radius:6px;padding:10px 14px;margin-bottom:14px;font-size:14px;display:none}
.quote-box span{color:#94a3b8;font-size:12px}
.modal-bg{display:none;position:fixed;inset:0;background:#000a;z-index:200;align-items:center;justify-content:center}
.modal-bg.show{display:flex}
.modal{background:#111827;border:1px solid #374151;border-radius:10px;padding:28px;min-width:340px;max-width:480px}
.modal h3{font-size:16px;margin-bottom:16px}
.modal .line{display:flex;justify-content:space-between;margin-bottom:8px;font-size:14px}
.modal .line span{color:#94a3b8}
.modal .btns{display:flex;gap:10px;margin-top:20px}
.modal .btns button{flex:1}
.alert{border-radius:6px;padding:10px 14px;font-size:13px;margin-bottom:14px;display:none}
.alert-ok{background:#022c22;border:1px solid #10b981;color:#6ee7b7}
.alert-err{background:#450a0a;border:1px solid #ef4444;color:#fca5a5}
.summary-row{background:#0f172a;font-weight:600}
.cfg-note{color:#64748b;font-size:12px;margin-top:6px;line-height:1.5}
.schwab-warn{background:#451a03;border:1px solid #f97316;color:#fed7aa;border-radius:6px;padding:12px;font-size:13px;margin-bottom:16px}
.loading{color:#64748b;font-size:13px;padding:20px 0}
</style>
</head><body>

<div id="mbar">
  <span class="logo">&#x25A6; BLEE Quant Pro</span>
  <span class="email">{{ email }}</span>
  <span class="tier">{{ tier }}</span>
  <div class="ml">
    <a href="/logout">Sign Out</a>
  </div>
</div>

<div class="tabs">
  <button class="tab active" onclick="showTab('trade')">Trade</button>
  <button class="tab" onclick="showTab('rebalance')">Rebalance</button>
  <button class="tab" onclick="showTab('positions')">Positions</button>
  <button class="tab" onclick="showTab('orders')">Orders</button>
  <button class="tab" onclick="showTab('settings')">Settings</button>
</div>

<!-- TRADE -->
<div id="tab-trade" class="panel active">
  <h2>Manual Trade</h2>
  <div id="schwab-warn" class="schwab-warn" style="display:none">
    Schwab is not configured. Go to <strong>Settings</strong> to enter your API credentials and run auth_server.py.
  </div>
  <div class="card">
    <div class="row">
      <div>
        <label>Action</label>
        <div class="tog-row">
          <button class="tog on" id="tSide-BUY" onclick="setTog('tSide','BUY')">BUY</button>
          <button class="tog" id="tSide-SELL" onclick="setTog('tSide','SELL')">SELL</button>
        </div>
      </div>
      <div>
        <label>Order Type</label>
        <div class="tog-row">
          <button class="tog on" id="tType-LIMIT" onclick="setTog('tType','LIMIT');toggleLimitPx()">LIMIT</button>
          <button class="tog" id="tType-MARKET" onclick="setTog('tType','MARKET');toggleLimitPx()">MARKET</button>
        </div>
      </div>
      <div>
        <label>Session</label>
        <select id="tSession">
          <option value="NORMAL">Regular Hours</option>
          <option value="AM">Pre-Market (AM)</option>
          <option value="PM">After-Hours (PM)</option>
          <option value="SEAMLESS">Seamless</option>
        </select>
      </div>
      <div>
        <label>Duration</label>
        <div class="tog-row">
          <button class="tog on" id="tDur-DAY" onclick="setTog('tDur','DAY')">DAY</button>
          <button class="tog" id="tDur-GTC" onclick="setTog('tDur','GTC')">GTC</button>
        </div>
      </div>
    </div>
    <div class="row">
      <div>
        <label>Symbol</label>
        <input id="tSym" type="text" placeholder="e.g. SGOV" style="text-transform:uppercase" oninput="this.value=this.value.toUpperCase()">
      </div>
      <div>
        <label>Shares</label>
        <input id="tQty" type="number" placeholder="100" min="1">
      </div>
      <div id="limitPxBox">
        <label>Limit Price</label>
        <input id="tLimit" type="number" placeholder="0.00" step="0.01">
      </div>
      <div style="display:flex;align-items:flex-end;gap:8px">
        <button class="btn btn-gray" onclick="getQuote()">Get Quote</button>
        <button class="btn btn-blue" onclick="openTradeModal()">Review Order</button>
      </div>
    </div>
    <div class="quote-box" id="quoteBox">
      <span>Ask</span> <strong id="qAsk">—</strong>&emsp;
      <span>Bid</span> <strong id="qBid">—</strong>&emsp;
      <span>Last</span> <strong id="qLast">—</strong>&emsp;
      <span>Symbol</span> <strong id="qSym">—</strong>
    </div>
    <div class="alert alert-ok" id="tradeOk"></div>
    <div class="alert alert-err" id="tradeErr"></div>
  </div>
</div>

<!-- REBALANCE -->
<div id="tab-rebalance" class="panel">
  <h2>Rebalance</h2>
  <div class="card">
    <div class="row" style="grid-template-columns:1fr 160px 200px auto">
      <div>
        <label>Symphony</label>
        <select id="rSym">
          <option value="">Loading symphonies...</option>
        </select>
      </div>
      <div>
        <label>Budget ($)</label>
        <input id="rBudget" type="number" value="{{ budget }}" step="100">
      </div>
      <div>
        <label>Exempt Symbols (comma-sep)</label>
        <input id="rExempt" type="text" placeholder="e.g. GOOG,AAPL">
      </div>
      <div style="display:flex;align-items:flex-end">
        <button class="btn btn-blue" onclick="computePlan()">Compute Plan</button>
      </div>
    </div>
    <div class="alert alert-ok" id="planOk"></div>
    <div class="alert alert-err" id="planErr"></div>
  </div>
  <div id="planSection" style="display:none">
    <div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap">
      <button class="btn btn-red" onclick="executePlan('sell')">Execute All Sells</button>
      <button class="btn btn-green" onclick="executePlan('buy')">Execute All Buys</button>
      <button class="btn btn-blue" onclick="executePlan('all')">Execute All Orders</button>
    </div>
    <div class="alert alert-ok" id="execOk"></div>
    <div class="alert alert-err" id="execErr"></div>
    <div style="overflow-x:auto">
    <table id="planTable">
      <thead><tr>
        <th>Symbol</th><th>Weight%</th><th>Target $</th><th>Ask</th>
        <th>Target Sh</th><th>Current Sh</th><th>Delta</th>
        <th>Action</th><th>Limit</th><th>Est. Cost</th>
      </tr></thead>
      <tbody id="planBody"></tbody>
    </table>
    </div>
    <div class="card" id="planSummary" style="margin-top:14px;font-size:13px"></div>
  </div>
</div>

<!-- POSITIONS -->
<div id="tab-positions" class="panel">
  <h2>Current Positions <button class="btn btn-gray btn-sm" style="margin-left:10px" onclick="loadPositions()">Refresh</button></h2>
  <div class="loading" id="posLoading">Loading...</div>
  <div id="posSection" style="display:none">
    <div class="card" id="posBalance" style="margin-bottom:14px;font-size:14px"></div>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th>Symbol</th><th>Qty</th><th>Current Price</th><th>Market Value</th></tr></thead>
      <tbody id="posBody"></tbody>
    </table>
    </div>
  </div>
  <div class="alert alert-err" id="posErr"></div>
</div>

<!-- ORDERS -->
<div id="tab-orders" class="panel">
  <h2>Recent Orders <button class="btn btn-gray btn-sm" style="margin-left:10px" onclick="loadOrders()">Refresh</button></h2>
  <div class="loading" id="ordLoading">Loading...</div>
  <div id="ordSection" style="display:none;overflow-x:auto">
    <table>
      <thead><tr><th>ID</th><th>Symbol</th><th>Action</th><th>Qty</th><th>Type</th><th>Price</th><th>Status</th><th>Cancel</th></tr></thead>
      <tbody id="ordBody"></tbody>
    </table>
  </div>
  <div class="alert alert-err" id="ordErr"></div>
</div>

<!-- SETTINGS -->
<div id="tab-settings" class="panel">
  <h2>Schwab API Settings</h2>
  <div id="settingsWarn" class="schwab-warn" style="display:none"></div>
  <div class="card" style="max-width:600px">
    <div class="row" style="grid-template-columns:1fr">
      <div>
        <label>Schwab API Key</label>
        <input id="sApiKey" type="text" placeholder="Your Schwab app's App Key">
      </div>
      <div>
        <label>Schwab App Secret</label>
        <input id="sAppSecret" type="password" placeholder="Your Schwab app's App Secret">
      </div>
      <div>
        <label>Account Number</label>
        <input id="sAcctNum" type="text" placeholder="e.g. 12345678">
      </div>
      <div>
        <label>Token Passphrase <span style="color:#64748b;font-weight:400">(any passphrase to encrypt the token file)</span></label>
        <input id="sPassphrase" type="password" placeholder="Choose any secure passphrase">
      </div>
      <div>
        <label>Callback URL <span style="color:#64748b;font-weight:400">(default is fine)</span></label>
        <input id="sCallbackUrl" type="text" placeholder="https://127.0.0.1:8182">
      </div>
      <div>
        <label>Portfolio Budget ($)</label>
        <input id="sBudget" type="number" placeholder="10000" step="100">
      </div>
    </div>
    <button class="btn btn-blue" onclick="saveSettings()">Save Settings</button>
    <div class="alert alert-ok" id="setOk" style="margin-top:12px"></div>
    <div class="alert alert-err" id="setErr" style="margin-top:12px"></div>
  </div>
  <div class="card" style="max-width:600px;margin-top:0">
    <h2 style="margin-bottom:10px;font-size:14px">Schwab Token Authentication</h2>
    <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin-bottom:10px">
      After saving settings above, run the one-time auth flow to get your Schwab token.
      You need to do this once and then once a week to refresh it.
    </p>
    <div style="background:#0b1120;border:1px solid #1f2937;border-radius:6px;padding:12px;font-size:13px;font-family:monospace;color:#a5b4fc;margin-bottom:10px">
      <div>1. Stop this app (Ctrl+C in terminal)</div>
      <div>2. Run: <strong>python auth_server.py</strong></div>
      <div>3. Click "Sign in with Schwab" in your browser</div>
      <div>4. Complete Schwab 2FA</div>
      <div>5. Run: <strong>python trader_client.py</strong> again</div>
    </div>
    <p class="cfg-note">The token file is encrypted with your passphrase and stored in the src/ folder.</p>
  </div>
</div>

<!-- Trade Confirmation Modal -->
<div class="modal-bg" id="tradeMod">
  <div class="modal">
    <h3>Confirm Order</h3>
    <div class="line"><span>Symbol</span><strong id="mSym"></strong></div>
    <div class="line"><span>Action</span><strong id="mAction"></strong></div>
    <div class="line"><span>Shares</span><strong id="mQty"></strong></div>
    <div class="line"><span>Order Type</span><strong id="mType"></strong></div>
    <div class="line"><span>Limit Price</span><strong id="mLimit"></strong></div>
    <div class="line"><span>Session</span><strong id="mSess"></strong></div>
    <div class="line"><span>Duration</span><strong id="mDur"></strong></div>
    <div class="modal-btns btns">
      <button class="btn btn-gray" onclick="closeMod('tradeMod')">Cancel</button>
      <button class="btn btn-blue" id="confirmBtn" onclick="submitOrder()">Place Order</button>
    </div>
  </div>
</div>

<script>
// Tab switching
function showTab(name){
  document.querySelectorAll('.tab').forEach((t,i)=>{
    const tabs=['trade','rebalance','positions','orders','settings'];
    t.classList.toggle('active',tabs[i]===name);
  });
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if(name==='positions')loadPositions();
  if(name==='orders')loadOrders();
  if(name==='settings')loadSettings();
}

// Toggle buttons
const togState={};
function setTog(group,val){
  togState[group]=val;
  document.querySelectorAll('[id^="'+group+'-"]').forEach(el=>{
    el.classList.toggle('on',el.id===group+'-'+val);
  });
}
// Init defaults
togState.tSide='BUY'; togState.tType='LIMIT'; togState.tDur='DAY';

function toggleLimitPx(){
  document.getElementById('limitPxBox').style.display=togState.tType==='MARKET'?'none':'block';
}

function showAlert(id,msg,clear){
  if(clear)document.querySelectorAll('.alert').forEach(e=>{e.style.display='none';});
  const el=document.getElementById(id);el.style.display='block';el.textContent=msg;
}
function closeMod(id){document.getElementById(id).classList.remove('show');}

// ── Quote ──────────────────────────────────────────────────────────────────────
async function getQuote(){
  const sym=document.getElementById('tSym').value.trim().toUpperCase();
  if(!sym)return;
  try{
    const r=await fetch('/api/quote?symbol='+sym);
    const d=await r.json();
    if(d.error){showAlert('tradeErr',d.error,true);return;}
    document.getElementById('qSym').textContent=d.symbol;
    document.getElementById('qAsk').textContent='$'+d.ask.toFixed(4);
    document.getElementById('qBid').textContent='$'+d.bid.toFixed(4);
    document.getElementById('qLast').textContent='$'+d.last.toFixed(4);
    document.getElementById('quoteBox').style.display='block';
    document.getElementById('tradeErr').style.display='none';
    if(!document.getElementById('tLimit').value && d.ask>0)
      document.getElementById('tLimit').value=d.ask.toFixed(2);
  }catch(e){showAlert('tradeErr',e.message,true);}
}

// ── Trade modal ───────────────────────────────────────────────────────────────
function openTradeModal(){
  const sym=document.getElementById('tSym').value.trim().toUpperCase();
  const qty=parseInt(document.getElementById('tQty').value)||0;
  if(!sym||qty<=0){showAlert('tradeErr','Enter symbol and quantity.',true);return;}
  const lim=parseFloat(document.getElementById('tLimit').value)||0;
  if(togState.tType==='LIMIT'&&lim<=0){showAlert('tradeErr','Enter limit price.',true);return;}
  document.getElementById('mSym').textContent=sym;
  document.getElementById('mAction').textContent=togState.tSide;
  document.getElementById('mQty').textContent=qty;
  document.getElementById('mType').textContent=togState.tType;
  document.getElementById('mLimit').textContent=togState.tType==='MARKET'?'N/A':'$'+lim.toFixed(2);
  document.getElementById('mSess').textContent=document.getElementById('tSession').value;
  document.getElementById('mDur').textContent=togState.tDur==='GTC'?'Good Till Cancel':'Day';
  document.getElementById('tradeMod').classList.add('show');
}

async function submitOrder(){
  document.getElementById('confirmBtn').disabled=true;
  document.getElementById('confirmBtn').textContent='Placing...';
  const body={
    symbol:document.getElementById('mSym').textContent,
    qty:parseInt(document.getElementById('mQty').textContent),
    side:togState.tSide, order_type:togState.tType,
    session:document.getElementById('tSession').value,
    duration:togState.tDur==='GTC'?'GOOD_TILL_CANCEL':'DAY',
    limit_price:togState.tType==='LIMIT'?parseFloat(document.getElementById('tLimit').value):null
  };
  try{
    const r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    closeMod('tradeMod');
    if(d.ok){showAlert('tradeOk','Order placed successfully.',true);}
    else{showAlert('tradeErr',d.error||'Order failed.',true);}
  }catch(e){showAlert('tradeErr',e.message,true);}
  finally{
    document.getElementById('confirmBtn').disabled=false;
    document.getElementById('confirmBtn').textContent='Place Order';
  }
}

// ── Rebalance ─────────────────────────────────────────────────────────────────
let planData=[];
async function computePlan(){
  document.getElementById('planOk').style.display='none';
  document.getElementById('planErr').style.display='none';
  const btn=event.target;btn.disabled=true;btn.textContent='Computing...';
  try{
    const r=await fetch('/api/plan',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        symphony_id:document.getElementById('rSym').value,
        budget:parseFloat(document.getElementById('rBudget').value)||10000,
        exempt:document.getElementById('rExempt').value.trim()
      })
    });
    const d=await r.json();
    if(d.error){showAlert('planErr',d.error,false);return;}
    planData=d.rows||[];
    renderPlan(d);
    document.getElementById('planSection').style.display='block';
    showAlert('planOk','Plan computed from bleeanalytics.com. Source: '+d.source,false);
  }catch(e){showAlert('planErr',e.message,false);}
  finally{btn.disabled=false;btn.textContent='Compute Plan';}
}

function renderPlan(d){
  const tbody=document.getElementById('planBody');
  tbody.innerHTML='';
  for(const row of d.rows){
    const cls=row.action==='buy'?'buy':row.action==='sell'?'sell':row.action==='excluded'?'excluded':'hold';
    const wPct=row.weight_pct>0?row.weight_pct.toFixed(2)+'%':'0%';
    const tgt=row.target_value>0?'$'+row.target_value.toLocaleString(undefined,{minimumFractionDigits:2}):'—';
    const ask=row.ask_price?'$'+row.ask_price.toFixed(4):'—';
    const lim=row.limit_price?'$'+row.limit_price.toFixed(2):'—';
    const cost=row.est_cost?'$'+Math.abs(row.est_cost).toLocaleString(undefined,{minimumFractionDigits:2}):'—';
    const err=row.error?` <span style="color:#f87171;font-size:11px">(${row.error})</span>`:'';
    tbody.innerHTML+=`<tr>
      <td><strong>${row.symbol}</strong>${err}</td>
      <td>${wPct}</td><td>${tgt}</td><td>${ask}</td>
      <td>${row.target_shares}</td><td>${row.current_shares}</td>
      <td class="${row.delta>0?'buy':row.delta<0?'sell':'hold'}">${row.delta>0?'+':''}${row.delta}</td>
      <td><span class="${cls}">${row.action.toUpperCase()}</span></td>
      <td>${lim}</td><td>${cost}</td>
    </tr>`;
  }
  // Summary
  const sells=d.rows.filter(r=>r.action==='sell'&&r.est_cost),buys=d.rows.filter(r=>r.action==='buy'&&r.est_cost);
  const sellTotal=sells.reduce((s,r)=>s+r.est_cost,0);
  const buyTotal=buys.reduce((s,r)=>s+r.est_cost,0);
  const symphTotal=d.rows.filter(r=>r.weight_pct>0).reduce((s,r)=>s+(r.target_shares*(r.ask_price||0)),0);
  document.getElementById('planSummary').innerHTML=
    `<strong>Symphony target:</strong> $${symphTotal.toLocaleString(undefined,{minimumFractionDigits:2})} &emsp;`+
    `<strong>Sell proceeds:</strong> <span class="sell">+$${sellTotal.toLocaleString(undefined,{minimumFractionDigits:2})}</span> &emsp;`+
    `<strong>Buy cost:</strong> <span class="buy">-$${buyTotal.toLocaleString(undefined,{minimumFractionDigits:2})}</span> &emsp;`+
    `<strong>Net:</strong> $${(sellTotal-buyTotal).toLocaleString(undefined,{minimumFractionDigits:2})}`;
}

async function executePlan(mode){
  const rows=planData.filter(r=>{
    if(mode==='sell')return r.action==='sell'&&r.delta!==0&&!r.error;
    if(mode==='buy')return r.action==='buy'&&r.delta!==0&&!r.error;
    return(r.action==='buy'||r.action==='sell')&&r.delta!==0&&!r.error;
  });
  if(!rows.length){showAlert('execErr','No '+(mode==='all'?'':mode+' ')+'orders to execute.',false);return;}
  if(!confirm('Place '+rows.length+' order(s)?'))return;
  document.getElementById('execOk').style.display='none';
  document.getElementById('execErr').style.display='none';
  let ok=0,fail=0;
  for(const row of rows){
    try{
      const r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({symbol:row.symbol,qty:Math.abs(row.delta),
          side:row.delta>0?'BUY':'SELL',order_type:'LIMIT',
          session:'NORMAL',duration:'DAY',limit_price:row.limit_price})});
      const d=await r.json();d.ok?ok++:fail++;
    }catch{fail++;}
  }
  if(ok)showAlert('execOk',ok+' order(s) placed successfully.',false);
  if(fail)showAlert('execErr',fail+' order(s) failed. Check Orders tab.',false);
}

// ── Positions ─────────────────────────────────────────────────────────────────
async function loadPositions(){
  document.getElementById('posLoading').style.display='block';
  document.getElementById('posSection').style.display='none';
  document.getElementById('posErr').style.display='none';
  try{
    const r=await fetch('/api/positions');const d=await r.json();
    if(d.error){showAlert('posErr',d.error,false);return;}
    const tbody=document.getElementById('posBody');tbody.innerHTML='';
    let total=0;
    for(const p of d.positions){
      const val=(p.qty*(p.last||0));total+=val;
      tbody.innerHTML+=`<tr><td><strong>${p.symbol}</strong></td><td>${p.qty}</td>
        <td>${p.last?'$'+p.last.toFixed(4):'—'}</td>
        <td>${val>0?'$'+val.toLocaleString(undefined,{minimumFractionDigits:2}):'—'}</td></tr>`;
    }
    const bal=d.balances||{};
    document.getElementById('posBalance').innerHTML=
      `<strong>Cash:</strong> $${(bal.cash||0).toLocaleString(undefined,{minimumFractionDigits:2})} &emsp;`+
      `<strong>Portfolio Value:</strong> $${(bal.portfolio||0).toLocaleString(undefined,{minimumFractionDigits:2})} &emsp;`+
      `<strong>Positions:</strong> ${d.positions.length}`;
    document.getElementById('posSection').style.display='block';
  }catch(e){showAlert('posErr',e.message,false);}
  finally{document.getElementById('posLoading').style.display='none';}
}

// ── Orders ────────────────────────────────────────────────────────────────────
async function loadOrders(){
  document.getElementById('ordLoading').style.display='block';
  document.getElementById('ordSection').style.display='none';
  document.getElementById('ordErr').style.display='none';
  try{
    const r=await fetch('/api/orders');const d=await r.json();
    if(d.error){showAlert('ordErr',d.error,false);return;}
    const tbody=document.getElementById('ordBody');tbody.innerHTML='';
    for(const o of d.orders){
      const canCancel=['PENDING_ACTIVATION','QUEUED','WORKING','ACCEPTED'].includes(o.status);
      const leg=o.legs&&o.legs[0]||{};
      tbody.innerHTML+=`<tr>
        <td style="font-size:11px;color:#94a3b8">${o.orderId||'—'}</td>
        <td><strong>${leg.symbol||'—'}</strong></td>
        <td class="${leg.action==='BUY'?'buy':'sell'}">${leg.action||'—'}</td>
        <td>${leg.qty||'—'}</td>
        <td>${o.orderType||'—'}</td>
        <td>${o.price?'$'+o.price:'MKT'}</td>
        <td>${o.status||'—'}</td>
        <td>${canCancel?`<button class="btn btn-red btn-sm" onclick="cancelOrder(${o.orderId})">Cancel</button>`:''}</td>
      </tr>`;
    }
    if(!d.orders.length)tbody.innerHTML='<tr><td colspan="8" style="color:#64748b;text-align:center;padding:20px">No recent orders.</td></tr>';
    document.getElementById('ordSection').style.display='block';
  }catch(e){showAlert('ordErr',e.message,false);}
  finally{document.getElementById('ordLoading').style.display='none';}
}

async function cancelOrder(orderId){
  if(!confirm('Cancel order #'+orderId+'?'))return;
  try{
    const r=await fetch('/api/order/'+orderId,{method:'DELETE'});
    const d=await r.json();
    if(d.ok){loadOrders();}else{showAlert('ordErr',d.error||'Cancel failed.',false);}
  }catch(e){showAlert('ordErr',e.message,false);}
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function loadSettings(){
  try{
    const r=await fetch('/api/settings');const d=await r.json();
    document.getElementById('sApiKey').value=d.SCHWAB_API_KEY||'';
    document.getElementById('sAppSecret').value=d.SCHWAB_APP_SECRET?'********':'';
    document.getElementById('sAcctNum').value=d.SCHWAB_ACCOUNT_NUMBER||'';
    document.getElementById('sPassphrase').value=d.SCHWAB_TOKEN_PASSPHRASE?'********':'';
    document.getElementById('sCallbackUrl').value=d.SCHWAB_CALLBACK_URL||'https://127.0.0.1:8182';
    document.getElementById('sBudget').value=d.PORTFOLIO_VALUE||'10000';
    if(!d.SCHWAB_API_KEY){
      const w=document.getElementById('settingsWarn');
      w.textContent='Schwab not configured. Fill in your credentials below and save.';
      w.style.display='block';
    }
  }catch(e){console.error(e);}
}

async function saveSettings(){
  const updates={
    SCHWAB_API_KEY:document.getElementById('sApiKey').value.trim(),
    SCHWAB_ACCOUNT_NUMBER:document.getElementById('sAcctNum').value.trim(),
    SCHWAB_CALLBACK_URL:document.getElementById('sCallbackUrl').value.trim()||'https://127.0.0.1:8182',
    PORTFOLIO_VALUE:document.getElementById('sBudget').value.trim()||'10000',
  };
  // Only overwrite secrets if user typed a new value (not the masked placeholder)
  const ap=document.getElementById('sAppSecret').value;if(ap&&ap!=='********')updates.SCHWAB_APP_SECRET=ap;
  const pp=document.getElementById('sPassphrase').value;if(pp&&pp!=='********')updates.SCHWAB_TOKEN_PASSPHRASE=pp;
  try{
    const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(updates)});
    const d=await r.json();
    if(d.ok){showAlert('setOk','Settings saved. Restart the app for Schwab changes to take effect.',false);}
    else{showAlert('setErr',d.error||'Save failed.',false);}
  }catch(e){showAlert('setErr',e.message,false);}
}

// Load symphony dropdown from server (admin gets all, pro gets 2)
async function loadSymphonies(){
  try{
    const r=await fetch('/api/symphonies');
    const d=await r.json();
    if(d.error)return;
    const sel=document.getElementById('rSym');
    sel.innerHTML='';
    for(const[sid,info]of Object.entries(d.symphonies)){
      const opt=document.createElement('option');
      opt.value=sid;
      opt.textContent=info.name;
      sel.appendChild(opt);
    }
    if(d.is_admin){
      const note=document.createElement('option');
      note.disabled=true;
      note.textContent='── '+Object.keys(d.symphonies).length+' symphonies (admin view) ──';
      // insert as first disabled hint — actually just set a data attribute
      sel.title='Admin: all '+ Object.keys(d.symphonies).length +' symphonies available';
    }
  }catch(e){console.warn('Could not load symphonies:',e);}
}

// Check Schwab on load
fetch('/api/status').then(r=>r.json()).then(d=>{
  if(!d.schwab_ok){
    const w=document.getElementById('schwab-warn');
    if(w)w.style.display='block';
  }
});

// Init symphonies on load
loadSymphonies();
</script>
</body></html>"""


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/login")
def login_page():
    if session.get("uid"):
        return redirect("/")
    return render_template_string(LOGIN_HTML)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/auth", methods=["POST"])
def api_auth():
    """Firebase token verification + tier check."""
    id_token = (request.json or {}).get("idToken", "")
    if not id_token:
        return jsonify({"error": "No token provided"}), 400
    try:
        info = _verify_token(id_token)
        uid, email = info["uid"], info["email"]

        # Admin bypass
        if email.lower() == BLEE_ADMIN_EMAIL.lower():
            session["uid"] = uid
            session["email"] = email
            session["tier"] = "admin"
            session["id_token"] = id_token
            log.info("Admin login: %s", email)
            return jsonify({"ok": True})

        # Check Firestore tier
        rank, tier_str = _check_tier(uid, id_token)
        if rank < BLEE_MIN_TIER:
            return jsonify({
                "error": (f"Subscription tier '{tier_str}' is not sufficient. "
                          "Premium or higher required. Visit bleeanalytics.com to upgrade.")
            })

        session["uid"] = uid
        session["email"] = email
        session["tier"] = tier_str
        session["id_token"] = id_token
        log.info("User login: %s (tier=%s, rank=%.1f)", email, tier_str, rank)
        return jsonify({"ok": True})

    except PermissionError as e:
        msg = str(e)
        if msg == "no_subscription":
            return jsonify({"error": "No subscription found. Please subscribe at bleeanalytics.com"})
        return jsonify({"error": msg})
    except Exception as e:
        log.exception("Auth error")
        return jsonify({"error": str(e)}), 500


@app.route("/")
@login_required
def main_page():
    budget = float(os.environ.get("PORTFOLIO_VALUE", "10000"))
    return render_template_string(
        MAIN_HTML,
        email=session.get("email", ""),
        tier=session.get("tier", ""),
        budget=budget,
    )


@app.route("/api/status")
@login_required
def api_status():
    return jsonify({
        "schwab_ok": _SCHWAB_AVAILABLE,
        "schwab_err": _SCHWAB_ERR,
    })


@app.route("/api/symphonies")
@login_required
def api_symphonies():
    """Return available symphonies based on tier.
    Admin: all from bleeanalytics.com
    Ultimate ($99/mo): 2 symphonies
    Pro ($49/mo): 1 symphony
    """
    email     = session.get("email", "").lower()
    tier      = session.get("tier", "")
    tier_rank = TIER_RANKS.get(tier, 0.0)
    is_admin    = email == BLEE_ADMIN_EMAIL.lower()
    is_ultimate = tier_rank >= TIER_RANKS["ultimate"]
    try:
        if is_admin:
            all_syms = _fetch_symphonies()
            syms = {}
            for s in all_syms:
                sid = s.get("id", "")
                if not sid:
                    continue
                stable = ULTIMATE_SYMPHONIES.get(sid, PRO_SYMPHONIES.get(sid, {})).get("stable_file", "")
                syms[sid] = {"name": s.get("name", sid), "stable_file": stable}
        elif is_ultimate:
            syms = {k: {"name": v["name"], "stable_file": v["stable_file"]}
                    for k, v in ULTIMATE_SYMPHONIES.items()}
        else:
            syms = {k: {"name": v["name"], "stable_file": v["stable_file"]}
                    for k, v in PRO_SYMPHONIES.items()}
        return jsonify({"symphonies": syms, "is_admin": is_admin, "tier": tier})
    except Exception as e:
        log.exception("Symphonies error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/quote")
@login_required
def api_quote():
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    try:
        return jsonify(_quote(symbol))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/positions")
@login_required
def api_positions():
    try:
        pos = _get_positions()
        bal = _get_balances()
        result = []
        for sym, qty in pos.items():
            try:
                q = _quote(sym)
                last = q.get("last", 0)
            except Exception:
                last = 0
            result.append({"symbol": sym, "qty": qty, "last": last})
        return jsonify({"positions": result, "balances": bal})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orders")
@login_required
def api_orders():
    try:
        client = _schwab()
        acct_hash = get_account_hash(client)
        from_dt = datetime.datetime.now() - datetime.timedelta(days=7)
        to_dt = datetime.datetime.now() + datetime.timedelta(days=1)
        r = client.get_orders_for_account(
            acct_hash,
            from_entered_datetime=from_dt,
            to_entered_datetime=to_dt,
        )
        r.raise_for_status()
        raw = r.json()
        orders = []
        for o in raw:
            legs = o.get("orderLegCollection", [])
            leg_out = []
            for leg in legs:
                inst = leg.get("instrument", {})
                leg_out.append({
                    "symbol": inst.get("symbol", ""),
                    "action": leg.get("instruction", ""),
                    "qty": leg.get("quantity", 0),
                })
            orders.append({
                "orderId": o.get("orderId"),
                "orderType": o.get("orderType", ""),
                "status": o.get("status", ""),
                "price": o.get("price"),
                "legs": leg_out,
            })
        return jsonify({"orders": orders})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/order", methods=["POST"])
@login_required
def api_order():
    body = request.json or {}
    try:
        side = body.get("side", "BUY").upper()
        symbol = body.get("symbol", "").upper()
        qty = int(body.get("qty", 0))
        order_type = body.get("order_type", "LIMIT").upper()
        sess = body.get("session", "NORMAL").upper()
        dur = body.get("duration", "DAY").upper()
        limit_price = float(body["limit_price"]) if body.get("limit_price") else None

        if not symbol or qty <= 0:
            return jsonify({"error": "symbol and qty required"}), 400
        if order_type == "LIMIT" and not limit_price:
            return jsonify({"error": "limit_price required for LIMIT orders"}), 400

        order = _build_order(side, symbol, qty, order_type, sess, dur, limit_price)
        client = _schwab()
        acct_hash = get_account_hash(client)
        r = client.place_order(acct_hash, order)
        r.raise_for_status()
        log.info("Order placed: %s %d %s @ %s", side, qty, symbol,
                 f"${limit_price:.2f}" if limit_price else "MKT")
        return jsonify({"ok": True})
    except Exception as e:
        log.exception("Order error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/order/<int:order_id>", methods=["DELETE"])
@login_required
def api_cancel_order(order_id):
    try:
        client = _schwab()
        acct_hash = get_account_hash(client)
        r = client.cancel_order(order_id, acct_hash)
        r.raise_for_status()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/plan", methods=["POST"])
@login_required
def api_plan():
    body = request.json or {}
    symphony_id = body.get("symphony_id", "")
    budget = float(body.get("budget", 10000))
    exempt_str = body.get("exempt", "")
    exempt = {s.strip().upper() for s in exempt_str.split(",") if s.strip()}

    email     = session.get("email", "").lower()
    tier      = session.get("tier", "")
    tier_rank = TIER_RANKS.get(tier, 0.0)
    is_admin    = email == BLEE_ADMIN_EMAIL.lower()
    is_ultimate = tier_rank >= TIER_RANKS["ultimate"]
    allowed = ULTIMATE_SYMPHONIES if is_ultimate else PRO_SYMPHONIES
    if not is_admin and symphony_id not in allowed:
        return jsonify({"error": "Symphony not available on your plan."}), 400

    try:
        holdings = _get_holdings(symphony_id)
        current_pos = _get_positions()

        # Resolve symphony name: check known symphonies first, then live data
        sym_name = ULTIMATE_SYMPHONIES.get(symphony_id, PRO_SYMPHONIES.get(symphony_id, {})).get("name")
        if not sym_name:
            for s in _fetch_symphonies():
                if s.get("id") == symphony_id:
                    sym_name = s.get("name", symphony_id)
                    break
            sym_name = sym_name or symphony_id

        # Remove exempt symbols from plan
        filtered_holdings = [h for h in holdings if h["ticker"] not in exempt]
        rows = _compute_plan(filtered_holdings, budget, current_pos)

        # Mark exempt positions as excluded
        for row in rows:
            if row["symbol"] in exempt:
                row["action"] = "excluded"
                row["delta"] = 0
                row["limit_price"] = None
                row["est_cost"] = None

        return jsonify({
            "rows": rows,
            "source": "bleeanalytics.com",
            "symphony": sym_name,
        })
    except Exception as e:
        log.exception("Plan error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["GET"])
@login_required
def api_settings_get():
    env = _read_env_file()
    # Mask secrets — only reveal whether they're set
    return jsonify({
        "SCHWAB_API_KEY":       env.get("SCHWAB_API_KEY", ""),
        "SCHWAB_APP_SECRET":    "set" if env.get("SCHWAB_APP_SECRET") else "",
        "SCHWAB_ACCOUNT_NUMBER": env.get("SCHWAB_ACCOUNT_NUMBER", ""),
        "SCHWAB_TOKEN_PASSPHRASE": "set" if env.get("SCHWAB_TOKEN_PASSPHRASE") else "",
        "SCHWAB_CALLBACK_URL":  env.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"),
        "PORTFOLIO_VALUE":      env.get("PORTFOLIO_VALUE", "10000"),
    })


@app.route("/api/settings", methods=["POST"])
@login_required
def api_settings_post():
    updates = request.json or {}
    try:
        _write_env_file(updates)
        # Reload env for PORTFOLIO_VALUE immediately
        if "PORTFOLIO_VALUE" in updates:
            os.environ["PORTFOLIO_VALUE"] = updates["PORTFOLIO_VALUE"]
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser
    import threading

    port = int(os.environ.get("CLIENT_PORT", "5060"))
    url = f"http://127.0.0.1:{port}"
    log.info("BLEE Quant Pro Trader starting at %s", url)

    def _open():
        time.sleep(1.5)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()
    app.run(host="127.0.0.1", port=port, debug=False)
