// charts.js — Chart.js configuration helpers for the analysis page.
//
// We expose a small object on window.GaitMindCharts with three render
// functions, each of which lazily creates the chart on first call and just
// updates the dataset on subsequent calls. This avoids the canvas-already-in-
// use error that Chart.js throws if you try to instantiate twice.

(function () {
  const charts = {};

  // Shared visual defaults to match the dark UI.
  const palette = {
    grid:  "rgba(255,255,255,0.06)",
    axis:  "rgba(230,236,246,0.55)",
    blue:  "#5b8cff",
    green: "#34d399",
    amber: "#f59e0b",
    red:   "#ef4444",
    purple:"#7b5bff",
  };

  Chart.defaults.color = palette.axis;
  Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  Chart.defaults.borderColor = palette.grid;

  function destroyIfExists(key) {
    if (charts[key]) { charts[key].destroy(); charts[key] = null; }
  }

  // -----------------------------------------------------------------
  // Signal chart: vertical acceleration trace, OR step intervals if
  // that's all we have.
  // -----------------------------------------------------------------
  function renderSignalChart(ctx, payload) {
    destroyIfExists("signal");
    const intervals = payload?.metrics?.step_intervals || [];
    const stepTimes = payload?.metrics?.step_times || [];

    let labels, dataset, title;
    if (stepTimes.length > 1 && intervals.length > 0) {
      labels = intervals.map((_, i) => `Step ${i + 1}`);
      dataset = {
        label: "Step interval (s)",
        data: intervals,
        borderColor: palette.blue,
        backgroundColor: "rgba(91,140,255,0.15)",
        tension: 0.25,
        fill: true,
        pointRadius: 3,
      };
      title = "Detected step intervals";
    } else {
      // Fallback for manual mode: synthesize a small illustrative wave from
      // the cadence / variability the user typed in, so the panel isn't blank.
      const cad = payload?.metrics?.cadence || 110;
      const period = 60.0 / cad;
      const cv  = (payload?.metrics?.variability || 0) / 100.0;
      labels = Array.from({ length: 60 }, (_, i) => (i * 0.1).toFixed(1));
      dataset = {
        label: "Illustrative gait waveform",
        data: labels.map((_, i) => {
          const t = i * 0.1;
          const jitter = 1 + (Math.random() - 0.5) * cv * 2;
          return Math.sin((2 * Math.PI * t) / (period * jitter));
        }),
        borderColor: palette.blue,
        backgroundColor: "rgba(91,140,255,0.10)",
        tension: 0.35, fill: true, pointRadius: 0,
      };
      title = "Illustrative gait waveform (manual entry)";
    }

    charts.signal = new Chart(ctx, {
      type: "line",
      data: { labels, datasets: [dataset] },
      options: {
        responsive: true,
        plugins: {
          legend: { display: true },
          title:  { display: true, text: title, color: palette.axis },
        },
        scales: {
          x: { grid: { color: palette.grid } },
          y: { grid: { color: palette.grid } },
        },
      },
    });
  }

  // -----------------------------------------------------------------
  // Per-feature contribution bar chart.
  // -----------------------------------------------------------------
  function renderContributionChart(ctx, payload) {
    destroyIfExists("contrib");
    const contributions = payload?.analysis?.contributions || {};
    const labels = Object.keys(contributions);
    const data = labels.map((k) => contributions[k]);
    const colors = labels.map((k) => {
      const v = contributions[k];
      if (v >= 0.5) return palette.red;
      if (v >= 0.2) return palette.amber;
      return palette.green;
    });

    charts.contrib = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Contribution to abnormality score",
          data,
          backgroundColor: colors,
          borderRadius: 6,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: palette.grid } },
          y: { beginAtZero: true, suggestedMax: 1, grid: { color: palette.grid } },
        },
      },
    });
  }

  // -----------------------------------------------------------------
  // Symmetry chart: left vs right step time.
  // -----------------------------------------------------------------
  function renderSymmetryChart(ctx, payload) {
    destroyIfExists("symmetry");
    const m = payload?.analysis?.metrics || {};
    const left  = m.mean_left_step_time;
    const right = m.mean_right_step_time;

    const hasBoth = typeof left === "number" && typeof right === "number";
    const labels = ["Left", "Right"];
    const data   = hasBoth ? [left, right] : [0, 0];

    charts.symmetry = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Mean step time (s)",
          data,
          backgroundColor: [palette.blue, palette.purple],
          borderRadius: 6,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        plugins: {
          legend: { display: false },
          title: {
            display: true,
            text: hasBoth
              ? `Symmetry index: ${m.symmetry}%`
              : "Left/right step times not provided",
            color: palette.axis,
          },
        },
        scales: {
          x: { grid: { color: palette.grid }, beginAtZero: true },
          y: { grid: { color: palette.grid } },
        },
      },
    });
  }

  window.GaitMindCharts = {
    renderSignalChart,
    renderContributionChart,
    renderSymmetryChart,
  };
})();
