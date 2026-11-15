"use strict";

const $ = (id) => document.getElementById(id);
const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  table:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10M15 10v10"/>',
  report:
    '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h6"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 8.5a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4M12 16h.01"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5"/>',
  upload: '<path d="M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',
  wallet:
    '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 6V4h14v2M16 11h5v5h-5z"/>',
  bag: '<path d="M5 7h14l1 14H4zM9 8V5a3 3 0 0 1 6 0v3"/>',
  chart: '<path d="M4 4v16h17M7 14l4-4 4 2 5-7M16 5h4v4"/>',
  box: '<path d="m12 3 9 5v9l-9 5-9-5V8zM3 8l9 5 9-5M12 13v9M7 5.7l9 5"/>',
  reset: '<path d="M3 10a9 9 0 1 1 2 8M3 4v6h6"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
};
document.querySelectorAll("[data-icon]").forEach((el) => {
  el.innerHTML = `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[el.dataset.icon] || ""}</svg>`;
});
let sourceFile = null;
let currentData = null;
let busy = false;
let tablePage = 0;
let toastTimer;
const number = (n) => new Intl.NumberFormat("en-US").format(n);
const escapeHTML = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (value, compact = false) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currentData?.currency || "USD",
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : 2,
    minimumFractionDigits: compact ? 0 : 2,
  }).format(value);
const shortDate = (value) =>
  new Date(`${value}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
const monthName = (value) =>
  new Date(`${value}-01T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  });

function setBusy(value, message = "") {
  busy = value;
  document.body.classList.toggle("is-loading", value);
  $("main").setAttribute("aria-busy", String(value));
  ["browse-button", "sample-button", "replace-button", "file-input"].forEach(
    (id) => ($(id).disabled = value),
  );
  $("filters")
    .querySelectorAll("input,select,button")
    .forEach((el) => (el.disabled = value));
  $("export-button").disabled = value || !currentData?.metrics.rows;
  $("status").textContent = message;
  if (value && message) showToast(message, 0);
  else $("toast").hidden = true;
}
function showError(message) {
  $("alert").textContent = message;
  $("alert").hidden = false;
  $("alert").scrollIntoView({ block: "nearest", behavior: "smooth" });
}
function showToast(message, duration = 5000) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  if (duration)
    toastTimer = setTimeout(() => ($("toast").hidden = true), duration);
}
function bodyFor(file, filters = {}) {
  const body = new FormData();
  body.append("file", file);
  for (const key of ["start", "end", "region"])
    body.append(key, filters[key] || "");
  return body;
}
async function responseError(response) {
  try {
    return (
      (await response.json()).error || "Something went wrong. Please try again."
    );
  } catch {
    return response.status === 413
      ? "This upload is too large. Keep your CSV below 5 MB."
      : "The server could not complete this request. Please try again.";
  }
}
async function analyzeFile(file, filters = {}, replacement = false) {
  if (busy) return;
  $("alert").hidden = true;
  if (!file.name.toLowerCase().endsWith(".csv")) {
    showError("Please choose a .csv file.");
    return;
  }
  if (file.size > 5 * 1024 * 1024 - 4096) {
    showError("This upload is too large. Keep your CSV below 5 MB.");
    return;
  }
  setBusy(true, "Cleaning your CSV and preparing the dashboard…");
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      body: bodyFor(file, filters),
    });
    if (!response.ok) throw new Error(await responseError(response));
    const data = await response.json();
    currentData = data;
    sourceFile = file;
    tablePage = 0;
    renderDashboard(replacement);
    setBusy(
      false,
      `${number(data.summary.clean_rows)} clean rows ready. Dashboard updated.`,
    );
    if (replacement) {
      const heading = document.querySelector("h1");
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "instant" });
      showToast(
        `${number(data.summary.clean_rows)} clean rows. Your dashboard is ready.`,
      );
    }
  } catch (error) {
    setBusy(false);
    showError(
      error instanceof TypeError
        ? "Unable to reach the server. Check that the app is running, then retry."
        : error.message,
    );
  }
}
function renderDashboard(replacement) {
  const d = currentData,
    s = d.summary;
  $("upload-section").hidden = true;
  $("empty-notes").hidden = true;
  $("dashboard").hidden = false;
  ["step-upload", "step-clean", "step-report"].forEach((id) =>
    $(id).classList.add("current"),
  );
  $("filename").textContent = d.filename;
  $("source-detail").textContent =
    `${number(s.input_rows)} source rows · ${d.currency} · ${sourceFile.size < 1024 ? sourceFile.size + " B" : (sourceFile.size / 1024).toFixed(1) + " KB"}`;
  $("q-read").textContent = number(s.input_rows);
  $("q-clean").textContent = number(s.clean_rows);
  $("q-duplicates").textContent = number(s.duplicate_rows);
  $("q-invalid").textContent = number(s.removed_rows - s.duplicate_rows);
  $("q-normalized").textContent = number(s.normalized_rows);
  $("quality-description").textContent = "Automatically checked & prepared";
  const reasons = {
    duplicate_rows: "Duplicate row",
    missing_required: "Missing required value",
    invalid_date: "Invalid date",
    invalid_number: "Invalid quantity or price",
    malformed_rows: "Malformed row",
  };
  const counts = Object.entries(reasons)
    .map(
      ([key, name]) => `<li>${name}: <strong>${number(s[key])}</strong></li>`,
    )
    .join("");
  const issues = s.issues
    .map((i) => `<li>CSV line ${i.line}: ${reasons[i.reason]}</li>`)
    .join("");
  $("quality-details").innerHTML =
    `<p>Cleaning covers the full source file. Removed rows have exactly one reason; normalized rows are retained, not removed.</p><ul>${counts}</ul><p>${number(s.missing_order_ids)} retained rows have no order ID and each counts as one order. ${number(s.missing_optional_rows)} rows use a default for an optional field (order ID, region or category).</p><p>Whitespace is trimmed, dates standardized and grouped numbers parsed. Exact duplicates are checked across recognized fields; product names remain case-sensitive.</p>${s.ignored_columns.length ? `<p>Ignored columns: ${s.ignored_columns.map(escapeHTML).join(", ")}. Revenue always uses quantity × unit price.</p>` : ""}${issues ? `<details><summary>First ${s.issues.length} excluded rows (CSV line numbers)</summary><ul>${issues}</ul></details>` : "<p>No rows were excluded.</p>"}`;
  if (replacement) {
    $("quality-details").hidden = true;
    $("quality-toggle").setAttribute("aria-expanded", "false");
    $("region-filter").replaceChildren(
      new Option("All regions", ""),
      ...d.available_regions.map((region) => new Option(region, region)),
    );
  }
  $("start-date").value = d.filters.start || d.full_range.start;
  $("end-date").value = d.filters.end || d.full_range.end;
  $("region-filter").value = d.filters.region;
  $("range-caption").textContent = d.date_range.start
    ? `${shortDate(d.date_range.start)} – ${shortDate(d.date_range.end)}`
    : "No matching sales";
  $("m-revenue").textContent = money(
    d.metrics.revenue,
    d.metrics.revenue >= 1e9,
  );
  $("m-revenue").title = money(d.metrics.revenue);
  $("m-orders").textContent = number(d.metrics.orders);
  $("m-average").textContent = money(
    d.metrics.average_order,
    d.metrics.average_order >= 1e8,
  );
  $("m-average").title = money(d.metrics.average_order);
  $("m-units").textContent = number(d.metrics.units);
  $("revenue-note").textContent =
    `${number(d.metrics.rows)} sales rows · ${d.currency}`;
  $("no-results").hidden = Boolean(d.metrics.rows);
  $("chart-currency").textContent = `All amounts in ${d.currency}`;
  const peak = d.trend.reduce(
    (best, item) => (item.revenue > (best?.revenue ?? -1) ? item : best),
    null,
  );
  $("trend-note").textContent = peak
    ? `Peak month: ${monthName(peak.month)} · ${money(peak.revenue)}`
    : "No revenue in this selection";
  renderTrend();
  renderProducts();
  renderRegions();
  renderTable();
}
function renderTrend() {
  const trend = currentData.trend;
  if (!trend.length) {
    $("trend-chart").innerHTML =
      '<div class="empty-chart">No data for this period</div>';
    return;
  }
  const w = Math.max(280, $("trend-chart").clientWidth - 30),
    h = 215,
    left = 52,
    right = 24,
    top = 18,
    bottom = 37;
  const max = Math.max(...trend.map((p) => p.revenue), 1) * 1.15;
  const x = (i) =>
    trend.length === 1
      ? (w + left - right) / 2
      : left + (i * (w - left - right)) / (trend.length - 1);
  const y = (v) => h - bottom - (v / max) * (h - top - bottom);
  const points = trend.map((p, i) => `${x(i)},${y(p.revenue)}`).join(" ");
  const baseline = h - bottom;
  let svg = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="trend-title trend-desc"><title id="trend-title">Monthly revenue in ${currentData.currency}</title><desc id="trend-desc">${escapeHTML(trend.length <= 24 ? trend.map((p) => `${monthName(p.month)}: ${money(p.revenue)}`).join("; ") : `${trend.length} monthly values. Focus chart points for individual values.`)}</desc><defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#c9ead5" stop-opacity=".65"/><stop offset="100%" stop-color="#eaf6ee" stop-opacity=".1"/></linearGradient></defs>`;
  for (let i = 0; i < 5; i++) {
    const value = (max * i) / 4,
      py = y(value);
    svg += `<line x1="${left}" y1="${py}" x2="${w - right}" y2="${py}" stroke="#e9eeea" stroke-dasharray="3 5"/><text x="${left - 9}" y="${py + 3}" text-anchor="end" font-size="11" fill="#637360">${escapeHTML(money(value, true))}</text>`;
  }
  svg += `<polygon points="${x(0)},${baseline} ${points} ${x(trend.length - 1)},${baseline}" fill="url(#area-fill)"/><polyline points="${points}" fill="none" stroke="#4c9271" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`;
  const labelEvery = Math.max(1, Math.ceil(trend.length / (w < 400 ? 3 : 7)));
  trend.forEach((p, i) => {
    if (
      i === trend.length - 1 ||
      (i % labelEvery === 0 && (i === 0 || x(trend.length - 1) - x(i) > 45))
    )
      svg += `<text x="${x(i)}" y="${h - 12}" text-anchor="middle" font-size="11" fill="#637360">${escapeHTML(monthName(p.month))}</text>`;
    svg += `<circle class="chart-point" cx="${x(i)}" cy="${y(p.revenue)}" r="${trend.length > 24 ? 2 : 4}" tabindex="0" data-index="${i}" aria-label="${escapeHTML(monthName(p.month) + ": " + money(p.revenue))}"><title>${escapeHTML(monthName(p.month) + ": " + money(p.revenue))}</title></circle>`;
  });
  svg +=
    '<g class="chart-tooltip" visibility="hidden" aria-hidden="true"><rect width="160" height="30" rx="5"/><text x="10" y="19"></text></g></svg>';
  $("trend-chart").innerHTML = svg;
  const tooltip = $("trend-chart").querySelector(".chart-tooltip");
  $("trend-chart")
    .querySelectorAll(".chart-point")
    .forEach((point) => {
      const show = () => {
        const i = Number(point.dataset.index);
        tooltip.setAttribute(
          "transform",
          `translate(${Math.max(0, Math.min(w - 160, x(i) - 80))},${Math.max(0, y(trend[i].revenue) - 40)})`,
        );
        tooltip.querySelector("text").textContent =
          `${monthName(trend[i].month)} · ${money(trend[i].revenue, true)}`;
        tooltip.setAttribute("visibility", "visible");
      };
      const hide = () => tooltip.setAttribute("visibility", "hidden");
      point.addEventListener("mouseenter", show);
      point.addEventListener("focus", show);
      point.addEventListener("mouseleave", hide);
      point.addEventListener("blur", hide);
    });
}
function bar(value, color) {
  return `<svg class="bar-svg" viewBox="0 0 100 5" preserveAspectRatio="none" aria-hidden="true"><rect width="100" height="5" rx="2.5" fill="#f0f4ee"/><rect width="${Math.max(0, Math.min(100, value))}" height="5" rx="2.5" fill="${color}"/></svg>`;
}
function renderProducts() {
  const products = currentData.products;
  const max = products[0]?.revenue || 1;
  const colors = ["#72a783", "#8bb796", "#a2c5a7", "#b8d2b5", "#ccdfc7"];
  $("products-chart").innerHTML = products.length
    ? products
        .map(
          (p, i) =>
            `<div class="product-row"><div class="product-label"><span class="product-name" title="${escapeHTML(p.name)}"><small>0${i + 1}</small>${escapeHTML(p.name)}</span><strong>${escapeHTML(money(p.revenue, p.revenue >= 1e6))}</strong></div>${bar((p.revenue / max) * 100, colors[i])}</div>`,
        )
        .join("")
    : '<div class="empty-chart">No products in this selection</div>';
}
function renderRegions() {
  $("regions-chart").innerHTML = currentData.regions.length
    ? currentData.regions
        .map((r) => {
          const share = currentData.metrics.revenue
            ? (r.revenue / currentData.metrics.revenue) * 100
            : 0;
          return `<div class="region-row"><div class="region-label"><span title="${escapeHTML(r.name)}">${escapeHTML(r.name)}</span><strong>${escapeHTML(money(r.revenue, r.revenue >= 1e6))} <span>· ${share.toFixed(1)}%</span></strong></div>${bar(share, "#9ab699")}</div>`;
        })
        .join("")
    : '<div class="empty-chart">No regions in this selection</div>';
  $("region-total").textContent = money(
    currentData.metrics.revenue,
    currentData.metrics.revenue >= 1e8,
  );
}
function renderTable() {
  const rows = currentData.preview;
  const pageSize = 5;
  $("preview-caption").textContent =
    `Latest ${Math.min(50, currentData.metrics.rows)} of ${number(currentData.metrics.rows)} matching sales rows.`;
  $("preview-body").innerHTML =
    rows
      .slice(tablePage * pageSize, (tablePage + 1) * pageSize)
      .map(
        (r) =>
          `<tr><td>${escapeHTML(shortDate(r.date))}</td><td title="${escapeHTML(r.product)}">${escapeHTML(r.product)}</td><td title="${escapeHTML(r.region)}">${escapeHTML(r.region)}</td><td class="numeric">${number(r.quantity)}</td><td class="numeric">${escapeHTML(money(r.revenue))}</td></tr>`,
      )
      .join("") || '<tr><td colspan="5">No matching sales rows.</td></tr>';
  $("table-count").textContent = rows.length
    ? `Showing ${tablePage * pageSize + 1}–${Math.min((tablePage + 1) * pageSize, rows.length)} of ${rows.length} preview rows`
    : "0 preview rows";
  $("page-number").textContent =
    `${tablePage + 1} / ${Math.max(1, Math.ceil(rows.length / pageSize))}`;
  $("previous-page").disabled = tablePage === 0;
  $("next-page").disabled = (tablePage + 1) * pageSize >= rows.length;
}
$("browse-button").addEventListener("click", () => $("file-input").click());
$("replace-button").addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) analyzeFile(file, {}, true);
  event.target.value = "";
});
$("sample-button").addEventListener("click", async () => {
  if (busy) return;
  setBusy(true, "Loading sample sales…");
  try {
    const response = await fetch("/sample.csv");
    if (!response.ok)
      throw new Error("Could not load the sample. Please try again.");
    const file = new File([await response.blob()], "sample_sales.csv", {
      type: "text/csv",
    });
    setBusy(false);
    await analyzeFile(file, {}, true);
  } catch (error) {
    setBusy(false);
    showError(error.message);
  }
});
let dragDepth = 0;
["dragenter", "dragover", "dragleave", "drop"].forEach((name) =>
  $("dropzone").addEventListener(name, (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (name === "dragenter") dragDepth++;
    if (name === "dragleave") dragDepth--;
    if (name === "drop") {
      dragDepth = 0;
      if (event.dataTransfer.files.length > 1)
        showError("Please upload one CSV at a time.");
      else if (event.dataTransfer.files[0])
        analyzeFile(event.dataTransfer.files[0], {}, true);
    }
    $("dropzone").classList.toggle("drag-over", dragDepth > 0);
  }),
);
// Prevent an accidental drop outside the target from navigating away from the app.
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());
$("filters").addEventListener("submit", (event) => {
  event.preventDefault();
  if (sourceFile)
    analyzeFile(sourceFile, Object.fromEntries(new FormData(event.target)));
});
$("reset-filters").addEventListener(
  "click",
  () => sourceFile && analyzeFile(sourceFile),
);
$("quality-toggle").addEventListener("click", () => {
  $("quality-details").hidden = !$("quality-details").hidden;
  $("quality-toggle").setAttribute(
    "aria-expanded",
    String(!$("quality-details").hidden),
  );
});
$("previous-page").addEventListener("click", () => {
  if (tablePage > 0) {
    tablePage--;
    renderTable();
  }
});
$("next-page").addEventListener("click", () => {
  if ((tablePage + 1) * 5 < currentData.preview.length) {
    tablePage++;
    renderTable();
  }
});
$("export-button").addEventListener("click", async () => {
  if (!sourceFile || busy || !currentData?.metrics.rows) return;
  $("alert").hidden = true;
  setBusy(true, "Preparing your two-page PDF report…");
  $("export-label").textContent = "Preparing report…";
  try {
    // Use applied filters, never unapplied form edits, to match the visible metrics exactly.
    const response = await fetch("/api/report", {
      method: "POST",
      body: bodyFor(sourceFile, currentData.filters),
    });
    if (!response.ok) throw new Error(await responseError(response));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "sales-report.pdf";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    setBusy(false, "PDF report ready. Download started.");
    showToast("Your report is ready. PDF download started.");
  } catch (error) {
    setBusy(false);
    showError(error.message);
  } finally {
    $("export-label").textContent = "Export PDF report";
  }
});
document
  .querySelectorAll(".guide-button")
  .forEach((button) =>
    button.addEventListener("click", () => $("help-dialog").showModal()),
  );
$("close-help").addEventListener("click", () => $("help-dialog").close());
$("help-dialog").addEventListener("click", (event) => {
  if (event.target === $("help-dialog")) {
    const r = $("help-dialog").getBoundingClientRect();
    if (
      event.clientX < r.left ||
      event.clientX > r.right ||
      event.clientY < r.top ||
      event.clientY > r.bottom
    )
      $("help-dialog").close();
  }
});
document.querySelectorAll(".nav-link").forEach((link) =>
  link.addEventListener("click", (event) => {
    if (!currentData && link.hash !== "#overview") {
      event.preventDefault();
      showToast("Upload a CSV or try the sample to explore your data.");
      return;
    }
    document
      .querySelectorAll(".nav-link")
      .forEach((item) => item.classList.toggle("active", item === link));
  }),
);
let resizeFrame;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => {
    if (currentData) renderTrend();
  });
});
