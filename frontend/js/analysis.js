// analysis.js — controller for the Analysis page.
//
// Responsibilities:
//   * Tab switching between CSV and manual input.
//   * Drag-and-drop file handling.
//   * Calling /api/analyze/* and rendering the result.
//   * Wiring the feedback buttons to /api/feedback.
//   * Loading and refreshing the cognitive-memory pane.

(function () {
  const $ = (sel) => document.querySelector(sel);

  // ---- State -------------------------------------------------------------
  let pickedFile = null;
  let lastResult = null;     // last full analyze response

  // ---- Tabs --------------------------------------------------------------
  const tabCsv    = $("#tab-csv");
  const tabManual = $("#tab-manual");
  const paneCsv   = $("#pane-csv");
  const paneManual= $("#pane-manual");

  function showTab(which) {
    const csv = which === "csv";
    tabCsv.classList.toggle("active", csv);
    tabManual.classList.toggle("active", !csv);
    paneCsv.classList.toggle("hidden", !csv);
    paneManual.classList.toggle("hidden", csv);
  }
  tabCsv.addEventListener("click", () => showTab("csv"));
  tabManual.addEventListener("click", () => showTab("manual"));

  // ---- File picking + drag/drop -----------------------------------------
  const drop = $("#drop");
  const fileInput = $("#file-input");
  const fileName  = $("#file-name");
  const pickLink  = $("#pick-file");

  pickLink.addEventListener("click", (e) => {
    e.preventDefault();
    fileInput.click();
  });
  fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

  ["dragover", "dragenter"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, () => drop.classList.remove("drag")));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });

  function setFile(f) {
    pickedFile = f || null;
    fileName.textContent = f ? f.name : "No file selected";
  }

  // ---- Run buttons -------------------------------------------------------
  $("#run-csv").addEventListener("click", runCsv);
  $("#run-manual").addEventListener("click", runManual);
  $("#use-sample").addEventListener("click", runSample);

  async function runCsv() {
    if (!pickedFile) {
      alert("Please choose a CSV file first (or click 'Use sample dataset').");
      return;
    }
    const fd = new FormData();
    fd.append("file", pickedFile);
    await runAnalyze("/api/analyze/csv", { method: "POST", body: fd });
  }

  async function runSample() {
    try {
      const res = await fetch(GaitMind.apiBase + "/api/sample-csv");
      if (!res.ok) throw new Error("could not fetch sample");
      const blob = await res.blob();
      pickedFile = new File([blob], "sample_gait.csv", { type: "text/csv" });
      fileName.textContent = pickedFile.name + "  (sample)";
      await runCsv();
    } catch (e) {
      alert("Could not load sample: " + e.message);
    }
  }

  async function runManual() {
    const payload = {
      step_time_variability: numOrNull("#m-var"),
      stride_length:         numOrNull("#m-stride"),
      cadence:               numOrNull("#m-cad"),
      symmetry_index:        numOrNull("#m-sym"),
      harmonic_ratio:        numOrNull("#m-hr"),
    };
    await runAnalyze("/api/analyze/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  function numOrNull(sel) {
    const v = $(sel).value;
    return v === "" ? null : Number(v);
  }

  async function runAnalyze(url, opts) {
    setBusy(true);
    try {
      const data = await GaitMind.api(url, opts);
      lastResult = data;
      renderResults(data);
      await refreshMemory();
    } catch (e) {
      alert("Analysis failed: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  function setBusy(b) {
    document.querySelectorAll(".btn").forEach((el) => el.disabled = b);
  }

  // ---- Render ------------------------------------------------------------
  function renderResults(data) {
    $("#results").classList.remove("hidden");

    // Score meter.
    const score = Number(data.analysis.score) || 0;
    const threshold = Number(data.analysis.threshold) || 50;
    const label = data.critique.final_label;
    $("#score-num").textContent = score.toFixed(1);
    $("#score-fill").style.width = Math.max(0, Math.min(100, score)) + "%";
    const pill = $("#label-pill");
    pill.textContent = label;
    pill.className = "label-pill " + label;
    $("#confidence-text").textContent =
      `  ·  confidence ${(data.critique.confidence * 100).toFixed(0)}%`;
    $("#threshold-text").textContent =
      `  ·  threshold ${threshold.toFixed(1)}`;

    // Reasoning trace.
    const trace = $("#trace");
    trace.innerHTML = "";
    trace.appendChild(traceBlock("planner",  "Planner",  formatPlan(data.plan)));
    trace.appendChild(traceBlock("analyzer", "Analyzer", formatAnalysis(data.analysis)));
    trace.appendChild(traceBlock("critic",   "Critic",   formatCritique(data.critique)));

    $("#final-explanation").innerHTML = escapeHtml(
      data.critique.final_explanation
    ).replace(/\n/g, "<br>");

    // Charts.
    GaitMindCharts.renderSignalChart($("#chart-signal"), data.analysis);
    GaitMindCharts.renderContributionChart($("#chart-contrib"), data);
    GaitMindCharts.renderSymmetryChart($("#chart-symmetry"), data);

    // Reset feedback status.
    $("#fb-status").textContent = "";
  }

  function traceBlock(cls, title, innerHtml) {
    const el = document.createElement("div");
    el.className = "trace__step " + cls;
    el.innerHTML = `
      <div>
        <span class="trace__chip ${cls}">${title}</span>
      </div>
      <div class="trace__body">${innerHtml}</div>
    `;
    return el;
  }

  function formatPlan(plan) {
    const steps = (plan.steps || [])
      .map((s) => `<li><b>${escapeHtml(s.title)}</b> — ${escapeHtml(s.detail)}</li>`)
      .join("");
    return `
      <div><b>Plan rationale:</b> ${escapeHtml(plan.rationale || "")}</div>
      <ul>${steps}</ul>
      <div class="muted small" style="margin-top:6px;">
        Modules scheduled: ${(plan.modules_to_run || []).map(escapeHtml).join(", ") || "none"}
      </div>`;
  }

  function formatAnalysis(a) {
    const traceLines = (a.trace || [])
      .map((t) => `<li>${escapeHtml(t)}</li>`)
      .join("");
    return `
      <div>${escapeHtml(a.explanation || "")}</div>
      <ul>${traceLines}</ul>`;
  }

  function formatCritique(c) {
    const notes = (c.notes || []).map((n) => `<li>${escapeHtml(n)}</li>`).join("");
    const adj   = (c.adjustments || []).map((n) => `<li>${escapeHtml(n)}</li>`).join("");
    return `
      <div><b>Confidence:</b> ${(c.confidence * 100).toFixed(0)}%</div>
      ${adj   ? `<div style="margin-top:6px;"><b>Adjustments:</b><ul>${adj}</ul></div>` : ""}
      ${notes ? `<div style="margin-top:6px;"><b>Notes:</b><ul>${notes}</ul></div>` : ""}`;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  // ---- Feedback ----------------------------------------------------------
  $("#fb-correct").addEventListener("click", () => {
    if (!lastResult) return;
    submitFeedback(lastResult.critique.final_label);
  });
  $("#fb-wrong-normal").addEventListener("click",   () => submitFeedback("normal"));
  $("#fb-wrong-abnormal").addEventListener("click", () => submitFeedback("abnormal"));

  async function submitFeedback(userLabel) {
    if (!lastResult) return;
    setBusy(true);
    try {
      const update = await GaitMind.api("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prediction_id: lastResult.prediction_id,
          user_label: userLabel,
        }),
      });
      const summary = update.agreed
        ? "✓ Recorded — agent agrees with you, no weight change needed."
        : "✓ Recorded — feature weights and threshold updated.";
      $("#fb-status").textContent = summary;
      await refreshMemory();
    } catch (e) {
      $("#fb-status").textContent = "Feedback failed: " + e.message;
    } finally {
      setBusy(false);
    }
  }

  // ---- Memory pane -------------------------------------------------------
  $("#reset-memory").addEventListener("click", async () => {
    if (!confirm("Reset all learned weights and history?")) return;
    await GaitMind.api("/api/memory/reset", { method: "POST" });
    await refreshMemory();
    $("#fb-status").textContent = "Memory reset.";
  });

  async function refreshMemory() {
    try {
      const mem = await GaitMind.api("/api/memory");
      const w = mem.feature_weights || {};
      const wEl = $("#weights");
      wEl.innerHTML = "";
      Object.entries(w).forEach(([name, val]) => {
        const div = document.createElement("div");
        div.className = "weight";
        div.innerHTML = `
          <div class="weight__name">${escapeHtml(name)}</div>
          <div class="weight__val">${Number(val).toFixed(2)}</div>`;
        wEl.appendChild(div);
      });

      const stats = mem.stats || {};
      const t = mem.thresholds || {};
      const kv = $("#memory-stats");
      kv.innerHTML = `
        <dt>Abnormal cutoff</dt><dd>${Number(t.abnormal_cutoff || 50).toFixed(2)}</dd>
        <dt>Total feedback</dt><dd>${stats.total_feedback || 0}</dd>
        <dt>Agreements</dt><dd>${stats.agreements || 0}</dd>
        <dt>Disagreements</dt><dd>${stats.disagreements || 0}</dd>
        <dt>History size</dt><dd>${(mem.history || []).length}</dd>`;
    } catch (e) {
      // memory pane is non-critical; swallow errors silently.
      console.warn("memory refresh failed", e);
    }
  }

  // Initial pull.
  refreshMemory();
})();
