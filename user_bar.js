// ============================================================
// user_bar.js
// BLEE Quant Analytics — universal signed-in status bar
//
// Include on ANY page (public or protected).
// Shows the logged-in email, role badge, and Sign Out button.
// If the auth_guard.js bar already exists, this script skips
// injection to avoid duplication.
//
// Usage — add inside <head> AFTER firebase SDKs + firebase-config.js:
//   <script src="user_bar.js" defer></script>
// ============================================================

(function () {
  const TIER_LABEL = {
    admin:    { text: "🔑 Admin",    color: "#f5a623" },
    manager:  { text: "🛡️ Manager",  color: "#38bdf8" },
    premium:  { text: "🚀 Pro",      color: "#facc15" },
    marketer: { text: "🎯 Marketer", color: "#a78bfa" },
    basic:    { text: "⭐ Starter",  color: "#4ade80" },
    free:     { text: "📧 Free",     color: "#94a3b8" },
  };

  function injectBar(email, tier) {
    // Skip if auth_guard already injected its bar
    if (document.getElementById("blee-member-bar")) return;
    if (document.getElementById("blee-user-bar"))   return;

    const info  = TIER_LABEL[tier] || { text: "Member", color: "#4ade80" };
    const isStaff = tier === "admin" || tier === "manager";

    const bar = document.createElement("div");
    bar.id = "blee-user-bar";
    bar.style.cssText = [
      "position:fixed;top:0;left:0;right:0;z-index:99998",
      "background:#0a0f1e",
      "border-bottom:1px solid rgba(255,255,255,0.1)",
      "display:flex;align-items:center;justify-content:flex-end",
      "padding:0 18px",
      "height:38px",
      "gap:14px",
      "font-size:13px",
      "font-family:-apple-system,system-ui,'Segoe UI',sans-serif",
      "box-shadow:0 2px 12px rgba(0,0,0,0.4)",
    ].join(";");

    bar.innerHTML = `
      <span style="color:#64748b;font-size:12px;">Signed in as</span>
      <span style="color:#e2e8f0;font-weight:500;max-width:220px;
                   overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
            title="${email}">${email}</span>
      <span style="
        color:${info.color};font-weight:700;font-size:12px;
        background:${info.color}1a;
        border:1px solid ${info.color}44;
        border-radius:999px;padding:2px 10px;white-space:nowrap;">
        ${info.text}
      </span>
      ${isStaff ? `<a href="${(window.BLEE_PAGES && BLEE_PAGES.admin) || "admin.html"}"
        style="color:#f5a623;font-size:12px;font-weight:600;text-decoration:none;
               border:1px solid rgba(245,166,35,0.35);border-radius:4px;
               padding:2px 9px;background:rgba(245,166,35,0.07);">
        ⚙ Admin</a>` : ""}
      <button id="blee-signout-btn"
        style="background:#7f1d1d;color:#fca5a5;border:1px solid #991b1b;
               border-radius:5px;padding:3px 12px;cursor:pointer;
               font-size:12px;font-weight:600;white-space:nowrap;
               font-family:inherit;transition:background .15s;">
        Sign Out
      </button>`;

    // Hover effect on sign out button
    const btn = bar.querySelector("#blee-signout-btn");
    btn.onmouseover = () => btn.style.background = "#991b1b";
    btn.onmouseout  = () => btn.style.background = "#7f1d1d";
    btn.onclick     = () => {
      firebase.auth().signOut().finally(() => {
        window.location.href = (window.BLEE_PAGES && BLEE_PAGES.login) || "login.html";
      });
    };

    // Push body down so bar doesn't overlap content
    document.body.style.paddingTop =
      (parseInt(document.body.style.paddingTop || "0") + 38) + "px";
    document.body.prepend(bar);
  }

  function removeBar() {
    const el = document.getElementById("blee-user-bar");
    if (!el) return;
    const added = 38;
    document.body.style.paddingTop =
      Math.max(0, parseInt(document.body.style.paddingTop || "0") - added) + "px";
    el.remove();
  }

  function start() {
    if (!window.firebase || !window.FIREBASE_CONFIG) {
      // Retry briefly if Firebase hasn't loaded yet
      setTimeout(start, 150);
      return;
    }
    if (!firebase.apps.length) firebase.initializeApp(FIREBASE_CONFIG);

    const auth = firebase.auth();
    const db   = firebase.firestore();

    auth.onAuthStateChanged(async (user) => {
      removeBar();
      if (!user) return;

      let tier = "basic";
      if (user.email === (window.BLEE_ADMIN_EMAIL || "")) {
        tier = "admin";
      } else {
        try {
          const snap = await db.collection("users").doc(user.uid).get();
          if (snap.exists) tier = snap.data().tier || "basic";
        } catch (e) { /* silent — still show bar without tier */ }
      }

      // Wait for DOMContentLoaded if needed
      if (document.body) {
        injectBar(user.email, tier);
      } else {
        document.addEventListener("DOMContentLoaded", () => injectBar(user.email, tier));
      }
    });
  }

  // Kick off after page loads so it never blocks rendering
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
