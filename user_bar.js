// ============================================================
// user_bar.js  –  BLEE Quant Analytics
// Shows signed-in email, role badge, and Sign Out on every page.
// Include AFTER firebase-app/auth/firestore compat SDKs + firebase-config.js
// No defer needed — initialises lazily after Firebase is ready.
// ============================================================

(function bleeuserbar() {
  var MAX_WAIT = 6000;   // give up after 6 s if Firebase never appears
  var waited   = 0;

  // ── Wait for Firebase SDKs + config to be available ─────────────────────
  function waitForFirebase() {
    if (typeof firebase === "undefined" || typeof FIREBASE_CONFIG === "undefined") {
      waited += 200;
      if (waited < MAX_WAIT) setTimeout(waitForFirebase, 200);
      return;
    }
    init();
  }

  function init() {
    try {
      if (!firebase.apps.length) firebase.initializeApp(FIREBASE_CONFIG);
    } catch (e) { /* already initialised — fine */ }

    var auth = firebase.auth();
    var db;
    try { db = firebase.firestore(); } catch (e) { db = null; }

    auth.onAuthStateChanged(function(user) {
      // Remove any bar we previously injected
      var old = document.getElementById("blee-user-bar");
      if (old) {
        document.body.style.paddingTop =
          Math.max(0, parseInt(document.body.style.paddingTop || "0") - 38) + "px";
        old.remove();
      }

      // Toggle the nav Sign In link — show when logged out, hide when logged in
      (function toggleSignInLink() {
        var link = document.getElementById("nav-signin-link");
        if (!link) {
          if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", toggleSignInLink);
          }
          return;
        }
        link.style.display = user ? "none" : "";
      })();

      if (!user) return;  // not signed in — show nothing

      // If auth_guard.js already drew its own bar, piggy-back only an admin
      // link into the nav rather than adding a duplicate bar.
      if (document.getElementById("blee-member-bar")) {
        injectAdminNavLink(getTierFromGuardBar());
        return;
      }

      // Read tier from Firestore then draw the bar
      var tier = "basic";
      var _adminEmail   = (typeof BLEE_ADMIN_EMAIL !== "undefined" ? BLEE_ADMIN_EMAIL : "");
      var _userEmailLc  = (user.email || "").trim().toLowerCase();
      var _adminEmailLc = (_adminEmail || "").trim().toLowerCase();
      if (_adminEmailLc && _userEmailLc === _adminEmailLc) {
        tier = "admin";
        drawBar(user.email, tier);
      } else if (db) {
        db.collection("users").doc(user.uid).get()
          .then(function(snap) {
            if (snap.exists) tier = snap.data().tier || "basic";
            drawBar(user.email, tier);
          })
          .catch(function() { drawBar(user.email, tier); });
      } else {
        drawBar(user.email, tier);
      }
    });
  }

  // ── Colour / label map ────────────────────────────────────────────────────
  var TIERS = {
    admin:    { label: "🔑 Admin",    color: "#f5a623" },
    manager:  { label: "🛡️ Manager",  color: "#38bdf8" },
    premium:  { label: "🚀 Pro",      color: "#facc15" },
    marketer: { label: "🎯 Marketer", color: "#a78bfa" },
    basic:    { label: "⭐ Starter",  color: "#4ade80" },
    free:     { label: "📧 Newsletter", color: "#94a3b8" },
  };

  function drawBar(email, tier) {
    // Guard: don't double-draw
    if (document.getElementById("blee-user-bar")) return;

    var info    = TIERS[tier] || { label: "Member", color: "#4ade80" };
    var isStaff = tier === "admin" || tier === "manager";
    var adminUrl = (typeof BLEE_PAGES !== "undefined" && BLEE_PAGES.admin) || "admin.html";
    var loginUrl = (typeof BLEE_PAGES !== "undefined" && BLEE_PAGES.login) || "login.html";

    var bar = document.createElement("div");
    bar.id = "blee-user-bar";

    // Inline all styles so nothing in the page can override them
    bar.style.cssText = [
      "position:fixed",
      "top:0",
      "left:0",
      "right:0",
      "height:38px",
      "z-index:2147483647",          // max possible z-index
      "background:#0a0f1e",
      "border-bottom:1px solid rgba(255,255,255,0.12)",
      "display:flex",
      "align-items:center",
      "justify-content:flex-end",
      "padding:0 16px",
      "gap:12px",
      "font-size:13px",
      "font-weight:400",
      "line-height:1",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
      "box-shadow:0 2px 16px rgba(0,0,0,0.5)",
      "box-sizing:border-box",
    ].join(";");

    bar.innerHTML =
      '<span style="color:#64748b;font-size:12px;flex-shrink:0;">Signed in as</span>' +
      '<span style="color:#e2e8f0;font-weight:500;max-width:200px;overflow:hidden;' +
            'text-overflow:ellipsis;white-space:nowrap;" title="' + email + '">' +
        email +
      '</span>' +
      '<span style="color:' + info.color + ';font-weight:700;font-size:11px;' +
            'background:' + info.color + '22;border:1px solid ' + info.color + '55;' +
            'border-radius:999px;padding:2px 10px;white-space:nowrap;flex-shrink:0;">' +
        info.label +
      '</span>' +
      (isStaff
        ? '<a href="' + adminUrl + '" style="color:#f5a623;font-size:12px;font-weight:700;' +
          'text-decoration:none;border:1px solid rgba(245,166,35,0.4);border-radius:4px;' +
          'padding:3px 10px;background:rgba(245,166,35,0.1);flex-shrink:0;">⚙ Admin</a>'
        : '') +
      '<button id="blee-signout-btn" style="background:#7f1d1d;color:#fca5a5;' +
        'border:1px solid #991b1b;border-radius:5px;padding:4px 13px;cursor:pointer;' +
        'font-size:12px;font-weight:600;white-space:nowrap;font-family:inherit;' +
        'flex-shrink:0;line-height:1.4;">Sign Out</button>';

    var btn = bar.querySelector("#blee-signout-btn");
    btn.onmouseover = function() { this.style.background = "#991b1b"; };
    btn.onmouseout  = function() { this.style.background = "#7f1d1d"; };
    btn.onclick     = function() {
      firebase.auth().signOut().finally
        ? firebase.auth().signOut().finally(function() { window.location.href = loginUrl; })
        : firebase.auth().signOut().then(function() { window.location.href = loginUrl; })
                                   .catch(function() { window.location.href = loginUrl; });
    };

    // Ensure body exists before injecting
    function doInject() {
      if (!document.body) { setTimeout(doInject, 50); return; }
      // Push body down so fixed bar doesn't cover content
      document.body.style.paddingTop =
        (parseInt(document.body.style.paddingTop || "0") + 38) + "px";
      document.body.insertBefore(bar, document.body.firstChild);

      // Also try to inject Admin link into the page nav
      if (isStaff) setTimeout(function() { injectAdminNavLink(tier); }, 300);
    }
    doInject();
  }

  // ── Inject ⚙ Admin into the page's own .nav-links (for admin/manager) ───
  function injectAdminNavLink(tier) {
    if (tier !== "admin" && tier !== "manager") return;
    if (document.getElementById("blee-admin-nav-link")) return;
    var navLinks = document.querySelector(".nav-links");
    if (!navLinks) return;
    var adminUrl = (typeof BLEE_PAGES !== "undefined" && BLEE_PAGES.admin) || "admin.html";
    var a = document.createElement("a");
    a.id   = "blee-admin-nav-link";
    a.href = adminUrl;
    a.textContent = "⚙ Admin";
    a.style.cssText = "color:#f5a623;font-weight:700;font-size:13px;text-decoration:none;" +
      "border:1px solid rgba(245,166,35,0.4);border-radius:5px;padding:4px 10px;" +
      "background:rgba(245,166,35,0.08);";
    var last = navLinks.lastElementChild;
    navLinks.insertBefore(a, last);
  }

  // Read tier from auth_guard's injected bar text (fallback)
  function getTierFromGuardBar() {
    var bar = document.getElementById("blee-member-bar");
    if (!bar) return "basic";
    var text = bar.textContent || "";
    if (text.indexOf("Admin")   !== -1) return "admin";
    if (text.indexOf("Manager") !== -1) return "manager";
    return "basic";
  }

  // ── Kick off ─────────────────────────────────────────────────────────────
  waitForFirebase();

})()