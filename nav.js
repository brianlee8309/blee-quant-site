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
    { href: "marketDailySummary.html",  label: "Market Forecast" },
    { href: "index2.html",              label: "Daily Signal"    },
    { href: "Algorithm185History.html", label: "Backtest"        },
    { href: "performance1.html",        label: "Performance"     },
    { href: "contact.html",             label: "Contact"         },
  ];

  var LANGS = [
    { code: "en", flag: "🇺🇸", label: "EN" },
    { code: "ja", flag: "🇯🇵", label: "JP" },
    { code: "vi", flag: "🇻🇳", label: "VI" },
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
      "display:none;position:fixed;top:60px;left:0;right:0;z-index:9999;",
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
  } else {
    document.addEventListener("DOMContentLoaded", inject);
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
      var link = document.getElementElementById("blee-nav-signin-link");
      if (link) link.style.display = user ? "none" : "";
    });
  }
  setTimeout(pollForAuth, 100);

})();
