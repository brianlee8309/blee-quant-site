/* analytics.js — shared Google Analytics (gtag.js) loader for BLEE Quant pages.
 *
 * Include on any page with:
 *     <script src="analytics.js"></script>
 *
 * (Skip on index.html — that page loads gtag inline.)
 *
 * Measurement ID: G-JYD4LP56QM
 *
 * What it does
 * ------------
 *   1. Idempotently injects the gtagmanager loader <script async src="..."></script>
 *      so multiple includes don't double-load it.
 *   2. Defines the global `gtag()` function and pushes the standard init events.
 *
 * Notes
 * -----
 *   - This file is safe to load before or after page interactive — the loader
 *     is async and gtag() queues calls into dataLayer until the loader runs.
 *   - To stop tracking a specific page, just remove the <script src="analytics.js">
 *     tag from that page; nothing else depends on this file.
 */
(function () {
  // Don't double-init if the page already loaded gtag inline (e.g. index.html).
  if (window.__bleeAnalyticsLoaded) return;
  window.__bleeAnalyticsLoaded = true;

  var GA_ID = "G-JYD4LP56QM";

  // dataLayer + gtag stub must exist before the async loader runs.
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };

  // Inject the gtagmanager loader if it isn't already on the page.
  if (!document.querySelector('script[src*="googletagmanager.com/gtag/js"]')) {
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + GA_ID;
    document.head.appendChild(s);
  }

  gtag("js", new Date());
  gtag("config", GA_ID);
})();
