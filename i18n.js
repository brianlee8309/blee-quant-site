/* i18n.js — shared language-switcher driver for BLEE Quant pages.
 *
 * What it does
 * ------------
 *   1. Initializes the (hidden) Google Translate widget.
 *   2. Wires up any element with class="lang-btn" (and data-lang="en|ja|vi|ko")
 *      to switch the page language.
 *   3. Remembers the user's choice in localStorage (key "blee-lang") and
 *      re-applies it on every subsequent page load.
 *   4. Hides Google Translate's top banner so the layout doesn't jump.
 *
 * How to use on a page
 * --------------------
 *   1. Drop the four flag buttons into your nav (typical place: after the
 *      Subscribe link):
 *
 *        <div class="nav-translate">
 *          <button class="lang-btn active" data-lang="en">🇺🇸 EN</button>
 *          <button class="lang-btn"        data-lang="ja">🇯🇵 JP</button>
 *          <button class="lang-btn"        data-lang="vi">🇻🇳 VI</button>
 *          <button class="lang-btn"        data-lang="ko">🇰🇷 KR</button>
 *        </div>
 *
 *   2. Add the matching CSS (or reuse this default block) somewhere in
 *      your stylesheet:
 *
 *        .nav-translate { display:flex; align-items:center; gap:3px;
 *                         margin-left:14px;
 *                         border-left:1px solid rgba(255,255,255,0.12);
 *                         padding-left:14px; }
 *        .lang-btn { background:transparent;
 *                    border:1px solid rgba(255,255,255,0.18);
 *                    color:rgba(255,255,255,0.60);
 *                    font-size:11.5px; font-weight:700;
 *                    padding:4px 8px; border-radius:5px; cursor:pointer;
 *                    transition:all .15s; white-space:nowrap;
 *                    font-family:inherit; letter-spacing:0.03em; }
 *        .lang-btn:hover  { background:rgba(255,255,255,0.10); color:#fff;
 *                           border-color:rgba(255,255,255,0.35); }
 *        .lang-btn.active { background:#f59e0b; color:#000;
 *                           border-color:#f59e0b; }
 *        @media (max-width:780px) { .nav-translate { display:none; } }
 *
 *   3. Include the script at the END of your <body>:
 *
 *        <script src="i18n.js"></script>
 *
 *      i18n.js will inject the hidden Google Translate element and the
 *      Google Translate loader for you.
 */

(function () {
  // Already loaded on this page? Don't double-init.
  if (window.__bleeI18nLoaded) return;
  window.__bleeI18nLoaded = true;

  /* ── 1. Inject hidden Google Translate mount + loader ─────────────── */
  if (!document.getElementById('google_translate_element')) {
    var hidden = document.createElement('div');
    hidden.id = 'google_translate_element';
    hidden.style.display = 'none';
    document.body.appendChild(hidden);
  }
  // Global callback Google's script will call once loaded.
  window.googleTranslateElementInit = function () {
    new google.translate.TranslateElement(
      { pageLanguage: 'en', includedLanguages: 'en,ja,vi,ko', autoDisplay: false },
      'google_translate_element'
    );
  };
  if (!document.querySelector('script[src*="translate.google.com/translate_a/element.js"]')) {
    var s = document.createElement('script');
    s.src = '//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
    s.async = true;
    document.body.appendChild(s);
  }

  /* ── 2. Hide Google's top toolbar banner ──────────────────────────── */
  var style = document.createElement('style');
  style.textContent = '.goog-te-banner-frame{display:none!important;}'
                    + 'body{top:0!important;}'
                    + '.skiptranslate{display:none!important;}';
  document.head.appendChild(style);

  /* ── 3. setLang ─ flip the active state, persist, fire Google ─────── */
  function setLang(lang) {
    document.querySelectorAll('.lang-btn').forEach(function (b) {
      b.classList.toggle('active', b.dataset.lang === lang);
    });
    try { localStorage.setItem('blee-lang', lang); } catch (e) {}

    if (lang === 'en') {
      // Wipe googtrans cookie and reload to show source language.
      document.cookie = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/';
      document.cookie = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=' + location.hostname;
      location.reload();
      return;
    }

    var sel = document.querySelector('.goog-te-combo');
    if (sel) {
      sel.value = lang;
      sel.dispatchEvent(new Event('change'));
      return;
    }
    // Widget not loaded yet: set cookie & reload (works on GitHub Pages).
    document.cookie = 'googtrans=/en/' + lang + '; path=/';
    document.cookie = 'googtrans=/en/' + lang + '; path=/; domain=' + location.hostname;
    location.reload();
  }
  window.setLang = setLang;  // exposed in case a page wants to call it manually

  /* ── 4. Wire up the flag buttons (idempotent — safe to re-run) ──── */
  function wireButtons() {
    document.querySelectorAll('.lang-btn').forEach(function (btn) {
      if (btn.__bleeWired) return;
      btn.__bleeWired = true;
      btn.addEventListener('click', function () { setLang(btn.dataset.lang); });
    });
  }
  wireButtons();

  /* ── 5. Restore the user's saved language after the widget loads ─── */
  var saved = (function () {
    try { return localStorage.getItem('blee-lang'); } catch (e) { return null; }
  })();
  if (saved && saved !== 'en') {
    var attempts = 0;
    var maxAttempts = 30;
    var t = setInterval(function () {
      attempts++;
      var sel = document.querySelector('.goog-te-combo');
      if (sel) {
        sel.value = saved;
        sel.dispatchEvent(new Event('change'));
        document.querySelectorAll('.lang-btn').forEach(function (b) {
          b.classList.toggle('active', b.dataset.lang === saved);
        });
        clearInterval(t);
      } else if (attempts >= maxAttempts) {
        clearInterval(t);
      }
    }, 300);
  }
})();
