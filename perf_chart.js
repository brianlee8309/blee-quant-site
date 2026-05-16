/* perf_chart.js
 * --------------
 * Renders the "$10,000 Backtest Growth" Chart.js chart on
 * Algorithm185History.html using the real BLEE equity curve + SPY benchmark
 * produced by update_performance.py.
 *
 * Data source: performance_data.json (written daily by update_performance.py)
 *
 * Setup on the page:
 *   1. Make sure there's a canvas:  <canvas id="growthChart"></canvas>
 *   2. Make sure Chart.js is loaded earlier in the page.
 *   3. Include this file with: <script src="perf_chart.js" defer></script>
 */
(function () {
  function init() {
    var canvas = document.getElementById("growthChart");
    if (!canvas || typeof Chart === "undefined") return;

    fetch("performance_data.json", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var curve = data && data.equity_curve;
        if (!curve || !curve.labels || !curve.blee) {
          drawFallback(canvas);
          return;
        }
        drawChart(canvas, curve, data);
      })
      .catch(function () { drawFallback(canvas); });
  }

  function drawChart(canvas, curve, data) {
    var datasets = [{
      label: "BLEE Calm Growth Model",
      data: curve.blee,
      borderColor: "#10b981",
      backgroundColor: "rgba(16,185,129,0.10)",
      borderWidth: 2.5,
      fill: true,
      tension: 0.4,
      pointRadius: 0,
      pointHoverRadius: 6,
      pointHoverBackgroundColor: "#10b981"
    }];
    if (curve.spy && curve.spy.length === curve.labels.length) {
      datasets.push({
        label: "S&P 500 (SPY)",
        data: curve.spy,
        borderColor: "#f472b6",
        backgroundColor: "rgba(244,114,182,0.06)",
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 6,
        pointHoverBackgroundColor: "#f472b6"
      });
    }

    var s3 = data.stats_3yr || {};
    var spy3 = data.spy_3yr || {};
    var subtitle =
      "BLEE " + fmtPct(s3.cum_return) + "  ($" + Math.round(s3.end_value || 0).toLocaleString() + ")"
      + (spy3.cum_return != null
          ? "  vs  SPY " + fmtPct(spy3.cum_return) + "  ($" + Math.round(spy3.end_value || 0).toLocaleString() + ")"
          : "");

    new Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels: curve.labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "top",
            labels: { color: "#cbd5e1", font: { size: 12, weight: "600" }, boxWidth: 14 }
          },
          title: {
            display: true,
            text: subtitle,
            color: "#94a3b8",
            font: { size: 12, weight: "600" },
            padding: { bottom: 10 }
          },
          tooltip: {
            backgroundColor: "rgba(15,23,42,0.95)",
            titleColor: "#f1f5f9",
            bodyColor: "#cbd5e1",
            borderColor: "rgba(255,255,255,0.08)",
            borderWidth: 1,
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + ": $" + Math.round(ctx.parsed.y).toLocaleString();
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: "#64748b", maxTicksLimit: 8, autoSkip: true },
            grid:  { color: "rgba(255,255,255,0.04)" }
          },
          y: {
            ticks: {
              color: "#64748b",
              callback: function (v) { return "$" + (v / 1000).toFixed(0) + "k"; }
            },
            grid: { color: "rgba(255,255,255,0.04)" }
          }
        }
      }
    });
  }

  function fmtPct(n) {
    if (n == null) return "—";
    var sign = n >= 0 ? "+" : "−";
    return sign + Math.abs(n).toFixed(1) + "%";
  }

  function drawFallback(canvas) {
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#64748b";
    ctx.font = "14px -apple-system,Segoe UI,sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(
      "Chart data unavailable. Run: python update_performance.py",
      canvas.width / 2,
      canvas.height / 2
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
