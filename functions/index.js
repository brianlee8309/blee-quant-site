/**
 * BLEE Quant Analytics — Firebase Cloud Functions
 *
 * Functions:
 *   sendWelcomeEmail   — triggers on new Firebase Auth user, sends welcome email
 *   sendDailyNewsletter — HTTP callable to send newsletter to all free-tier users
 */

const functions  = require("firebase-functions");
const admin      = require("firebase-admin");
const nodemailer = require("nodemailer");

admin.initializeApp();

// ── Gmail SMTP transporter ─────────────────────────────────────────────────
// Uses the same Google Workspace App Password as alert_sender.py
const transporter = nodemailer.createTransport({
  host: "smtp.gmail.com",
  port: 587,
  secure: false,
  auth: {
    user: "brianlee1004@bleeanalytics.com",
    pass: functions.config().gmail?.app_password || "tijo thnd heao vwbc",
  },
});

// ── Email helpers ──────────────────────────────────────────────────────────

function welcomeEmailHTML(displayName) {
  const name = displayName || "there";
  return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: -apple-system, sans-serif; background: #0b1120; color: #fff; margin: 0; padding: 0; }
    .container { max-width: 580px; margin: 0 auto; padding: 40px 24px; }
    .logo { font-size: 22px; font-weight: 800; color: #fff; margin-bottom: 32px; }
    .logo span { color: #f59e0b; }
    h1 { font-size: 26px; font-weight: 800; margin-bottom: 12px; }
    p { color: #9ca3af; line-height: 1.7; font-size: 15px; }
    .highlight { color: #fff; }
    .btn { display: inline-block; background: #f59e0b; color: #000; font-weight: 800;
           padding: 14px 28px; border-radius: 8px; text-decoration: none;
           font-size: 15px; margin-top: 24px; }
    .feature { background: #111827; border: 1px solid #1f2937; border-radius: 10px;
               padding: 16px 20px; margin-top: 12px; }
    .feature-title { color: #f59e0b; font-weight: 700; font-size: 14px; margin-bottom: 4px; }
    .feature-desc { color: #9ca3af; font-size: 13px; margin: 0; }
    .footer { margin-top: 40px; padding-top: 24px; border-top: 1px solid #1f2937;
              color: #4b5563; font-size: 12px; line-height: 1.7; }
    .footer a { color: #f59e0b; text-decoration: none; }
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">BLEE <span>Quant</span></div>

    <h1>Welcome, ${name}! 👋</h1>
    <p>
      You're now part of <span class="highlight">BLEE Quant Analytics</span> —
      a quantitative research platform built to help you navigate markets with
      data-driven signals.
    </p>

    <p style="margin-top: 20px;">
      <span class="highlight">Your Newsletter & Market Forecast plan includes:</span>
    </p>

    <div class="feature">
      <div class="feature-title">📊 Daily Market Forecast</div>
      <p class="feature-desc">Our Quant Engine scores the market each day — Clear Sky, Cloudy, Rain, or Thunderstorm — so you know where conditions stand before you trade.</p>
    </div>

    <div class="feature">
      <div class="feature-title">📈 Backtest & Performance History</div>
      <p class="feature-desc">Full access to Algorithm 185 backtest results and live performance tracking since inception.</p>
    </div>

    <div class="feature">
      <div class="feature-title">🔜 Coming Soon: Daily Signal Alerts</div>
      <p class="feature-desc">Upgrade to Starter or Pro to receive daily allocation signals and auto-trade integration.</p>
    </div>

    <a href="https://bleeanalytics.com" class="btn">Go to Your Dashboard →</a>

    <div class="footer">
      <p>
        Questions? Reply to this email or contact us at
        <a href="mailto:contact@bleeanalytics.com">contact@bleeanalytics.com</a>
      </p>
      <p style="margin-top: 8px;">
        © ${new Date().getFullYear()} BLEE Quant Analytics · Educational research only<br>
        <a href="https://bleeanalytics.com/subscribe.html">Manage subscription</a>
      </p>
    </div>
  </div>
</body>
</html>
  `.trim();
}

function welcomeEmailText(displayName) {
  const name = displayName || "there";
  return `
Welcome to BLEE Quant Analytics, ${name}!

You're now on the Newsletter & Market Forecast plan. Here's what you have access to:

📊 Daily Market Forecast
   Our Quant Engine scores the market each day (Clear Sky, Cloudy, Rain, Thunderstorm)
   so you know where conditions stand before you trade.

📈 Backtest & Performance History
   Full access to Algorithm 185 backtest results and live performance tracking.

🔜 Coming Soon: Daily Signal Alerts
   Upgrade to Starter or Pro for daily allocation signals and auto-trade integration.

Go to your dashboard → https://bleeanalytics.com

Questions? Email us at contact@bleeanalytics.com

© ${new Date().getFullYear()} BLEE Quant Analytics · Educational research only
Manage subscription → https://bleeanalytics.com/subscribe.html
  `.trim();
}

// ── FUNCTION 1: Welcome email on new user signup ───────────────────────────

exports.sendWelcomeEmail = functions.auth.user().onCreate(async (user) => {
  const { email, displayName } = user;

  if (!email) {
    console.log("No email address for new user — skipping welcome email.");
    return null;
  }

  console.log(`Sending welcome email to: ${email}`);

  try {
    await transporter.sendMail({
      from:    '"BLEE Quant Analytics" <do-not-reply@bleeanalytics.com>',
      to:      email,
      subject: "Welcome to BLEE Quant Analytics 📊",
      text:    welcomeEmailText(displayName),
      html:    welcomeEmailHTML(displayName),
    });
    console.log(`✓ Welcome email sent to ${email}`);
  } catch (err) {
    console.error(`✗ Failed to send welcome email to ${email}:`, err);
  }

  return null;
});


// ── FUNCTION 2: Send newsletter to all free-tier users ─────────────────────
// Call via Firebase Admin SDK or HTTP trigger (secured by Firebase Auth check)

exports.sendNewsletter = functions.https.onCall(async (data, context) => {
  // Only allow admin users to trigger this
  if (!context.auth) {
    throw new functions.https.HttpsError("unauthenticated", "Must be signed in.");
  }

  const db        = admin.firestore();
  const callerDoc = await db.collection("users").doc(context.auth.uid).get();
  const callerTier = callerDoc.data()?.tier;

  if (!["admin", "manager"].includes(callerTier)) {
    throw new functions.https.HttpsError("permission-denied", "Admin only.");
  }

  const { subject, htmlBody, textBody } = data;
  if (!subject || !htmlBody) {
    throw new functions.https.HttpsError("invalid-argument", "subject and htmlBody required.");
  }

  // Get all free-tier users
  const snapshot = await db.collection("users")
    .where("tier", "in", ["free", "basic", "premium"])
    .get();

  const emails = [];
  snapshot.forEach(doc => {
    const d = doc.data();
    if (d.email) emails.push(d.email);
  });

  console.log(`Sending newsletter to ${emails.length} subscribers...`);

  let sent = 0, failed = 0;
  for (const email of emails) {
    try {
      await transporter.sendMail({
        from:    '"BLEE Quant Analytics" <newsletter@bleeanalytics.com>',
        to:      email,
        subject: subject,
        text:    textBody || "",
        html:    htmlBody,
      });
      sent++;
    } catch (err) {
      console.error(`✗ Failed to send to ${email}:`, err.message);
      failed++;
    }
  }

  console.log(`Newsletter done — sent: ${sent}, failed: ${failed}`);
  return { sent, failed, total: emails.length };
});
