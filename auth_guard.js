// ============================================================
// auth_guard.js
// BLEE Quant Analytics — shared auth enforcement
//
// Usage — add these lines inside <head> of any protected page:
//
//   <!-- For Newsletter (free)+ pages (forecast / backtest): -->
//   <script>const BLEE_REQUIRED_TIER = "free";</script>
//
//   <!-- For Starter (basic)+ pages (signal): -->
//   <script>const BLEE_REQUIRED_TIER = "basic";</script>
//
//   Then include Firebase SDKs + config + this file:
//   <script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js"></script>
//   <script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-auth-compat.js"></script>
//   <script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore-compat.js"></script>
//   <script src="firebase-config.js"></script>
//   <script src="auth_guard.js"></script>
// ============================================================

(function () {
  // ── LOCAL FILE BYPASS ───────────────────────────────────────────────────
  if (window.location.protocol === "file:") {
    const badge = document.createElement("div");
    badge.style.cssText = [
      "position:fixed;top:0;left:0;right:0;z-index:9999",
      "background:#0a0f1e;border-bottom:1px solid #333",
      "display:flex;align-items:center;justify-content:flex-end",
      "padding:5px 18px;gap:12px;font-size:12px",
      "font-family:-apple-system,system-ui,'Segoe UI',sans-serif"
    ].join(";");
    badge.innerHTML =
      '<span style="color:#555;">Local mode</span>' +
      '<span style="color:#f5a623;font-weight:700;">Admin (local)</span>' +
      '<a href="admin.html" style="color:#f5a623;text-decoration:none;">Admin</a>';
    document.body.style.paddingTop =
      (parseInt(document.body.style.paddingTop || "0") + 34) + "px";
    document.addEventListener("DOMContentLoaded", function () { document.body.prepend(badge); });
    return;
  }

  // ── Inject full-screen loading overlay ─────────────────────────────────
  const overlay = document.createElement("div");
  overlay.id = "blee-auth-overlay";
  overlay.style.cssText = [
    "position:fixed",
    "top:0;left:0;right:0;bottom:0",
    "z-index:2147483647",
    "background:#0a0f1e",
    "display:flex;flex-direction:column",
    "align-items:center;justify-content:center",
    "font-family:-apple-system,system-ui,'Segoe UI',sans-serif",
    "color:#fff"
  ].join(";");
  overlay.innerHTML =
    '<div style="font-size:22px;font-weight:700;letter-spacing:0.05em;' +
    'color:#f5a623;margin-bottom:12px;">BLEE Quant</div>' +
    '<div id="blee-auth-overlay-msg" style="font-size:14px;color:#aaa;margin-bottom:28px;">' +
    'Verifying membership...</div>' +
    '<div style="width:36px;height:36px;border:3px solid #333;' +
    'border-top-color:#f5a623;border-radius:50%;' +
    'animation:blee-spin 0.8s linear infinite;"></div>' +
    '<style>' +
    '@keyframes blee-spin { to { transform:rotate(360deg); } }' +
    'html.blee-auth-locked, body.blee-auth-locked { overflow:hidden !important; }' +
    '</style>';
  document.documentElement.appendChild(overlay);
  document.documentElement.classList.add("blee-auth-locked");

  function setMsg(msg) {
    const m = document.getElementById("blee-auth-overlay-msg");
    if (m && msg) m.textContent = msg;
  }
  function removeOverlay() {
    document.documentElement.classList.remove("blee-auth-locked");
    if (document.body) document.body.classList.remove("blee-auth-locked");
    const el = document.getElementById("blee-auth-overlay");
    if (el) el.remove();
  }
  function redirect(url, msg) {
    setMsg(msg || "Redirecting...");
    setTimeout(function () { window.location.href = url; }, 600);
  }

  // ── Tier hierarchy ──────────────────────────────────────────────────────
  // free (Newsletter): 0.5 — registered free user
  // basic   (Starter): 1
  // premium (Pro):     2
  // marketer:          3 — partners; can see all member-facing pages
  // manager:          10 — staff
  // admin:            99 — super-admin
  const TIER_RANK = {
    none: 0, free: 0.5, basic: 1, premium: 2,
    marketer: 3, manager: 10, admin: 99
  };

  function tierSufficient(userTier, required) {
    if (required === "free") return true;
    return (TIER_RANK[userTier] || 0) >= (TIER_RANK[required] || 1);
  }

  function isAdminEmail(email) {
    if (!email || typeof BLEE_ADMIN_EMAIL === "undefined" || !BLEE_ADMIN_EMAIL) return false;
    return (email || "").trim().toLowerCase() ===
           (BLEE_ADMIN_EMAIL || "").trim().toLowerCase();
  }

  if (!firebase.apps.length) firebase.initializeApp(FIREBASE_CONFIG);
  const auth = firebase.auth();
  const db   = firebase.firestore();

  let _resolvedOnce    = false;
  let _restoreInFlight = false;

  auth.onAuthStateChanged(async function (user) {
    if (!user) {
      if (!_resolvedOnce && !_restoreInFlight) {
        _restoreInFlight = true;
        await new Promise(function (r) { setTimeout(r, 2000); });
        _restoreInFlight = false;
        if (auth.currentUser) return;
      }
      if (_resolvedOnce) return;
      _resolvedOnce = true;
      redirect(BLEE_PAGES.login + "?next=" +
               encodeURIComponent(window.location.pathname),
               "Please log in to continue.");
      return;
    }
    _resolvedOnce = true;

    try {
      if (isAdminEmail(user.email)) {
        removeOverlay();
        _bleeInjectMemberBar(user, "admin");
        return;
      }

      const snap = await db.collection("users").doc(user.uid).get();
      let data = snap.exists ? snap.data() : null;

      if (!data) {
        const pendingId = "pending_" + (user.email || "").replace(/[^a-zA-Z0-9]/g, "_");
        const pSnap = await db.collection("users").doc(pendingId).get().catch(function () { return null; });
        if (pSnap && pSnap.exists) data = pSnap.data();
      }

      if (!data) {
        redirect(BLEE_PAGES.subscribe + "?reason=no_subscription",
                 "No subscription found.");
        return;
      }

      const userTier = data.tier || "none";
      const status   = data.subscriptionStatus || "inactive";

      const isStaffTier  = userTier === "admin" || userTier === "manager" || userTier === "marketer";
      const isFreeAccess = (typeof BLEE_REQUIRED_TIER !== "undefined") && BLEE_REQUIRED_TIER === "free";
      if (!isStaffTier && !isFreeAccess && status !== "active") {
        redirect(BLEE_PAGES.subscribe + "?reason=inactive",
                 "Subscription inactive.");
        return;
      }

      const required = (typeof BLEE_REQUIRED_TIER !== "undefined")
        ? BLEE_REQUIRED_TIER : "basic";

      if (!tierSufficient(userTier, required)) {
        redirect(BLEE_PAGES.subscribe + "?reason=upgrade",
                 "Upgrade required for this page.");
        return;
      }

      removeOverlay();
      _bleeInjectMemberBar(user, userTier);

      db.collection("users").doc(user.uid).update({
        lastLoginAt: firebase.firestore.FieldValue.serverTimestamp()
      }).catch(function () {});

    } catch (err) {
      console.error("Auth guard error:", err);
      if (isAdminEmail(user.email)) {
        removeOverlay();
        _bleeInjectMemberBar(user, "admin");
        return;
      }
      redirect(BLEE_PAGES.login + "?next=" +
               encodeURIComponent(window.location.pathname) +
               "&reason=verify_failed",
               "Could not verify membership - please sign in again.");
    }
  });

  function _bleeInjectMemberBar(user, tier) {
    const bar = document.createElement("div");
    bar.id = "blee-member-bar";
    bar.style.cssText = [
      "position:fixed;top:0;left:0;right:0;z-index:10001",
      "background:#0a0f1e;border-bottom:1px solid #222",
      "display:flex;align-items:center;justify-content:flex-end",
      "padding:6px 20px;gap:12px;font-size:12px",
      "font-family:-apple-system,system-ui,'Segoe UI',sans-serif"
    ].join(";");

    const tierLabel = tier === "admin"    ? "Admin"
                    : tier === "manager"  ? "Manager"
                    : tier === "premium"  ? "Pro"
                    : tier === "marketer" ? "Marketer"
                    : tier === "free"     ? "Newsletter"
                    : "Starter";
    const tierColor = tier === "admin"    ? "#f5a623"
                    : tier === "manager"  ? "#38bdf8"
                    : tier === "premium"  ? "#facc15"
                    : tier === "marketer" ? "#a78bfa"
                    : "#4ade80";

    bar.innerHTML =
      '<span style="color:#888;">' + (user.email || "") + '</span>' +
      '<span style="color:' + tierColor + ';font-weight:600;">' + tierLabel + '</span>' +
      ((tier === "admin" || tier === "manager")
        ? '<a href="' + BLEE_PAGES.admin + '" ' +
          'style="color:#f5a623;text-decoration:none;">Admin</a>'
        : "") +
      '<button onclick="firebase.auth().signOut().then(function(){location.href=\'' + BLEE_PAGES.home + '\';})" ' +
        'style="background:#b00020;color:#fff;border:0;border-radius:4px;' +
        'padding:3px 10px;cursor:pointer;font-size:11px;">Sign out</button>';

    document.body.style.paddingTop =
      (parseInt(document.body.style.paddingTop || "0") + 36) + "px";
    document.body.prepend(bar);

    // Push the sticky site nav down so it doesn't overlap the fixed member bar.
    // nav.js sets #blee-site-nav to position:sticky;top:0 and z-index:10000.
    // We need sticky threshold at 36px so the nav sticks just below this bar.
    var siteNav = document.getElementById("blee-site-nav");
    if (siteNav) siteNav.style.top = "36px";
    // Mobile dropdown also needs adjusting (nav height 60px + bar height 36px)
    var mobileMenu = document.getElementById("blee-mobile-menu");
    if (mobileMenu) mobileMenu.style.top = "96px";

    if (tier === "admin" || tier === "manager") {
      document.addEventListener("DOMContentLoaded", function () { _bleeInjectAdminNavLink(); });
      if (document.readyState !== "loading") _bleeInjectAdminNavLink();
    }
  }

  function _bleeInjectAdminNavLink() {
    if (document.getElementById("blee-admin-nav-link")) return;
    const navLinks = document.querySelector(".nav-links");
    if (!navLinks) return;
    const a = document.createElement("a");
    a.id   = "blee-admin-nav-link";
    a.href = BLEE_PAGES.admin;
    a.textContent = "Admin";
    a.style.cssText = [
      "color:#f5a623","font-weight:700","font-size:13px","text-decoration:none",
      "border:1px solid rgba(245,166,35,0.4)","border-radius:5px","padding:4px 10px",
      "background:rgba(245,166,35,0.08)"
    ].join(";");
    const lastChild = navLinks.lastElementChild;
    navLinks.insertBefore(a, lastChild);
  }
})();
