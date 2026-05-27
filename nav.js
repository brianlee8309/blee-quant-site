// ============================================================
// nav.js  —  BLEE Quant Analytics shared navigation
//
// Drop-in for every sub-page (NOT index.html which has its own).
// Include AFTER firebase-config.js:
//   <script src="firebase-config.js"></script>
//   <script src="nav.js"></script>
//
// Automatically:
//  • Injects the full blee-nav bar
//  • Highlights the current page link
//  • Shows "Sign In" when logged out, hides it when logged in
//    (user_bar.js / auth_guard.js handle the top member strip)
//  • Fires applyLang() if defined on the page (i18n support)
//  • Provides a mobile hamburger dropdown
// ============================================================

(function () {

  // ── Nav definition ────────────────────────────────────────────────────────
  var LINKS = [
    { href: "index.html",               label: "Home"            },
    { href: "mission.html",             label: "Our Mission"     },
    { href: "retirement_calculator.html", label: "Freedom Calc"  },
    { href: "marketDailySummary.html",  label: "Market Forecast" },
    { href: "index2.html",              label: "Daily Signal"    },
    { href: "Algorithm185History.html", label: "Backtest"        },
    { href: "performance1.html",        label: "Performance"     },
    { href: "contact.html",             label: "Contact"         },
  ];

  var LANGS = [
    { code: "en", flag: "🇺🇸", label: "EN" },
    { code: "ja", flag: "🇯🇵", label: "JP" },
    { code: "ko", flag: "🇰🇷", label: "KR" },
  ];

  // ── CSS ───────────────────────────────────────────────────────────────────
  var CSS = [
    "#blee-site-nav{",
      "position:sticky;top:0;z-index:10000;",
      "background:#0d1829;",
      "border-bottom:1px solid rgba(255,255,255,0.07);",
      "padding:0 28px;height:60px;",
      "display:flex;align-items:center;justify-content:space-between;",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;",
      "box-sizing:border-box;",
    "}",
    "#blee-site-nav .blee-nav-logo{",
      "font-size:17px;font-weight:800;color:#fff;text-decoration:none;",
      "white-space:nowrap;flex-shrink:0;letter-spacing:-0.01em;",
    "}",
    "#blee-site-nav .blee-nav-logo span{color:#f59e0b;}",
    "#blee-site-nav .blee-nav-links{",
      "display:flex;align-items:center;gap:22px;flex:1;justify-content:center;",
    "}",
    "#blee-site-nav .blee-nav-links a{",
      "color:rgba(255,255,255,0.55);font-size:13.5px;font-weight:500;",
      "text-decoration:none;white-space:nowrap;transition:color .15s;",
    "}",
    "#blee-site-nav .blee-nav-links a:hover{color:#fff;}",
    "#blee-site-nav .blee-nav-links a.active{color:#fff;font-weight:700;}",
    "#blee-site-nav .blee-nav-right{",
      "display:flex;align-items:center;gap:8px;flex-shrink:0;",
    "}",
    "#blee-site-nav .blee-nav-subscribe{",
      "background:#f59e0b;color:#000;padding:6px 14px;border-radius:6px;",
      "font-size:13px;font-weight:700;text-decoration:none;white-space:nowrap;",
      "transition:background .15s;",
    "}",
    "#blee-site-nav .blee-nav-subscribe:hover{background:#fbbf24;}",
    "#blee-site-nav .blee-nav-signin{",
      "color:rgba(255,255,255,0.7);font-size:13px;font-weight:500;",
      "text-decoration:none;white-space:nowrap;padding:5px 10px;",
      "border:1px solid rgba(255,255,255,0.2);border-radius:6px;transition:all .15s;",
    "}",
    "#blee-site-nav .blee-nav-signin:hover{color:#fff;border-color:rgba(255,255,255,0.5);}",
    "#blee-site-nav .blee-lang-btn{",
      "background:transparent;border:1px solid rgba(255,255,255,0.18);",
      "color:rgba(255,255,255,0.6);font-size:11px;font-weight:700;",
      "padding:4px 8px;border-radius:5px;cursor:pointer;font-family:inherit;",
      "transition:all .15s;",
    "}",
    "#blee-site-nav .blee-lang-btn.active{background:#f59e0b;color:#000;border-color:#f59e0b;}",
    "#blee-site-nav .blee-lang-btn:hover:not(.active){background:rgba(255,255,255,0.10);color:#fff;}",

    // Mobile hamburger button
    "#blee-site-nav .blee-nav-hamburger{",
      "display:none;flex-direction:column;justify-content:center;gap:5px;",
      "background:transparent;border:none;cursor:pointer;padding:6px;",
    "}",
    "#blee-site-nav .blee-nav-hamburger span{",
      "display:block;width:22px;height:2px;background:#fff;border-radius:2px;",
      "transition:all .25s;",
    "}",

    // Mobile dropdown menu
    "#blee-mobile-menu{",
      "display:none;position:fixed;top:98px;left:0;right:0;z-index:9999;",
      "background:#0d1829;border-bottom:1px solid rgba(255,255,255,0.1);",
      "padding:12px 0;flex-direction:column;",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;",
    "}",
    "#blee-mobile-menu.open{display:flex;}",
    "#blee-mobile-menu a{",
      "color:rgba(255,255,255,0.7);font-size:14px;font-weight:500;",
      "text-decoration:none;padding:11px 24px;border-bottom:1px solid rgba(255,255,255,0.05);",
      "transition:background .15s;",
    "}",
    "#blee-mobile-menu a:hover{background:rgba(255,255,255,0.05);color:#fff;}",
    "#blee-mobile-menu a.active{color:#f59e0b;font-weight:700;}",
    "#blee-mobile-menu .mob-subscribe{",
      "background:#f59e0b;color:#000;margin:10px 20px;border-radius:6px;",
      "font-weight:700;text-align:center;border-bottom:none;",
    "}",
    "#blee-mobile-menu .mob-langs{",
      "display:flex;gap:8px;padding:10px 20px;",
    "}",

    // Responsive breakpoints
    "@media(max-width:960px){",
      "#blee-site-nav .blee-nav-links{display:none;}",
      "#blee-site-nav .blee-lang-btn{display:none;}",
      "#blee-site-nav .blee-nav-hamburger{display:flex;}",
    "}",
    "@media(max-width:640px){",
      "#blee-site-nav{padding:0 16px;}",
      "#blee-site-nav .blee-nav-subscribe{display:none;}",
      "#blee-site-nav .blee-nav-signin{display:none;}",
    "}",
  ].join("");

  // ── Detect current page ───────────────────────────────────────────────────
  var currentPage = (window.location.pathname.split("/").pop() || "index.html").toLowerCase();

  // ── Build nav HTML ────────────────────────────────────────────────────────
  function buildLinks(isMobile) {
    return LINKS.map(function (l) {
      var active = (currentPage === l.href.toLowerCase()) ? " active" : "";
      var cls = active ? ' class="active"' : "";
      if (isMobile && l.href === "subscribe.html") return ""; // subscribe shown separately in mobile
      return '<a href="' + l.href + '"' + cls + ">" + l.label + "</a>";
    }).join("");
  }

  function buildLangButtons(cls) {
    return LANGS.map(function (l, i) {
      return '<button class="' + cls + (i === 0 ? " active" : "") +
             '" data-lang="' + l.code + '">' + l.flag + " " + l.label + "</button>";
    }).join("");
  }

  var navHTML =
    '<nav id="blee-site-nav">' +
      '<a href="index.html" class="blee-nav-logo">BLEE <span>Quant</span></a>' +
      '<div class="blee-nav-links">' + buildLinks(false) + "</div>" +
      '<div class="blee-nav-right">' +
        '<a href="subscribe.html" class="blee-nav-subscribe">Subscribe</a>' +
        '<a href="login.html" class="blee-nav-signin" id="blee-nav-signin-link" style="display:none;">Sign In</a>' +
        buildLangButtons("blee-lang-btn") +
        '<button class="blee-nav-hamburger" id="blee-nav-hamburger" aria-label="Menu">' +
          "<span></span><span></span><span></span>" +
        "</button>" +
      "</div>" +
    "</nav>" +
    '<div id="blee-mobile-menu">' +
      buildLinks(true) +
      '<a href="subscribe.html" class="mob-subscribe">Subscribe</a>' +
      '<div class="mob-langs">' + buildLangButtons("blee-lang-btn") + "</div>" +
    "</div>";

  // ── Inject into page ──────────────────────────────────────────────────────
  function inject() {
    if (document.getElementById("blee-site-nav")) return; // already present

    // Inject CSS
    var styleEl = document.createElement("style");
    styleEl.id  = "blee-nav-styles";
    styleEl.textContent = CSS;
    document.head.appendChild(styleEl);

    // Inject HTML before first child of body
    var wrap = document.createElement("div");
    wrap.innerHTML = navHTML;
    while (wrap.firstChild) {
      document.body.insertBefore(wrap.firstChild, document.body.firstChild);
    }

    // NOTE: No paddingTop needed here. position:sticky keeps the nav in the
    // normal document flow, so it naturally pushes content below it. Adding
    // paddingTop here would double-count the nav's height and create a gap.
    // auth_guard.js adds its own 36px paddingTop for the fixed member bar.

    // ── Wire language buttons ─────────────────────────────────────────────
    document.querySelectorAll(".blee-lang-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        // Update active state on ALL lang buttons (desktop + mobile)
        document.querySelectorAll(".blee-lang-btn").forEach(function (b) {
          b.classList.toggle("active", b.dataset.lang === btn.dataset.lang);
        });
        // Fire page's own i18n system if present
        if (typeof applyLang === "function")  applyLang(btn.dataset.lang);
        if (typeof i18nApply === "function")  i18nApply(btn.dataset.lang);
      });
    });

    // ── Wire hamburger ────────────────────────────────────────────────────
    var hamburger  = document.getElementById("blee-nav-hamburger");
    var mobileMenu = document.getElementById("blee-mobile-menu");
    if (hamburger && mobileMenu) {
      hamburger.addEventListener("click", function () {
        var isOpen = mobileMenu.classList.toggle("open");
        // Animate the three bars into an X
        var spans = hamburger.querySelectorAll("span");
        if (spans.length === 3) {
          spans[0].style.transform = isOpen ? "translateY(7px) rotate(45deg)"  : "";
          spans[1].style.opacity   = isOpen ? "0" : "";
          spans[2].style.transform = isOpen ? "translateY(-7px) rotate(-45deg)" : "";
        }
      });
      // Close mobile menu on link click
      mobileMenu.querySelectorAll("a").forEach(function (a) {
        a.addEventListener("click", function () {
          mobileMenu.classList.remove("open");
        });
      });
    }
  }

  // Run immediately if body is ready, otherwise wait for DOM
  if (document.body) {
    inject();
    initTicker();
  } else {
    document.addEventListener("DOMContentLoaded", function() { inject(); initTicker(); });
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // MARKET TICKER BAR  —  DOW / S&P 500 / NASDAQ
  // ═══════════════════════════════════════════════════════════════════════════
  var _TICKERS = [
    { id: "bt-dji", sym: "^DJI",  label: "DOW"     },
    { id: "bt-spx", sym: "^GSPC", label: "S&P 500" },
    { id: "bt-ndx", sym: "^IXIC", label: "NASDAQ"  },
  ];
  var _tickerTimer = null;

  var TICKER_CSS = [
    "#blee-ticker-bar{",
      "position:sticky;top:60px;z-index:9998;",
      "background:#050d1a;",
      "border-bottom:1px solid rgba(255,255,255,0.07);",
      "padding:0 28px;height:38px;",
      "display:flex;align-items:center;justify-content:center;gap:32px;overflow:hidden;",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;",
      "box-sizing:border-box;",
    "}",
    ".bt-item{display:flex;align-items:center;gap:6px;white-space:nowrap;}",
    ".bt-name{color:rgba(255,255,255,0.42);font-size:10px;font-weight:700;",
              "text-transform:uppercase;letter-spacing:.06em;}",
    ".bt-price{color:#e2e8f0;font-size:12.5px;font-weight:600;}",
    ".bt-chg{font-size:11.5px;font-weight:500;}",
    ".bt-chg.up{color:#4ade80;}.bt-chg.down{color:#f87171;}.bt-chg.flat{color:rgba(255,255,255,0.35);}",
    ".bt-sep{color:rgba(255,255,255,0.18);font-size:11px;margin:0 2px;}",
    ".bt-ext{font-size:11px;font-weight:500;}",
    ".bt-ext.up{color:#86efac;}.bt-ext.down{color:#fca5a5;}.bt-ext.flat{color:rgba(255,255,255,0.3);}",
    ".bt-state{font-size:9px;padding:1px 6px;border-radius:3px;font-weight:700;letter-spacing:.05em;}",
    ".bt-state.open{background:#15803d;color:#fff;}",
    ".bt-state.pre{background:#1e40af;color:#fff;}",
    ".bt-state.post{background:#6d28d9;color:#fff;}",
    ".bt-state.closed{background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.45);}",
    ".bt-div{width:1px;height:20px;background:rgba(255,255,255,0.09);flex-shrink:0;}",
    "#bt-time{margin-left:auto;font-size:10px;color:rgba(255,255,255,0.22);white-space:nowrap;}",
    "@media(max-width:780px){#blee-ticker-bar{gap:14px;padding:0 14px;}#bt-time{display:none;}}",
    "@media(max-width:520px){.bt-div,.bt-ext,.bt-sep{display:none;}}",
  ].join("");

  function _fmtN(n, dec) {
    if (n == null || isNaN(n)) return "—";
    dec = dec == null ? 2 : dec;
    return n >= 1000
      ? n.toLocaleString("en-US", {minimumFractionDigits: dec, maximumFractionDigits: dec})
      : n.toFixed(dec);
  }

  function _renderItem(elId, name, price, chg, pct, state, extPrice, extChg, extPct) {
    var el = document.getElementById(elId);
    if (!el) return;
    var dir   = chg  >  0 ? "up"   : chg  < 0 ? "down"  : "flat";
    var sign  = chg  >= 0 ? "+"    : "";
    var sLbl  = { REGULAR:"OPEN", PRE:"PRE", POST:"POST" }[state] || "CLOSED";
    var sCls  = { REGULAR:"open", PRE:"pre",  POST:"post" }[state] || "closed";

    var extHTML = "";
    if (state !== "REGULAR" && extPrice != null) {
      var ed   = extChg > 0 ? "up" : extChg < 0 ? "down" : "flat";
      var es   = extChg >= 0 ? "+" : "";
      extHTML  = '<span class="bt-sep">▸</span>'
               + '<span class="bt-ext ' + ed + '">'
               + _fmtN(extPrice) + " " + es + _fmtN(extPct) + "%"
               + "</span>";
    }

    el.innerHTML =
      '<span class="bt-name">' + name + "</span>"
    + '<span class="bt-price">' + _fmtN(price) + "</span>"
    + '<span class="bt-chg ' + dir + '">'
        + sign + _fmtN(Math.abs(chg)) + " (" + sign + _fmtN(pct) + "%)"
      + "</span>"
    + extHTML
    + '<span class="bt-state ' + sCls + '">' + sLbl + "</span>";
  }

  function _processQuotes(data) {
    var results = ((data.quoteResponse || {}).result) || [];
    if (!results.length) throw new Error("empty results");
    results.forEach(function(q, i) {
      var t = _TICKERS[i]; if (!t) return;
      var st   = q.marketState || "CLOSED";
      var extP = null, extC = null, extPt = null;
      if      (st === "PRE"  && q.preMarketPrice)  { extP = q.preMarketPrice;  extC = q.preMarketChange;  extPt = q.preMarketChangePercent;  }
      else if (st === "POST" && q.postMarketPrice) { extP = q.postMarketPrice; extC = q.postMarketChange; extPt = q.postMarketChangePercent; }
      _renderItem(t.id, t.label,
        q.regularMarketPrice, q.regularMarketChange, q.regularMarketChangePercent,
        st, extP, extC, extPt);
    });
    var timeEl = document.getElementById("bt-time");
    if (timeEl) {
      timeEl.textContent = new Date().toLocaleTimeString("en-US",
        { hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
    }
    var st0   = results.length ? (results[0].marketState || "CLOSED") : "CLOSED";
    var delay = st0 === "REGULAR" ? 30000 : (st0 === "PRE" || st0 === "POST") ? 120000 : 300000;
    if (_tickerTimer) clearTimeout(_tickerTimer);
    _tickerTimer = setTimeout(_fetchTicker, delay);
  }

  function _fetchTicker() {
    var syms   = _TICKERS.map(function(t) { return encodeURIComponent(t.sym); }).join(",");
    var yahooQ = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=" + syms
               + "&fields=regularMarketPrice,regularMarketChange,regularMarketChangePercent"
               + ",preMarketPrice,preMarketChange,preMarketChangePercent"
               + ",postMarketPrice,postMarketChange,postMarketChangePercent,marketState";

    // Try direct fetch first; fall back to allorigins CORS proxy
    fetch(yahooQ, { headers: { Accept: "application/json" } })
      .then(function(r) {
        if (!r.ok) throw new Error("direct HTTP " + r.status);
        return r.json();
      })
      .then(_processQuotes)
      .catch(function() {
        // Direct blocked by CORS — route through allorigins proxy
        var proxyUrl = "https://api.allorigins.win/get?url=" + encodeURIComponent(yahooQ);
        return fetch(proxyUrl)
          .then(function(r) {
            if (!r.ok) throw new Error("proxy HTTP " + r.status);
            return r.json();
          })
          .then(function(wrapper) {
            // allorigins returns { contents: "<json string>", status: {...} }
            var data = JSON.parse(wrapper.contents);
            _processQuotes(data);
          })
          .catch(function(e) {
            console.warn("[BLEE ticker] proxy failed:", e.message);
            if (_tickerTimer) clearTimeout(_tickerTimer);
            _tickerTimer = setTimeout(_fetchTicker, 120000);
          });
      });
  }

  function initTicker() {
    // Inject CSS
    var s = document.createElement("style");
    s.id  = "blee-ticker-styles";
    s.textContent = TICKER_CSS;
    document.head.appendChild(s);

    // Build placeholder HTML for the three indices
    var items = _TICKERS.map(function(t, i) {
      return (i > 0 ? '<div class="bt-div"></div>' : "")
           + '<div class="bt-item" id="' + t.id + '">'
           + '<span class="bt-name">' + t.label + '</span>'
           + '<span class="bt-price">…</span>'
           + "</div>";
    }).join("");
    var barHTML = '<div id="blee-ticker-bar">' + items + '<span id="bt-time"></span></div>';

    // Insert right after #blee-site-nav
    var nav = document.getElementById("blee-site-nav");
    if (nav && nav.parentNode) {
      var wrap = document.createElement("div");
      wrap.innerHTML = barHTML;
      nav.parentNode.insertBefore(wrap.firstChild, nav.nextSibling);
    }

    // Fetch live data
    _fetchTicker();
  }

  // ── Sign In link toggle (Firebase auth state) ─────────────────────────────
  // Wait for Firebase to be initialised (by firebase-config.js or auth_guard.js)
  var _authPollCount = 0;
  function pollForAuth() {
    if (typeof firebase === "undefined" || !firebase.apps || !firebase.apps.length) {
      if (++_authPollCount < 40) setTimeout(pollForAuth, 250);
      return;
    }
    firebase.auth().onAuthStateChanged(function (user) {
      var link = document.getElementById("blee-nav-signin-link");
      if (link) link.style.display = user ? "none" : "";
    });
  }
  setTimeout(pollForAuth, 100);

})();
