// ============================================================
// firebase-config.js
// BLEE Quant Analytics — Firebase + Stripe configuration
//
// HOW TO FILL THIS IN (one-time setup):
//
// 1. Go to https://console.firebase.google.com
// 2. Create project → name it "blee-quant"
// 3. Project Settings (gear icon) → General → Your apps → Add app → Web (</>)
// 4. Copy the firebaseConfig object values below
// 5. Authentication → Sign-in method → Enable "Email/Password"
// 6. Firestore Database → Create database → Start in production mode
//
// Stripe:
// 7. Go to https://stripe.com → create account
// 8. Products → Add product → "Basic" $19/mo + "Premium" $49/mo
// 9. Each product → Payment link → copy URL into STRIPE below
// 10. Billing portal → activate → copy link into STRIPE.portalLink
// ============================================================

const FIREBASE_CONFIG = {
  apiKey:            "PASTE_YOUR_API_KEY_HERE",
  authDomain:        "PASTE_YOUR_PROJECT_ID.firebaseapp.com",
  projectId:         "PASTE_YOUR_PROJECT_ID",
  storageBucket:     "PASTE_YOUR_PROJECT_ID.appspot.com",
  messagingSenderId: "PASTE_YOUR_SENDER_ID",
  appId:             "PASTE_YOUR_APP_ID",
};

// Admin email — this account gets full admin dashboard access
const BLEE_ADMIN_EMAIL = "brianlee1004@gmail.com";

// Stripe hosted links (no backend needed)
const STRIPE = {
  basicLink:   "https://buy.stripe.com/PASTE_BASIC_PAYMENT_LINK",
  premiumLink: "https://buy.stripe.com/PASTE_PREMIUM_PAYMENT_LINK",
  portalLink:  "https://billing.stripe.com/p/login/PASTE_PORTAL_LINK",
};

// Site pages — relative paths work for both local file:// and GitHub Pages
const BLEE_PAGES = {
  login:     "login.html",
  subscribe: "subscribe.html",
  home:      "index.html",
  signal:    "index2.html",
  forecast:  "marketDailySummary.html",
  admin:     "admin.html",
};
