// ============================================================
// auth_guard.js
// BLEE Quant Analytics — shared auth enforcement
//
// Usage — add these lines inside <head> of any protected page:
//
//   <!-- For Basic+ pages (signal + forecast): -->
//   <script>const BLEE_REQUIRED_TIER = "basic";</script>
//
//   <!-- For Premium-only pages: -->
//   <script>const BLEE_REQUIRED_TIER = "premium";</script>
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
  // When opened as a local file (file://) skip all auth checks entirely.
  // This lets you use the site on your own PC without Firebase being set up.
  if (window.location.protocol === "file:") {
    // Inject a small "Local / Admin" badge so you know bypass is active
    const badge = document.createElement("div");
    badge.style.cssText = [
      "position:fixed;top:0;left:0;right:0;z-index:9999",
      "background:#0a0f1e;border-bottom:1px solid #333",
      "display:flex;align-items:center;justify-content:flex-end",
      "padding:5px 18px;gap:12px;font-size:12px",
      "font-family:-apple-system,system-ui,'Segoe UI',sans-serif",
    ].join(";");
    badge.innerHTML = `
      <span style="color:#555;">Local mode</span>
      <span style="color:#f5a623;font-weight:700;">🔑 Admin (local)</span>
      <a href="admin.html" style="color:#f5a623;text-decoration:none;">Admin</a>`;
    document.body.style.paddingTop =
      (parseInt(document.body.style.paddingTop || "0") + 34) + "px";
    document.addEventListener("DOMContentLoaded", () => document.body.prepend(badge));
    return; // ← skip everything else
  }

  // ── Inject full-screen loading overlay ─────────────────────────────────
  const overlay = document.createElement("div");
  overlay.id = "blee-auth-overlay";
  overlay.innerHTML = `
    <div style="
      position:fixed;inset:0;z-index:99999;
      background:#0a0f1e;
      display:flex;flex-direction:column;
      align-items:center;justify-content:center;
      font-family:-apple-system,system-ui,'Segoe UI',sans-serif;
      color:#fff;">
      <div style="font-size:22px;font-weight:700;letter-spacing:0.05em;
                  color:#f5a623;margin-bottom:12px;">BLEE Quant</div>
      <div style="font-size:14px;color:#aaa;margin-bottom:28px;">
        Verifying membership…
      </div>
      <div style="width:36px;height:36px;border:3px solid #333;
                  border-top-color:#f5a623;border-radius:50%;
                  animation:blee-spin 0.8s linear infinite;"></div>
      <style>
        @keyframes blee-spin { to { transform:rotate(360deg); } }
      </style>
    </div>`;
  document.documentElement.appendChild(overlay);

  function removeOverlay() {
    const el = document.getElementById("blee-auth-overlay");
    if (el) el.remove();
  }

  function redirect(url, msg) {
    overlay.querySelector("div > div:nth-child(2)").textContent =
      msg || "Redirecting…";
    setTimeout(() => { window.location.href = url; }, 600);
  }

  // ── Tier hierarchy ──────────────────────────────────────────────────────
  // free: 0.5 — any registered user (just logged in)
  // manager: 10 — above premium, can access all member pages
  const TIER_RANK = { free: 0.5, basic: 1, premium: 2, manager: 10, admin: 99 };

  function tierSufficient(userTier, required) {
    // Any authenticated user satisfies a "free" requirement
    if (required === "free") return true;
    return (TIER_RANK[userTier] || 0) >= (TIER_RANK[required] || 1);
  }

  // ── Initialize Firebase ─────────────────────────────────────────────────
  if (!firebase.apps.length) {
    firebase.initializeApp(FIREBASE_CONFIG);
  }
  const auth = firebase.auth();
  const db   = firebase.firestore();

  // ── Main auth check ─────────────────────────────────────────────────────
  auth.onAuthStateChanged(async (user) => {
    if (!user) {
      redirect(BLEE_PAGES.login + "?next=" +
               encodeURIComponent(window.location.pathname),
               "Please log in to continue.");
      return;
    }

    try {
      // Admin shortcut
      if (user.email === BLEE_ADMIN_EMAIL) {
        removeOverlay();
        _bleeInjectMemberBar(user, "admin");
        return;
      }

      // Read tier from Firestore
      const snap = await db.collection("users").doc(user.uid).get();
      if (!snap.exists) {
        redirect(BLEE_PAGES.subscribe + "?reason=no_subscription",
                 "No subscription found.");
        return;
      }

      const data    = snap.data();
      const userTier = data.tier || "none";
      const status   = data.subscriptionStatus || "inactive";

      // Staff roles and free-access pages skip the subscriptionStatus check
      const isStaffTier  = userTier === "admin" || userTier === "manager";
      const isFreeAccess = (typeof BLEE_REQUIRED_TIER !== "undefined") && BLEE_REQUIRED_TIER === "free";
      if (!isStaffTier && !isFreeAccess && status !== "active" && user.email !== BLEE_ADMIN_EMAIL) {
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

      // ✓ Authorized
      removeOverlay();
      _bleeInjectMemberBar(user, userTier);

      // Update last-seen timestamp
      db.collection("users").doc(user.uid).update({
        lastLoginAt: firebase.firestore.FieldValue.serverTimestamp(),
      }).catch(() => {});

    } catch (err) {
      console.error("Auth guard error:", err);
      removeOverlay(); // fail-open so page still loads on Firestore errors
    }
  });

  // ── Member top-bar injected into every protected page ───────────────────
  // user_bar.js handles the visible bar on all pages; this function only
  // injects the admin nav link (user_bar.js deduplicates the bar itself).
  function _bleeInjectMemberBar(user, tier) {
    const bar = document.createElement("div");
    bar.id = "blee-member-bar";
    bar.style.cssText = [
      "position:fixed;top:0;left:0;right:0;z-index:9999",
      "background:#0a0f1e;border-bottom:1px solid #222",
      "display:flex;align-items:center;justify-content:flex-end",
      "padding:6px 20px;gap:12px;font-size:12px",
      "font-family:-apple-system,system-ui,'Segoe UI',sans-serif",
    ].join(";");

    const tierLabel = tier === "admin"    ? "🔑 Admin"
                    : tier === "manager"  ? "🛡️ Manager"
                    : tier === "premium"  ? "🚀 Pro"
                    : tier === "marketer" ? "🎯 Marketer"
                    : tier === "free"     ? "📧 Newsletter"
                    : "⭐ Starter";
    const tierColor = tier === "admin"    ? "#f5a623"
                    : tier === "manager"  ? "#38bdf8"
                    : tier === "premium"  ? "#facc15"
                    : tier === "marketer" ? "#a78bfa"
                    : "#4ade80";

    bar.innerHTML = `
      <span style="color:#888;">${user.email}</span>
      <span style="color:${tierColor};font-weight:600;">${tierLabel}</span>
      ${tier === "premium" || tier === "basic"
        ? `<a href="${STRIPE.portalLink}" target="_blank"
             style="color:#00a0df;text-decoration:none;">Manage plan</a>`
        : ""}
      ${tier === "marketer"
        ? `<a href="${BLEE_PAGES.marketing || 'marketing.html'}"
             style="color:#a78bfa;text-decoration:none;">My Dashboard</a>`
        : ""}
      ${tier === "admin" || tier === "manager"
        ? `<a href="${BLEE_PAGES.admin}"
             style="color:#f5a623;text-decoration:none;">Admin</a>`
        : ""}
      <button onclick="firebase.auth().signOut().then(()=>location.href='${BLEE_PAGES.home}')"
        style="background:#b00020;color:#fff;border:0;border-radius:4px;
               padding:3px 10px;cursor:pointer;font-size:11px;">
        Sign out
      </button>`;

    // Push page content down so bar doesn't overlap
    document.body.style.paddingTop =
      (parseInt(document.body.style.paddingTop || "0") + 36) + "px";
    document.body.prepend(bar);

    // ── Inject Admin link into the page's main nav (admin & manager only) ──
    if (tier === "admin" || tier === "manager") {
      document.addEventListener("DOMContentLoaded", () => _bleeInjectAdminNavLink());
      // Also try immediately in case DOM is already ready
      if (document.readyState !== "loading") _bleeInjectAdminNavLink();
    }
  }

  function _bleeInjectAdminNavLink() {
    // Already injected?
    if (document.getElementById("blee-admin-nav-link")) return;

    // Look for the page's nav links container (.nav-links is used across all pages)
    const navLinks = document.querySelector(".nav-links");
    if (!navLinks) return;

    const a = document.createElement("a");
    a.id   = "blee-admin-nav-link";
    a.href = BLEE_PAGES.admin;
    a.textContent = "⚙ Admin";
    a.style.cssText = [
      "color:#f5a623",
      "font-weight:700",
      "font-size:13px",
      "text-decoration:none",
      "border:1px solid rgba(245,166,35,0.4)",
      "border-radius:5px",
      "padding:4px 10px",
      "background:rgba(245,166,35,0.08)",
      "transition:background .15s",
    ].join(";");
    a.onmouseover = () => a.style.background = "rgba(245,166,35,0.18)";
    a.onmouseout  = () => a.style.background = "rgba(245,166,35,0.08)";

    // Insert before the last item (usually a CTA button) or just append
    const lastChild = navLinks.lastElementChild;
    navLinks.insertBefore(a, lastChild);
  }

})();
