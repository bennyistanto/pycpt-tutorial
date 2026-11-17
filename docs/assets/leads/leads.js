// Interactive views for the lead-time case studies.
// Presentation only: every number drawn here was computed by the executed notebook and
// saved to interactive-data.json; nothing is fitted or re-scored in the browser.

const NS = "http://www.w3.org/2000/svg";
const INK = "#1b1d22", MUTED = "#6b6e75", LINE = "#d9d3c7";
const METHOD_COLORS = {CCA: "#1f4fa3", PCR: "#c8462b", raw: "#6b6e75"};
const LEAD_COLORS = {1: "#1f4fa3", 2: "#4f8a5a", 3: "#c48a1d"};
const CATEGORY = [["Below normal", "#e07b39"], ["Near normal", "#9a9a94"], ["Above normal", "#2f6fb5"]];
let sequence = 0;

const el = (tag, cls, text) => {const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n;};
const sv = (tag, attrs = {}, text) => {const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (text !== undefined) n.textContent = text; return n;};
const num = (v, d = 1) => Number.isFinite(v) ? v.toLocaleString("en", {minimumFractionDigits: d, maximumFractionDigits: d}) : "–";
const fmtDate = s => new Date(s + "T00:00:00Z").toLocaleDateString("en-GB", {day: "numeric", month: "short", timeZone: "UTC"});

function ramp(stops, n = 256) {
  const rgb = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const pts = stops.map(rgb), out = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1) * (pts.length - 1), k = Math.min(pts.length - 2, Math.floor(t)), f = t - k;
    out.push(`rgb(${pts[k].map((v, j) => Math.round(v + (pts[k + 1][j] - v) * f)).join(",")})`);
  }
  return out;
}
const RAIN = ramp(["#ffffd9", "#c7e9b4", "#7fcdbb", "#41b6c4", "#1d91c0", "#225ea8", "#0c2c84"]);
const DIVERGE = ramp(["#2166ac", "#92c5de", "#f7f7f7", "#f4a582", "#b2182b"]);
const DIFF = ramp(["#8c510a", "#d8b365", "#f5f5f5", "#5ab4ac", "#01665e"]);
const pick = (colors, t) => colors[Math.max(0, Math.min(colors.length - 1, Math.round(t * (colors.length - 1))))];

// Case-specific labels come from the data file; the defaults describe the dekad case.
const leadName = (data, lead) => data.leadNames ? data.leadNames[data.leads.indexOf(lead)] : `Dekad +${lead}`;
const rawName = data => data.rawName || "raw GEFS";
const rawTitle = data => rawName(data).replace(/^raw/, "Raw");
const rainMax = data => data.rainMax || 300;
const unitText = data => ({month: "mm in the month", season: "mm in the season"}[data.kind] || "mm per dekad");
const trainingText = data => data.training || "2000-2018";
const sampleText = data => data.sample || "the 171 training dekads of 2000-2018";
const areaMean = (data, values) => {
  let s = 0, w = 0;
  values.forEach((v, k) => {if (v !== null) {const c = Math.cos(data.grid.lat[k] * Math.PI / 180); s += v * c; w += c;}});
  return w ? s / w : NaN;
};

export function selectControl(label, options, value) {
  const form = el("form", "story-control"), id = `lead-select-${++sequence}`;
  const lab = el("label", null, label); lab.htmlFor = id;
  const select = el("select"); select.id = id;
  for (const option of options) {const [v, l] = Array.isArray(option) ? option : [option, option]; const o = el("option", null, l); o.value = v; select.append(o);}
  select.value = value; form.append(lab, select);
  Object.defineProperty(form, "value", {get: () => select.value});
  select.addEventListener("change", () => form.dispatchEvent(new Event("input", {bubbles: true})));
  form.addEventListener("submit", e => e.preventDefault());
  return form;
}

function tooltip(root) {
  const tip = el("div", "story-tooltip"); tip.hidden = true; tip.setAttribute("role", "tooltip");
  const readout = el("p", "story-readout", "Hover, tap, or use the arrow keys on a map or chart to read a value.");
  readout.setAttribute("aria-live", "polite"); root.append(readout, tip);
  let pinned = false;
  const hide = () => {tip.hidden = true; pinned = false;};
  function show(title, entries, event, pin = false) {
    if (pinned && !pin && !["focus", "keydown"].includes(event?.type)) return;
    pinned = pin; tip.replaceChildren();
    const close = el("button", "story-tip-close", "×"); close.type = "button"; close.setAttribute("aria-label", "Dismiss detail"); close.onclick = hide;
    const dl = el("dl"); for (const [k, v] of entries) dl.append(el("dt", null, k), el("dd", null, String(v)));
    tip.append(close, el("strong", null, title), dl, el("small", null, "Tap to pin · Escape to dismiss")); tip.hidden = false;
    const r = event?.currentTarget?.getBoundingClientRect?.() || root.getBoundingClientRect();
    const x = event?.clientX || r.left + r.width / 2, y = event?.clientY || r.top + 15;
    tip.style.left = `${Math.max(8, Math.min(innerWidth - 340, x + 14))}px`;
    tip.style.top = `${Math.max(8, Math.min(innerHeight - tip.offsetHeight - 8, y + 14))}px`;
    readout.textContent = `${title} · ${entries.map(([k, v]) => `${k}: ${v}`).join(" · ")}`;
  }
  root.addEventListener("keydown", e => {if (e.key === "Escape") hide();});
  return {show, hide, leave: () => {if (!pinned) tip.hidden = true;}};
}

function bind(node, tip, title, entries) {
  node.setAttribute("role", "button"); node.setAttribute("tabindex", "0");
  node.setAttribute("aria-label", `${title}. ${entries.map(e => e.join(": ")).join(". ")}`);
  node.addEventListener("pointerenter", e => tip.show(title, entries, e));
  node.addEventListener("focus", e => tip.show(title, entries, e));
  node.addEventListener("pointerleave", tip.leave); node.addEventListener("blur", tip.leave);
  node.addEventListener("click", e => tip.show(title, entries, e, true));
}

function panel(id, title, hint) {
  const root = el("div", "story-view"); root.dataset.view = id;
  root.append(el("h3", "story-chart-title", title));
  if (hint) root.append(el("p", "story-hint", hint));
  return root;
}

function exportButtons(root, name, makePng, makeSvg) {
  const bar = el("div", "story-export"), status = el("span", "story-export-status"); status.setAttribute("aria-live", "polite");
  const add = (label, make, ext) => {
    const b = el("button", null, label); b.type = "button"; bar.append(b);
    b.onclick = async () => {
      b.disabled = true; status.textContent = "Preparing…";
      try {
        const blob = await make(), url = URL.createObjectURL(blob), a = el("a");
        a.href = url; a.download = `pycpt-${name}.${ext}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
        status.textContent = "Ready · includes the current selections.";
      } catch (error) {status.textContent = `Could not export: ${error.message}`;}
      finally {b.disabled = false;}
    };
  };
  if (makePng) add("Download current view (PNG)", makePng, "png");
  if (makeSvg) add("Download chart (SVG)", makeSvg, "svg");
  root.append(bar);
}

const svgBlob = svg => {
  const clone = svg.cloneNode(true), box = svg.viewBox.baseVal;
  clone.setAttribute("width", box.width); clone.setAttribute("height", box.height);
  clone.prepend(sv("style", {}, "text{font-family:Arial,sans-serif;fill:#1b1d22} .story-axis{font-size:12px;fill:#3c4049}"));
  return new Blob([new XMLSerializer().serializeToString(clone)], {type: "image/svg+xml;charset=utf-8"});
};

async function stackPng(title, canvases, legendText) {
  const W = 1000, gap = 16, scaled = canvases.map(c => ({c, h: c.height * W / c.width}));
  const H = 50 + scaled.reduce((a, s) => a + s.h + gap + 26, 0) + 40;
  const out = el("canvas"); out.width = W; out.height = Math.ceil(H);
  const ctx = out.getContext("2d"); ctx.fillStyle = "white"; ctx.fillRect(0, 0, W, H); ctx.fillStyle = INK;
  ctx.font = "bold 20px Arial"; ctx.fillText(title, 12, 30); let y = 50;
  ctx.font = "16px Arial";
  for (const {c, h} of scaled) {ctx.fillText(c.dataset.title || "", 12, y + 18); ctx.drawImage(c, 0, y + 26, W, h); y += h + gap + 26;}
  ctx.font = "14px Arial"; ctx.fillStyle = MUTED; ctx.fillText(legendText || "", 12, y + 20);
  return await new Promise(resolve => out.toBlob(resolve, "image/png"));
}

function rings(g) {
  if (g.type === "Polygon") return g.coordinates;
  if (g.type === "MultiPolygon") return g.coordinates.flat();
  if (g.type === "GeometryCollection") return g.geometries.flatMap(rings);
  return [];
}

// One map of a field stored at the cells listed in data.grid (one value per cell, null = no value).
function mapCanvas(tip, data, geo, values, {title, colorOf, describe}) {
  const card = el("div", "story-map-card"), canvas = el("canvas"); card.append(el("h4", null, title), canvas);
  canvas.dataset.title = title; canvas.tabIndex = 0; canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `${title}. Hover or tap a cell; arrow keys move between cells.`);
  const extent = [94, 142, -12, 8], W = 960, L = 56, R = 16, T = 16, B = 46;
  const pw = W - L - R, ph = pw * (extent[3] - extent[2]) / (extent[1] - extent[0]), H = Math.ceil(ph + T + B);
  canvas.width = W; canvas.height = H; canvas.style.aspectRatio = `${W}/${H}`;
  const ctx = canvas.getContext("2d"), x = v => L + (v - extent[0]) / (extent[1] - extent[0]) * pw, y = v => T + (extent[3] - v) / (extent[3] - extent[2]) * ph;
  const step = data.grid.step, cw = pw * step / (extent[1] - extent[0]) + .6, ch = ph * step / (extent[3] - extent[2]) + .6;
  ctx.fillStyle = "white"; ctx.fillRect(0, 0, W, H); ctx.save(); ctx.beginPath(); ctx.rect(L, T, pw, ph); ctx.clip();
  const drawLayer = (layer, fill) => {
    for (const f of layer.features) for (const ring of rings(f.geometry)) {
      ctx.beginPath(); ring.forEach((p, i) => i ? ctx.lineTo(x(p[0]), y(p[1])) : ctx.moveTo(x(p[0]), y(p[1]))); ctx.closePath();
      if (fill) {ctx.fillStyle = "#eceae4"; ctx.fill();} ctx.strokeStyle = "#7d8580"; ctx.lineWidth = .6; ctx.stroke();
    }
  };
  drawLayer(geo.neighbours, true); drawLayer(geo.indonesia, true);
  const {lat, lon} = data.grid, lookup = new Map();
  for (let k = 0; k < lat.length; k++) {
    lookup.set(`${Math.round(lon[k] / step)},${Math.round(lat[k] / step)}`, k);
    const v = values[k]; if (v === null) continue;
    ctx.fillStyle = colorOf(v); ctx.fillRect(x(lon[k] - step / 2), y(lat[k] + step / 2), cw, ch);
  }
  drawLayer(geo.provinces, false); ctx.restore();
  ctx.strokeStyle = LINE; ctx.strokeRect(L, T, pw, ph); ctx.fillStyle = MUTED; ctx.font = "20px Arial"; ctx.textAlign = "center";
  for (let lo = 100; lo <= 140; lo += 10) ctx.fillText(`${lo}°E`, x(lo), T + ph + 30);
  ctx.textAlign = "right"; for (const la of [-10, -5, 0, 5]) ctx.fillText(la < 0 ? `${-la}°S` : la > 0 ? `${la}°N` : "0°", L - 6, y(la) + 6);
  let current = 0;
  function show(k, e, pin = false) {
    if (k === undefined) return; current = k;
    tip.show(title, [["Longitude", num(lon[k], 3)], ["Latitude", num(lat[k], 3)], ...describe(values[k], k)], e, pin);
  }
  function hit(e, pin = false) {
    const b = canvas.getBoundingClientRect(), px = (e.clientX - b.left) * W / b.width, py = (e.clientY - b.top) * H / b.height;
    const lo = extent[0] + (px - L) / pw * (extent[1] - extent[0]), la = extent[3] - (py - T) / ph * (extent[3] - extent[2]);
    // Cell centres sit at (n + 0.5) * step and are keyed by Math.round(centre / step) = n + 1.
    const k = lookup.get(`${Math.floor(lo / step) + 1},${Math.floor(la / step) + 1}`);
    if (k !== undefined) show(k, e, pin); else tip.leave();
  }
  canvas.addEventListener("pointermove", e => hit(e)); canvas.addEventListener("click", e => hit(e, true)); canvas.addEventListener("pointerleave", tip.leave);
  canvas.addEventListener("focus", e => show(current, e));
  canvas.addEventListener("keydown", e => {
    const d = {ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1]}[e.key]; if (!d) return; e.preventDefault();
    for (let s = 1; s < 40; s++) {
      const k = lookup.get(`${Math.round(lon[current] / step) + d[0] * s},${Math.round(lat[current] / step) + d[1] * s}`);
      if (k !== undefined) {show(k, e, true); return;}
    }
  });
  return {card, canvas};
}

function gradientLegend(root, colors, min, max, label, ticks = 3) {
  const bar = el("div", "story-legend"), strip = el("div", "story-gradient");
  strip.style.background = `linear-gradient(to right,${colors.filter((_, i) => i % 16 === 0).join(",")})`;
  const ends = el("div", "story-legend-ends");
  for (let i = 0; i < ticks; i++) ends.append(el("span", null, num(min + (max - min) * i / (ticks - 1), Math.abs(max - min) < 5 ? 1 : 0)));
  bar.append(strip, ends, el("p", null, label)); root.append(bar);
}

function categoryLegend(root, note) {
  const key = el("div", "story-key story-key-row");
  for (const [name, color] of CATEGORY) {const item = el("span", "story-key-item"), sw = el("span", "story-key-swatch"); sw.style.borderTop = `10px solid ${color}`; item.append(sw, name); key.append(item);}
  root.append(key); if (note) root.append(el("p", "story-hint", note));
}

// ---------------------------------------------------------------------------------------
// 1. How issue dates, leads and target dekads line up
export function issueTimeline(data, issue) {
  const item = data.issues.find(d => d.issued === issue) || data.issues[0];
  const root = panel("issue-timeline", `Issued ${item.label}: the next three dekads`,
    "Each forecast starts at 00 UTC on the issue date. Hover a block for its dates and the model days it uses.");
  const tip = tooltip(root), W = 900, H = 150, svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Issue date and the three target dekads"});
  const day0 = Date.parse(item.issued + "T00:00:00Z"), dayW = 22, x0 = 60, x = d => x0 + d * dayW;
  svg.append(sv("line", {x1: x0, x2: x(36), y1: 104, y2: 104, stroke: LINE}));
  for (let d = 0; d <= 35; d += 5) {svg.append(sv("line", {x1: x(d), x2: x(d), y1: 100, y2: 108, stroke: LINE})); svg.append(sv("text", {x: x(d), y: 126, "text-anchor": "middle", class: "story-axis"}, `day ${d}`));}
  svg.append(sv("rect", {x: x(35), y: 96, width: x(36) - x(35), height: 16, fill: "#f3e3dd"}));
  svg.append(sv("text", {x: x(35.5), y: 142, "text-anchor": "middle", class: "story-axis"}, "model ends"));
  svg.append(sv("circle", {cx: x(0), cy: 104, r: 6, fill: INK}));
  svg.append(sv("text", {x: x(0), y: 88, "text-anchor": "start", class: "story-axis", "font-size": 14, "font-weight": 600}, `issued ${fmtDate(item.issued)}, 00 UTC`));
  for (const t of item.targets) {
    const start = (Date.parse(t.dekad + "T00:00:00Z") - day0) / 864e5, dk = data.dekads.find(d => d.start === t.dekad);
    const next = data.dekads.find(d => Date.parse(d.start) > Date.parse(t.dekad));
    const len = next ? (Date.parse(next.start) - Date.parse(t.dekad)) / 864e5 : 10 + (t.dekad.endsWith("-21") ? 1 : 0);
    const g = sv("g"); g.append(sv("rect", {x: x(start), y: 30, width: len * dayW - 3, height: 40, rx: 6, fill: LEAD_COLORS[t.lead], opacity: .85}));
    g.append(sv("text", {x: x(start + len / 2), y: 55, "text-anchor": "middle", fill: "white", "font-size": 14, "font-weight": 600}, `Dekad +${t.lead} · ${dk ? dk.label : t.dekad}`));
    bind(g, tip, `Dekad +${t.lead}`, [["Target", `${fmtDate(t.dekad)}, ${len} days`], ["Model days used", `${start} to ${start + len - 1}`], ["Issued", fmtDate(item.issued)]]);
    svg.append(g);
  }
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `issue-timeline-${item.issued}`, null, async () => svgBlob(svg));
  return root;
}

// 2. Skill by lead: area-weighted mean, CCA vs PCR vs raw GEFS
export function skillByLead(data, metric = "Pearson") {
  const label = metric === "Pearson" ? "Pearson correlation" : "2AFC (%)", ref = metric === "Pearson" ? 0 : 50;
  const root = panel("skill-by-lead", `${label} by lead · cross-validated, ${trainingText(data)}`,
    `Area-weighted mean over ${data.cellText || "Indonesia's 3,240 cells"}. ${rawTitle(data)} involves no fitting, so it is scored by correlation only.`);
  const tip = tooltip(root), rows = data.skillTable, methods = metric === "Pearson" ? ["CCA", "PCR", rawName(data)] : ["CCA", "PCR"];
  const vals = rows.map(r => r[metric]).filter(Number.isFinite), lo = Math.min(ref, ...vals) - (metric === "Pearson" ? .05 : 2), hi = Math.max(...vals) + (metric === "Pearson" ? .05 : 2);
  const n = data.leads.length, W = 900, H = 90 + n * 62, L = 150, R = 150, T = 20, B = 40;
  const x = v => L + (v - lo) / (hi - lo) * (W - L - R), y = (lead, k) => T + (data.leads.indexOf(lead) + .5) * (H - T - B) / n + (k - 1) * 16;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": `${label} by lead`});
  for (let i = 0; i <= 4; i++) {const v = lo + (hi - lo) * i / 4; svg.append(sv("line", {x1: x(v), x2: x(v), y1: T, y2: H - B, stroke: "#ece8e0"})); svg.append(sv("text", {x: x(v), y: H - B + 18, "text-anchor": "middle", class: "story-axis"}, num(v, metric === "Pearson" ? 2 : 0)));}
  svg.append(sv("line", {x1: x(ref), x2: x(ref), y1: T, y2: H - B, stroke: "#9a9a94", "stroke-dasharray": "4 3"}));
  for (const lead of data.leads) svg.append(sv("text", {x: L - 12, y: y(lead, 1) + 4, "text-anchor": "end", class: "story-axis"}, leadName(data, lead)));
  methods.forEach((m, k) => {
    const color = METHOD_COLORS[m === rawName(data) ? "raw" : m], pts = data.leads.map(lead => rows.find(r => r.lead === lead && r.method === m));
    svg.append(sv("polyline", {points: pts.map((r, i) => `${x(r[metric])},${y(data.leads[i], k)}`).join(" "), fill: "none", stroke: color, "stroke-width": 1.2, opacity: .45}));
    pts.forEach((r, i) => {const c = sv("circle", {cx: x(r[metric]), cy: y(data.leads[i], k), r: 7, fill: color}); bind(c, tip, `${m} · ${leadName(data, r.lead)}`, [[label, num(r[metric], metric === "Pearson" ? 3 : 1)]]); svg.append(c);});
    svg.append(sv("circle", {cx: W - R + 24, cy: T + 14 + k * 22, r: 6, fill: color}), sv("text", {x: W - R + 36, y: T + 18 + k * 22, class: "story-axis"}, m));
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `skill-by-lead-${metric}`, null, async () => svgBlob(svg));
  return root;
}

// 3. Where the skill is: one map per lead, stacked
export function skillMaps(data, geo, method = "CCA", metric = "pearson") {
  const label = metric === "pearson" ? "Pearson correlation" : "2AFC (%)";
  const name = method === "raw" ? rawTitle(data) : method;
  const root = panel("skill-maps", `${name} · ${label} by lead`,
    `Cross-validated over ${sampleText(data)}. Hover, tap or use the arrow keys to read a cell.`);
  const tip = tooltip(root), canvases = [], [lo, hi] = metric === "pearson" ? [-1, 1] : [0, 100];
  const grid = el("div"); grid.style.display = "grid"; grid.style.gap = ".8rem";
  for (const lead of data.leads) {
    const values = method === "raw" ? data.raw[lead] : data.skill[method][lead][metric];
    const {card, canvas} = mapCanvas(tip, data, geo, values, {title: leadName(data, lead), colorOf: v => pick(DIVERGE, (v - lo) / (hi - lo)), describe: v => [[label, v === null ? "no value" : num(v, metric === "pearson" ? 3 : 1)]]});
    grid.append(card); canvases.push(canvas);
  }
  root.append(grid); gradientLegend(root, DIVERGE, lo, hi, `${label} · ${metric === "pearson" ? "0 = no linear relationship" : "50% = no skill"}`, 5);
  exportButtons(root, `skill-maps-${method}-${metric}`, () => stackPng(`${name} · ${label} by lead`, canvases, `${label}, cross-validated ${trainingText(data)}`), null);
  return root;
}

// 4. A forecast as issued: the next three dekads, forecast against observed
export function issueMaps(data, geo, issue, method = "CCA", view = "total") {
  const item = data.issues.find(d => d.issued === issue) || data.issues[0];
  const names = {total: "Forecast total", observed: "Observed total", difference: "Forecast minus observed", category: "Most likely category", observedCategory: "Observed category"};
  const root = panel("issue-maps", `Issued ${item.label} · ${method} · ${names[view]}`,
    "Dekad +1 at the top. Totals are the 2000-2018 mean for that dekad plus the calibrated anomaly; categories follow CPT's terciles of the training anomalies.");
  const tip = tooltip(root), canvases = [], grid = el("div"); grid.style.display = "grid"; grid.style.gap = ".8rem";
  for (const t of item.targets) {
    const dk = data.dekads.find(d => d.start === t.dekad), f = t[method];
    let values, colorOf, describe;
    const cell = k => [["Forecast", num(f.total[k], 1) + " mm"], ["Observed", num(dk.observed[k], 1) + " mm"], ["2000-2018 mean", num(dk.mean[k], 1) + " mm"],
                       ["Most likely", f.category[k] === null ? "–" : `${CATEGORY[f.category[k]][0]} (${num(f.probability[k], 0)}%)`],
                       ["Observed category", dk.category[k] === null ? "–" : CATEGORY[dk.category[k]][0]]];
    if (view === "total" || view === "observed") {values = view === "total" ? f.total : dk.observed; colorOf = v => pick(RAIN, Math.sqrt(v / 300)); describe = (v, k) => cell(k);}
    else if (view === "difference") {values = f.total.map((v, k) => v === null || dk.observed[k] === null ? null : v - dk.observed[k]); colorOf = v => pick(DIFF, (v + 150) / 300); describe = (v, k) => [["Difference", num(v, 1) + " mm"], ...cell(k)];}
    else {values = view === "category" ? f.category : dk.category; colorOf = v => CATEGORY[v][1]; describe = (v, k) => cell(k);}
    const {card, canvas} = mapCanvas(tip, data, geo, values, {title: `Dekad +${t.lead} · ${dk.label}`, colorOf, describe});
    grid.append(card); canvases.push(canvas);
  }
  root.append(grid);
  let legendText;
  if (view === "total" || view === "observed") {legendText = "mm per dekad (square-root colour scale, 0 to 300+)"; gradientLegend(root, RAIN, 0, 300, legendText, 4);}
  else if (view === "difference") {legendText = "Forecast minus observed, mm per dekad (brown: forecast too dry, green: too wet)"; gradientLegend(root, DIFF, -150, 150, legendText, 5);}
  else {legendText = "Tercile categories"; categoryLegend(root, view === "category" ? "Colour shows the category with the highest forecast probability; hover for the probability." : null);}
  exportButtons(root, `issued-${item.issued}-${method}-${view}`, () => stackPng(`Issued ${item.label} · ${method} · ${names[view]}`, canvases, legendText), null);
  return root;
}

// 5. The season as a series: area-weighted totals, observed vs forecast at each lead
export function seasonSeries(data) {
  const s = data.series, n = s.dekad.length;
  const root = panel("season-series", "October-December 2023 · area-weighted dekad rainfall over Indonesia",
    "Bars: observed. Dashed: 2000-2018 mean. Lines: CCA forecast totals made one, two and three dekads ahead.");
  const tip = tooltip(root), all = [...s.observed, ...s.mean_2000_2018, ...[1, 2, 3].flatMap(l => s[`cca_total_lead${l}`])];
  const W = 900, H = 300, L = 60, R = 160, T = 20, B = 40, top = Math.ceil(Math.max(...all) / 20) * 20;
  const x = i => L + (i + .5) * (W - L - R) / n, y = v => T + (1 - v / top) * (H - T - B), bw = (W - L - R) / n * .6;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Area-weighted dekad rainfall, October-December 2023"});
  for (let v = 0; v <= top; v += top / 4) {svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, num(v, 0)));}
  svg.append(sv("text", {x: 14, y: T + (H - T - B) / 2, transform: `rotate(-90 14 ${T + (H - T - B) / 2})`, "text-anchor": "middle", class: "story-axis"}, "mm per dekad"));
  for (let i = 0; i < n; i++) {
    const r = sv("rect", {x: x(i) - bw / 2, y: y(s.observed[i]), width: bw, height: y(0) - y(s.observed[i]), fill: "#d9d3c7"});
    bind(r, tip, `${s.dekad[i]} 2023`, [["Observed", num(s.observed[i], 1) + " mm"], ["2000-2018 mean", num(s.mean_2000_2018[i], 1) + " mm"],
      ...[1, 2, 3].map(l => [`CCA, dekad +${l}`, num(s[`cca_total_lead${l}`][i], 1) + " mm"])]);
    svg.append(r, sv("text", {x: x(i), y: H - B + 18, "text-anchor": "middle", class: "story-axis"}, s.dekad[i]));
  }
  svg.append(sv("polyline", {points: s.mean_2000_2018.map((v, i) => `${x(i)},${y(v)}`).join(" "), fill: "none", stroke: MUTED, "stroke-dasharray": "5 4"}));
  [1, 2, 3].forEach((l, k) => {
    const v = s[`cca_total_lead${l}`];
    svg.append(sv("polyline", {points: v.map((d, i) => `${x(i)},${y(d)}`).join(" "), fill: "none", stroke: LEAD_COLORS[l], "stroke-width": 2}));
    v.forEach((d, i) => {const c = sv("circle", {cx: x(i), cy: y(d), r: 5, fill: LEAD_COLORS[l]}); bind(c, tip, `CCA, dekad +${l} · ${s.dekad[i]}`, [["Forecast", num(d, 1) + " mm"], ["Observed", num(s.observed[i], 1) + " mm"]]); svg.append(c);});
    svg.append(sv("circle", {cx: W - R + 22, cy: T + 14 + k * 22, r: 6, fill: LEAD_COLORS[l]}), sv("text", {x: W - R + 34, y: T + 18 + k * 22, class: "story-axis"}, `CCA, dekad +${l}`));
  });
  svg.append(sv("rect", {x: W - R + 16, y: T + 74, width: 12, height: 12, fill: "#d9d3c7"}), sv("text", {x: W - R + 34, y: T + 84, class: "story-axis"}, "observed"),
             sv("line", {x1: W - R + 14, x2: W - R + 30, y1: T + 102, y2: T + 102, stroke: MUTED, "stroke-dasharray": "5 4"}), sv("text", {x: W - R + 34, y: T + 106, class: "story-axis"}, "2000-2018 mean"));
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, "ond-2023-series", null, async () => svgBlob(svg));
  return root;
}

// ---------------------------------------------------------------------------------------
// Views for the monthly and seasonal cases (one issue date, six targets)

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthIndex = s => {const d = new Date(s + "T00:00:00Z"); return d.getUTCFullYear() * 12 + d.getUTCMonth();};
const target = (data, lead) => data.targets.find(t => t.lead === Number(lead));

// 6. The issue date and the six targets it forecasts
export function issueTargets(data, lead) {
  lead = Number(lead);
  const root = panel("issue-targets", `Issued ${data.issue.label}: the next six ${data.kind}s`,
    "One CFSv2 run, started on the issue date, forecasts every target. Lead = months from the issue date to the first day of the target. Hover a bar for its dates.");
  const tip = tooltip(root), first = monthIndex(data.issue.date), last = Math.max(...data.targets.map(t => monthIndex(t.end)));
  const n = data.targets.length, W = 900, rowH = 30, T = 30, H = T + n * rowH + 60, L = 190, R = 30, x = m => L + (m - first) / (last - first) * (W - L - R);
  const axisY = T + n * rowH + 12;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Issue date and the six targets"});
  svg.append(sv("line", {x1: L, x2: W - R, y1: axisY, y2: axisY, stroke: LINE}));
  for (let m = first; m <= last; m++) {
    svg.append(sv("line", {x1: x(m), x2: x(m), y1: axisY - 5, y2: axisY + 5, stroke: LINE}));
    if (m < last) svg.append(sv("text", {x: (x(m) + x(m + 1)) / 2, y: axisY + 22, "text-anchor": "middle", class: "story-axis"}, MONTHS[m % 12] + (m % 12 === 0 || m === first ? ` ${Math.floor(m / 12)}` : "")));
  }
  svg.append(sv("line", {x1: x(first), x2: x(first), y1: T - 12, y2: axisY, stroke: INK, "stroke-dasharray": "3 3"}));
  svg.append(sv("text", {x: x(first) + 6, y: T - 16, class: "story-axis", "font-weight": 600}, `issued ${data.issue.label}`));
  data.targets.forEach((t, i) => {
    const on = t.lead === lead, a = monthIndex(t.start), b = monthIndex(t.end), y = T + i * rowH;
    const g = sv("g");
    g.append(sv("rect", {x: x(a), y: y + 3, width: x(b) - x(a) - 2, height: rowH - 6, rx: 5, fill: on ? "#c48a1d" : "#1f4fa3", opacity: on ? .95 : .55}));
    g.append(sv("text", {x: L - 12, y: y + rowH / 2 + 5, "text-anchor": "end", class: "story-axis", "font-weight": on ? 700 : 400}, `Lead ${t.lead} · ${t.label}`));
    const end = new Date(Date.parse(t.end + "T00:00:00Z") - 864e5).toISOString().slice(0, 10);
    bind(g, tip, `Lead ${t.lead} · ${t.label}`, [["Target", `${fmtDate(t.start)} ${t.start.slice(0, 4)} to ${fmtDate(end)} ${end.slice(0, 4)}`], ["Issued", data.issue.label], ["PyCPT target", t.pycpt]]);
    svg.append(g);
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `issue-targets-${lead}`, null, async () => svgBlob(svg));
  return root;
}

// 7. The forecasts as issued: one map per lead, each against its own target
export function targetMaps(data, geo, method = "CCA", view = "category") {
  const names = {total: "Forecast total", observed: "Observed total", difference: "Forecast minus observed", category: "Most likely category", observedCategory: "Observed category"};
  const root = panel("target-maps", `Issued ${data.issue.label} · ${method} · ${names[view]}`,
    "Lead 1 at the top. Each map is a different target; hover a cell for the forecast, the observation and that target's 1991-2020 mean.");
  const tip = tooltip(root), canvases = [], grid = el("div"); grid.style.display = "grid"; grid.style.gap = ".8rem";
  const top = rainMax(data), rain = v => pick(RAIN, Math.sqrt(Math.max(0, v) / top)), cat = v => CATEGORY[v][1], diff = v => pick(DIFF, (v + top / 2) / top);
  for (const ld of data.leads) {
    const f = data.forecasts[ld][method], o = data.observed[ld], t = target(data, ld);
    const cell = k => [["Forecast", num(f.total[k], 0) + " mm"], ["Observed", num(o.total[k], 0) + " mm"], ["1991-2020 mean", num(o.mean[k], 0) + " mm"],
      ["Most likely", f.category[k] === null ? "–" : `${CATEGORY[f.category[k]][0]} (${num(f.probability[k], 0)}%)`],
      ["Observed category", o.category[k] === null ? "–" : CATEGORY[o.category[k]][0]]];
    let values, colorOf, describe = (v, k) => cell(k);
    if (view === "total") {values = f.total; colorOf = rain;}
    else if (view === "observed") {values = o.total; colorOf = rain;}
    else if (view === "difference") {values = f.total.map((v, k) => v === null || o.total[k] === null ? null : v - o.total[k]); colorOf = diff; describe = (v, k) => [["Difference", num(v, 0) + " mm"], ...cell(k)];}
    else {values = view === "category" ? f.category : o.category; colorOf = cat;}
    const {card, canvas} = mapCanvas(tip, data, geo, values, {title: `Lead ${ld} · ${t.label}`, colorOf, describe});
    grid.append(card); canvases.push(canvas);
  }
  root.append(grid);
  let legendText;
  if (view === "total" || view === "observed") {legendText = `${unitText(data)} (square-root colour scale, 0 to ${top}+)`; gradientLegend(root, RAIN, 0, top, legendText, 4);}
  else if (view === "difference") {legendText = `Forecast minus observed, ${unitText(data)} (brown: forecast too dry, green: too wet)`; gradientLegend(root, DIFF, -top / 2, top / 2, legendText, 5);}
  else {legendText = "Tercile categories"; categoryLegend(root, view === "category" ? "Colour shows the category with the highest forecast probability; hover for the probability." : "Terciles of each target's 1991-2020 values at each cell.");}
  exportButtons(root, `issued-${data.issue.date}-${method}-${view}`, () => stackPng(`Issued ${data.issue.label} · ${method} · ${names[view]}`, canvases, legendText), null);
  return root;
}

// 8. One target from earlier starts, against one issue date whose target changes with lead
export function sameTargetSkill(data) {
  const st = data.sameTarget, rows = st.rows, n = data.leads.length;
  const root = panel("same-target", "Lead or target? Area-weighted mean correlation by lead",
    `Solid: issued ${data.issue.label}, so each lead is a different target. Open, dashed: one target, ${st.target}, started earlier at each lead. CCA is cross-validated; the raw model involves no fitting.`);
  const tip = tooltip(root), lines = [["CCA Pearson, issued 1 Nov", METHOD_COLORS.CCA, false, `CCA, issued ${data.issue.label}`], ["CCA Pearson", METHOD_COLORS.CCA, true, `CCA, ${st.target}`],
    ["raw CFSv2 Pearson, issued 1 Nov", METHOD_COLORS.raw, false, `Raw CFSv2, issued ${data.issue.label}`], ["raw CFSv2 Pearson", METHOD_COLORS.raw, true, `Raw CFSv2, ${st.target}`]];
  const vals = rows.flatMap(r => lines.map(l => r[l[0]])), lo = Math.min(0, ...vals) - .05, hi = Math.max(...vals) + .05;
  const W = 900, H = 320, L = 60, R = 250, T = 20, B = 50, x = i => L + (i + .5) * (W - L - R) / n, y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Correlation by lead for the two designs"});
  for (let i = 0; i <= 4; i++) {const v = lo + (hi - lo) * i / 4; svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, num(v, 2)));}
  svg.append(sv("line", {x1: L, x2: W - R, y1: y(0), y2: y(0), stroke: "#9a9a94", "stroke-dasharray": "4 3"}));
  rows.forEach((r, i) => svg.append(sv("text", {x: x(i), y: H - B + 20, "text-anchor": "middle", class: "story-axis"}, `Lead ${r.lead}`)));
  lines.forEach(([key, color, dashed, name], k) => {
    svg.append(sv("polyline", {points: rows.map((r, i) => `${x(i)},${y(r[key])}`).join(" "), fill: "none", stroke: color, "stroke-width": 2, "stroke-dasharray": dashed ? "6 4" : "none"}));
    rows.forEach((r, i) => {
      const c = sv("circle", {cx: x(i), cy: y(r[key]), r: 6, fill: dashed ? "white" : color, stroke: color, "stroke-width": 2});
      bind(c, tip, `${name} · lead ${r.lead}`, [["Pearson", num(r[key], 3)], dashed ? ["Start", fmtDate(r.start) + " " + r.start.slice(0, 4)] : ["Target", target(data, r.lead).label]]);
      svg.append(c);
    });
    svg.append(sv("circle", {cx: W - R + 18, cy: T + 14 + k * 24, r: 6, fill: dashed ? "white" : color, stroke: color, "stroke-width": 2}), sv("text", {x: W - R + 30, y: T + 18 + k * 24, class: "story-axis"}, name));
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, "same-target-vs-issue", null, async () => svgBlob(svg));
  return root;
}

// 9. The forecasts as issued, scored by lead against their own targets
export function scoresByLead(data, metric = "mean") {
  const names = {mean: "Area-weighted forecast total", hit: "Hit rate of the most likely category (%)", rpss: "RPSS against climatological odds"};
  const key = {mean: "mean forecast (mm)", hit: "hit rate (%)", rpss: "RPSS"}[metric];
  const root = panel("scores-by-lead", `Issued ${data.issue.label} · ${names[metric]}`,
    metric === "mean" ? "Grey squares: observed area-weighted total of each target; open squares: its 1991-2020 mean." :
    metric === "hit" ? "Grey squares: always forecasting the category that covered most of the area in that target (chosen with hindsight)." :
    "0 is no better than 33/34/33% odds. One outcome per lead: this rewards leaning the right way, not skill in general.");
  const tip = tooltip(root), rows = data.scores2023, refs = data.references, n = data.leads.length;
  const refSets = metric === "mean" ? [["observed mean (mm)", "Observed", true], ["1991-2020 mean (mm)", "1991-2020 mean", false]]
    : metric === "hit" ? [["reference hit rate (%)", "Reference", true]] : [];
  const vals = rows.map(r => r[key]).concat(refSets.flatMap(([k]) => refs.map(r => r[k]))).concat(metric === "rpss" ? [0] : []);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * .15 || 1;
  const W = 900, H = 300, L = 70, R = 170, T = 20, B = 50, y = v => T + (1 - (v - (lo - pad)) / (hi - lo + 2 * pad)) * (H - T - B), x = i => L + (i + .5) * (W - L - R) / n;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": names[metric]});
  for (let i = 0; i <= 4; i++) {const v = lo - pad + (hi - lo + 2 * pad) * i / 4; svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, num(v, metric === "rpss" ? 2 : 0)));}
  if (metric === "rpss") svg.append(sv("line", {x1: L, x2: W - R, y1: y(0), y2: y(0), stroke: MUTED, "stroke-dasharray": "6 4"}));
  data.leads.forEach((ld, i) => svg.append(sv("text", {x: x(i), y: H - B + 20, "text-anchor": "middle", class: "story-axis"}, target(data, ld).label)));
  let legendRow = 0;
  refSets.forEach(([k, name, filled]) => {
    refs.forEach((r, i) => {const q = sv("rect", {x: x(i) - 7, y: y(r[k]) - 7, width: 14, height: 14, fill: filled ? "#9a9a94" : "white", stroke: "#9a9a94", "stroke-width": 2}); bind(q, tip, `${name} · ${r.target}`, [[name, num(r[k], 1)]]); svg.append(q);});
    svg.append(sv("rect", {x: W - R + 12, y: T + 8 + legendRow * 22, width: 12, height: 12, fill: filled ? "#9a9a94" : "white", stroke: "#9a9a94", "stroke-width": 2}), sv("text", {x: W - R + 30, y: T + 18 + legendRow * 22, class: "story-axis"}, name));
    legendRow++;
  });
  ["CCA", "PCR"].forEach((m, k) => {
    const pts = data.leads.map(ld => rows.find(r => r.lead === ld && r.method === m));
    pts.forEach((r, i) => {const c = sv("circle", {cx: x(i) + (k - .5) * 16, cy: y(r[key]), r: 6, fill: METHOD_COLORS[m]}); bind(c, tip, `${m} · lead ${r.lead} · ${r.target}`, [[names[metric], num(r[key], metric === "rpss" ? 3 : 1)]]); svg.append(c);});
    svg.append(sv("circle", {cx: W - R + 18, cy: T + 14 + (legendRow + k) * 22, r: 6, fill: METHOD_COLORS[m]}), sv("text", {x: W - R + 30, y: T + 18 + (legendRow + k) * 22, class: "story-axis"}, m));
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `scores-${metric}`, null, async () => svgBlob(svg));
  return root;
}

// 10. Season against its first month, from the same issue date
export function compareScales(data) {
  const root = panel("compare-scales", "Area-weighted mean correlation · season (filled) and its first month (open)",
    `Both issued ${data.issue.label}, with the same model, observations, grid, settings and lead. CCA is cross-validated; the raw model involves no fitting.`);
  const tip = tooltip(root), rows = data.comparison, n = data.leads.length;
  const vals = rows.flatMap(r => [r["Pearson, season"], r["Pearson, month"]]), lo = Math.min(0, ...vals) - .05, hi = Math.max(...vals) + .05;
  const W = 900, H = 90 + n * 62, L = 190, R = 190, T = 20, B = 40, x = v => L + (v - lo) / (hi - lo) * (W - L - R), y = (i, k) => T + (i + .5) * (H - T - B) / n + (k - .5) * 18;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Seasonal and monthly correlation by lead"});
  for (let i = 0; i <= 4; i++) {const v = lo + (hi - lo) * i / 4; svg.append(sv("line", {x1: x(v), x2: x(v), y1: T, y2: H - B, stroke: "#ece8e0"})); svg.append(sv("text", {x: x(v), y: H - B + 18, "text-anchor": "middle", class: "story-axis"}, num(v, 2)));}
  data.leads.forEach((ld, i) => {const r = rows.find(q => q.lead === ld && q.method === "CCA"); svg.append(sv("text", {x: L - 12, y: y(i, .5) + 4, "text-anchor": "end", class: "story-axis"}, `Lead ${ld}: ${r.season} / ${r.month}`));});
  [["CCA", METHOD_COLORS.CCA], [rawName(data), METHOD_COLORS.raw]].forEach(([m, color], k) => {
    data.leads.forEach((ld, i) => {
      const r = rows.find(q => q.lead === ld && q.method === m), a = r["Pearson, month"], b = r["Pearson, season"];
      svg.append(sv("line", {x1: x(a), x2: x(b), y1: y(i, k), y2: y(i, k), stroke: color, opacity: .5}));
      const open = sv("circle", {cx: x(a), cy: y(i, k), r: 6, fill: "white", stroke: color, "stroke-width": 2}), full = sv("circle", {cx: x(b), cy: y(i, k), r: 6, fill: color});
      for (const c of [open, full]) bind(c, tip, `${m} · lead ${ld}`, [[r.season, num(b, 3)], [r.month, num(a, 3)], ["Season minus month", num(b - a, 3)]]);
      svg.append(open, full);
    });
    svg.append(sv("circle", {cx: W - R + 18, cy: T + 14 + k * 44, r: 6, fill: color}), sv("text", {x: W - R + 30, y: T + 18 + k * 44, class: "story-axis"}, `${m}, season`),
               sv("circle", {cx: W - R + 18, cy: T + 36 + k * 44, r: 6, fill: "white", stroke: color, "stroke-width": 2}), sv("text", {x: W - R + 30, y: T + 40 + k * 44, class: "story-axis"}, `${m}, month`));
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, "seasonal-vs-monthly", null, async () => svgBlob(svg));
  return root;
}

// ---------------------------------------------------------------------------------------
// Views for the weekly case: native 0.05° fields, loaded per map only when a view needs them

const rgbCache = new Map();
const rgbOf = colors => {
  if (!rgbCache.has(colors)) rgbCache.set(colors, colors.map(c => c.match(/\d+/g).map(Number)));
  return rgbCache.get(colors);
};
const CATEGORY_RGB = CATEGORY.map(([, c]) => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16)));
const pickRgb = (colors, t) => {const a = rgbOf(colors); return a[Math.max(0, Math.min(a.length - 1, Math.round(t * (a.length - 1))))];};
const fieldCache = new Map();

async function loadBytes(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  const buffer = await response.arrayBuffer(), head = new Uint8Array(buffer, 0, 2);
  if (head[0] === 0x1f && head[1] === 0x8b) {
    const stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"));
    return await new Response(stream).arrayBuffer();
  }
  return buffer;                                         // already decompressed by the server
}

// The manifest and the shared pixel list; `base` is the folder of manifest.json, relative to the page
export async function loadWeekData(base) {
  const manifest = await fetch(base + "manifest.json").then(r => r.json());
  const pixels = new Int32Array(await fetch(base + "pixels.bin").then(r => r.arrayBuffer()));
  const {nx, ny} = manifest.grid, lookup = new Int32Array(nx * ny).fill(-1);
  pixels.forEach((p, k) => {lookup[p] = k;});
  return {...manifest, base, pixels, lookup};
}

// One map file, decoded into Float32Arrays (NaN = no value) by the layout in the manifest
async function weekField(data, name, kind, scale = 1) {
  if (fieldCache.has(name)) return fieldCache.get(name);
  const promise = loadBytes(`${data.base}fields/${name}.bin.gz`).then(buffer => {
    const n = data.grid.pixels, out = {};
    let offset = 0;
    for (const [part, type, partScale, partOffset = 0] of data.layout[kind]) {
      const Type = {i16: Int16Array, u16: Uint16Array, u8: Uint8Array, i8: Int8Array}[type], missing = {i16: -32768, u16: 65535, u8: 255, i8: -128}[type];
      const raw = new Type(buffer, offset, n), s = partScale || scale, values = new Float32Array(n);
      for (let i = 0; i < n; i++) values[i] = raw[i] === missing ? NaN : raw[i] / s + partOffset;
      out[part] = values; offset += raw.byteLength;
    }
    return out;
  });
  fieldCache.set(name, promise);
  return promise;
}

const leadKey = (data, lead) => data.leadKeys[data.leads.indexOf(lead)];
const leadOfKey = (data, key) => data.leads[data.leadKeys.indexOf(key)];

// Shared zoom, pan and hover marker for all maps of one view. Maps may cover different boxes
// (the predictor box and Indonesia): they share a zoom factor and a centre in longitude/latitude.
function mapGroup(root) {
  const state = {k: 1, cx: null, cy: null}, maps = [];
  const bar = el("div", "story-map-tools");
  const button = (label, title, run) => {const b = el("button", null, label); b.type = "button"; b.title = title; b.setAttribute("aria-label", title); b.onclick = run; bar.append(b); return b;};
  const zoomIn = button("+", "Zoom in", () => zoom(1.6)), zoomOut = button("−", "Zoom out", () => zoom(1 / 1.6));
  const resetView = () => {state.k = 1; state.cx = state.cy = null; apply();};
  const reset = button("Reset view", "Back to the full map", resetView);
  bar.append(el("span", "story-map-tools-note", "Zoom and the red marker apply to every map in this view. Drag to move when zoomed · double-click or Ctrl + scroll to zoom."));
  root.append(bar);
  let queued = false;
  // Buttons, keys and double-clicks redraw at once; a drag sends many moves, so those wait for the next frame
  function apply(later = false) {
    state.k = Math.max(1, Math.min(32, state.k)); if (state.k < 1.001) {state.k = 1; state.cx = state.cy = null;}   // 1.6 * 1.6 / 1.6 / 1.6 is not exactly 1
    zoomOut.disabled = reset.disabled = state.k === 1; zoomIn.disabled = state.k === 32;
    if (!later) {for (const m of maps) m.redraw(); return;}
    if (queued) return; queued = true;
    (document.hidden ? setTimeout : requestAnimationFrame)(() => {queued = false; for (const m of maps) m.redraw();});
  }
  // Zoom by factor f, keeping the point (lon, lat) where it is on screen; without a point, about the centre
  function zoom(f, lon, lat, from) {
    const k = Math.max(1, Math.min(32, state.k * f)), ratio = k / state.k; if (ratio === 1) return;
    const [x0, x1, y0, y1] = (from || maps[0]).window(), cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    state.cx = lon === undefined ? cx : lon + (cx - lon) / ratio; state.cy = lat === undefined ? cy : lat + (cy - lat) / ratio;
    state.k = k; apply();
  }
  function pan(dLon, dLat, from) {
    const [x0, x1, y0, y1] = from.window(); state.cx = (x0 + x1) / 2 + dLon; state.cy = (y0 + y1) / 2 + dLat;
    const [a0, a1, b0, b1] = from.window(); state.cx = (a0 + a1) / 2; state.cy = (b0 + b1) / 2; apply(true);      // keep the clamped centre
  }
  const hover = (lon, lat) => {for (const m of maps) m.mark(lon, lat);};
  const leave = () => {for (const m of maps) m.mark();};
  zoomOut.disabled = reset.disabled = true;
  return {state, maps, zoom, pan, hover, leave, reset: resetView};
}

// The part of a full extent [west, east, south, north] a map shows for the group's zoom and centre
function groupWindow(group, full) {
  const k = group.state.k, w = (full[1] - full[0]) / k, h = (full[3] - full[2]) / k;
  const cx = Math.max(full[0] + w / 2, Math.min(full[1] - w / 2, group.state.cx ?? (full[0] + full[1]) / 2));
  const cy = Math.max(full[2] + h / 2, Math.min(full[3] - h / 2, group.state.cy ?? (full[2] + full[3]) / 2));
  return [cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2];
}
const tickStep = span => [20, 10, 5, 2, 1, .5, .2, .1, .05].find(s => span / s >= 3) || .05;
const degreeLabel = (v, pos, neg, step) => {const d = step < 1 ? (step < .1 ? 2 : 1) : 0, a = Math.abs(v).toFixed(d); return Math.abs(v) < 1e-9 ? "0°" : `${a}°${v > 0 ? pos : neg}`;};

// Frame, zoom gestures and hover marker shared by the two kinds of map; `paint` draws the data for a window
function zoomableMap(tip, geo, group, full, title, hint, paint, locate, layersBelow = true) {
  const card = el("div", "story-map-card"), wrap = el("div", "story-map-wrap"), canvas = el("canvas"), dot = el("span", "story-map-dot");
  dot.hidden = true; wrap.append(canvas, dot); card.append(el("h4", null, title), wrap);
  canvas.dataset.title = title; canvas.tabIndex = 0; canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", `${title}. ${hint}`);
  const W = 960, L = 56, R = 16, T = 16, B = 46, pw = W - L - R, ph = pw * (full[3] - full[2]) / (full[1] - full[0]), H = Math.ceil(ph + T + B);
  canvas.width = W; canvas.height = H; canvas.style.aspectRatio = `${W}/${H}`;
  const ctx = canvas.getContext("2d");
  let win = full.slice();
  const x = v => L + (v - win[0]) / (win[1] - win[0]) * pw, y = v => T + (win[3] - v) / (win[3] - win[2]) * ph;
  const drawLayer = (layer, fill, stroke = "#7d8580", width = .6) => {
    for (const f of layer.features) for (const ring of rings(f.geometry)) {
      ctx.beginPath(); ring.forEach((p, i) => i ? ctx.lineTo(x(p[0]), y(p[1])) : ctx.moveTo(x(p[0]), y(p[1]))); ctx.closePath();
      if (fill) {ctx.fillStyle = "#eceae4"; ctx.fill();} ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.stroke();
    }
  };
  function redraw() {
    win = groupWindow(group, full);
    ctx.fillStyle = "white"; ctx.fillRect(0, 0, W, H); ctx.save(); ctx.beginPath(); ctx.rect(L, T, pw, ph); ctx.clip();
    if (layersBelow) {drawLayer(geo.neighbours, true); drawLayer(geo.indonesia, true);}
    paint(ctx, win, {L, T, pw, ph, x, y});
    if (layersBelow) drawLayer(geo.provinces, false); else {drawLayer(geo.neighbours, false, "#3c4049", .7); drawLayer(geo.indonesia, false, "#3c4049", .7);}
    ctx.restore(); ctx.strokeStyle = LINE; ctx.lineWidth = 1; ctx.strokeRect(L, T, pw, ph); ctx.fillStyle = MUTED; ctx.font = "20px Arial"; ctx.textAlign = "center";
    const sx = tickStep(win[1] - win[0]), sy = tickStep((win[3] - win[2]) * 1.6);
    for (let v = Math.ceil(win[0] / sx - 1e-9) * sx; v <= win[1] + 1e-9; v += sx) if (x(v) > L + 30 && x(v) < L + pw - 30) ctx.fillText(degreeLabel(v, "E", "W", sx), x(v), T + ph + 30);
    ctx.textAlign = "right";
    for (let v = Math.ceil(win[2] / sy - 1e-9) * sy; v <= win[3] + 1e-9; v += sy) if (y(v) > T + 10 && y(v) < T + ph - 4) ctx.fillText(degreeLabel(v, "N", "S", sy), L - 6, y(v) + 6);
    canvas.style.touchAction = group.state.k > 1 ? "none" : "pan-y"; canvas.style.cursor = group.state.k > 1 ? "grab" : "crosshair";
    mark(...marked);
  }
  let marked = [];
  function mark(lon, lat) {
    marked = [lon, lat];
    if (lon === undefined || lon < win[0] || lon > win[1] || lat < win[2] || lat > win[3]) {dot.hidden = true; return;}
    dot.hidden = false; dot.style.left = `${x(lon) / W * 100}%`; dot.style.top = `${y(lat) / H * 100}%`;
  }
  const at = e => {const b = canvas.getBoundingClientRect(), px = (e.clientX - b.left) * W / b.width, py = (e.clientY - b.top) * H / b.height;
    return [win[0] + (px - L) / pw * (win[1] - win[0]), win[3] - (py - T) / ph * (win[3] - win[2]), px >= L && px <= L + pw && py >= T && py <= T + ph];};
  const self = {card, canvas, redraw, mark, window: () => groupWindow(group, full)};
  let drag = null, moved = false;
  function point(e, pin) {
    const [lon, lat, inside] = at(e), hit = inside ? locate(lon, lat) : null;
    if (!hit) {tip.leave(); group.leave(); return;}
    group.hover(hit.lon, hit.lat); hit.show(e, pin);
  }
  canvas.addEventListener("pointerdown", e => {moved = false; if (group.state.k > 1 && e.button === 0) {drag = {x: e.clientX, y: e.clientY}; canvas.setPointerCapture(e.pointerId);}});
  canvas.addEventListener("pointermove", e => {
    if (drag) {
      const b = canvas.getBoundingClientRect(), dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) < 4 && !moved) return;
      moved = true; drag = {x: e.clientX, y: e.clientY}; tip.leave();
      group.pan(-dx * W / b.width / pw * (win[1] - win[0]), dy * H / b.height / ph * (win[3] - win[2]), self); return;
    }
    point(e, false);
  });
  const release = e => {if (drag) {drag = null; try {canvas.releasePointerCapture(e.pointerId);} catch {}}};
  canvas.addEventListener("pointerup", release); canvas.addEventListener("pointercancel", release);
  canvas.addEventListener("click", e => {if (moved) {moved = false; return;} point(e, true);});
  canvas.addEventListener("dblclick", e => {const [lon, lat, inside] = at(e); if (inside) {e.preventDefault(); group.zoom(2, lon, lat, self);}});
  canvas.addEventListener("wheel", e => {if (!e.ctrlKey && !e.metaKey) return; e.preventDefault(); const [lon, lat, inside] = at(e); if (inside) group.zoom(e.deltaY < 0 ? 1.25 : .8, lon, lat, self);}, {passive: false});
  canvas.addEventListener("pointerleave", () => {tip.leave(); group.leave();});
  canvas.addEventListener("keydown", e => {
    if (e.key === "+" || e.key === "=") {e.preventDefault(); group.zoom(1.6, undefined, undefined, self);}
    else if (e.key === "-" || e.key === "_") {e.preventDefault(); group.zoom(1 / 1.6, undefined, undefined, self);}
    else if (e.key === "0") {e.preventDefault(); group.reset();}
  });
  group.maps.push(self);
  return self;
}

// One 0.05° map: the field is drawn as an image (one image pixel per grid pixel), boundaries on top
function rasterCanvas(tip, data, geo, values, {title, colorOf, describe, onPick, group}) {
  const {west, north, step, nx, ny} = data.grid, full = [west, west + nx * step, north - ny * step, north];
  const image = new ImageData(nx, ny);
  data.pixels.forEach((p, k) => {
    const v = values[k]; if (Number.isNaN(v)) return;
    const c = colorOf(v); image.data.set([c[0], c[1], c[2], 255], p * 4);
  });
  const raster = el("canvas"); raster.width = nx; raster.height = ny; raster.getContext("2d").putImageData(image, 0, 0);
  const paint = (ctx, win, {L, T, pw, ph}) => {
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(raster, (win[0] - west) / step, (north - win[3]) / step, (win[1] - win[0]) / step, (win[3] - win[2]) / step, L, T, pw, ph);
  };
  const centre = k => {const p = data.pixels[k]; return [west + (p % nx + .5) * step, north - (Math.floor(p / nx) + .5) * step];};
  let current = 0;
  function show(k, e, pin = false) {
    if (k === undefined || k < 0) return; current = k; const [lo, la] = centre(k);
    tip.show(title, [["Longitude", num(lo, 3)], ["Latitude", num(la, 3)], ...describe(values[k], k)], e, pin);
    if (pin && onPick) onPick(k, lo, la);
  }
  const locate = (lon, lat) => {
    const col = Math.floor((lon - west) / step), row = Math.floor((north - lat) / step);
    const k = col >= 0 && col < nx && row >= 0 && row < ny ? data.lookup[row * nx + col] : -1;
    if (k < 0) return null; const [lo, la] = centre(k);
    return {lon: lo, lat: la, show: (e, pin) => show(k, e, pin)};
  };
  const map = zoomableMap(tip, geo, group || mapGroup(el("div")), full, title, "Hover or tap a pixel; arrow keys move between pixels; + and - zoom.", paint, locate);
  const {canvas} = map;
  canvas.addEventListener("focus", e => {show(current, e); map.mark(...centre(current));});
  canvas.addEventListener("keydown", e => {
    const d = {ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[e.key]; if (!d) return; e.preventDefault();
    const p = data.pixels[current], col = p % nx, row = Math.floor(p / nx);
    for (let s = 1; s < 200; s++) {
      const c = col + d[0] * s, r = row + d[1] * s; if (c < 0 || c >= nx || r < 0 || r >= ny) break;
      const k = data.lookup[r * nx + c]; if (k >= 0) {show(k, e, true); (group ? group.hover : map.mark)(...centre(k)); return;}
    }
  });
  map.redraw();
  return {card: map.card, canvas};
}

function loadingPanel(root) {
  const note = el("p", "story-hint", "Loading maps…"); root.append(note); return note;
}

// 1. One issue date and its five targets, in days after the issue date
export function weekIssueTimeline(data, issue) {
  const item = data.issues.find(d => d.issued === issue) || data.issues[0];
  const root = panel("week-issue-timeline", `Issued ${item.label}: ${data.timelineTitle || "weeks 1-4 and weeks 3-4"}`,
    data.timelineHint || "Issued at 00 UTC on a Wednesday. Bars are the target windows in days after the issue date; hover for dates.");
  const tip = tooltip(root), n = data.leads.length, W = 900, rowH = 30, T = 34, H = T + n * rowH + 56, L = 170, R = 30;
  const span = data.axisDays || 30, x = d => L + d / span * (W - L - R), axisY = T + n * rowH + 10;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Issue date and target windows"});
  svg.append(sv("line", {x1: x(0), x2: x(span), y1: axisY, y2: axisY, stroke: LINE}));
  for (let d = 0; d <= span; d += span > 30 ? 5 : 7) {svg.append(sv("line", {x1: x(d), x2: x(d), y1: axisY - 5, y2: axisY + 5, stroke: LINE})); svg.append(sv("text", {x: x(d), y: axisY + 22, "text-anchor": "middle", class: "story-axis"}, `day ${d}`));}
  svg.append(sv("line", {x1: x(0), x2: x(0), y1: T - 14, y2: axisY, stroke: INK, "stroke-dasharray": "3 3"}));
  svg.append(sv("text", {x: x(0) + 6, y: T - 18, class: "story-axis", "font-weight": 600}, `issued ${item.label}, 00 UTC`));
  data.leads.forEach((lead, i) => {
    const key = leadKey(data, lead), yy = T + i * rowH, t = item.targets.find(q => q.lead === key);
    const first = t ? (Date.parse(t.start + "T00:00:00Z") - Date.parse(item.issued + "T00:00:00Z")) / 864e5 : (data.firstDay || {})[key];
    const days = t ? t.days : (data.days || {})[key];
    svg.append(sv("text", {x: L - 12, y: yy + rowH / 2 + 5, "text-anchor": "end", class: "story-axis"}, leadName(data, lead)));
    const g = sv("g");
    if (first === undefined) {svg.append(sv("text", {x: x(0) + 8, y: yy + rowH / 2 + 5, class: "story-axis"}, "target outside October-December 2023")); return;}
    g.append(sv("rect", {x: x(first), y: yy + 3, width: x(first + days) - x(first) - 2, height: rowH - 6, rx: 5, fill: t ? "#1f4fa3" : "#d9d3c7", opacity: t ? .8 : 1}));
    const entries = [["Model days", `${first} to ${first + days - 1}`]];
    if (t) {const end = new Date(Date.parse(t.start + "T00:00:00Z") + (days - 1) * 864e5).toISOString().slice(0, 10); entries.unshift(["Target", `${fmtDate(t.start)} to ${fmtDate(end)} ${end.slice(0, 4)}`]);}
    else entries.unshift(["Target", "outside October-December 2023, not forecast here"]);
    bind(g, tip, leadName(data, lead), entries); svg.append(g);
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `week-issue-${item.issued}`, null, async () => svgBlob(svg));
  return root;
}

// 2. Skill maps at 0.05°, one per lead
export async function weekSkillMaps(data, geo, method = "CCA", metric = "pearson") {
  const label = metric === "pearson" ? "Pearson correlation" : "2AFC (%)", name = method === "raw" ? rawTitle(data) : method;
  const root = panel("week-skill-maps", `${name} · ${label} by lead · 0.05°`, `Cross-validated over ${sampleText(data)}. Hover, tap or use the arrow keys to read a pixel.`);
  const tip = tooltip(root), note = loadingPanel(root), canvases = [], [lo, hi] = metric === "pearson" ? [-1, 1] : [0, 100];
  const fields = await Promise.all(data.leads.map(lead => weekField(data, `skill-${method}-${metric}-${leadKey(data, lead)}`, "skill", data.scales[metric])));
  note.remove();
  const grid = el("div"), group = mapGroup(root); grid.style.display = "grid"; grid.style.gap = ".8rem";
  data.leads.forEach((lead, i) => {
    const values = fields[i].value;
    const {card, canvas} = rasterCanvas(tip, data, geo, values, {group, title: leadName(data, lead), colorOf: v => pickRgb(DIVERGE, (v - lo) / (hi - lo)),
      describe: v => [[label, Number.isNaN(v) ? "no value" : num(v, metric === "pearson" ? 3 : 1)]]});
    grid.append(card); canvases.push(canvas);
  });
  root.append(grid); gradientLegend(root, DIVERGE, lo, hi, `${label} · ${metric === "pearson" ? "0 = no linear relationship" : "50% = no skill"}`, 5);
  exportButtons(root, `week-skill-${method}-${metric}`, () => stackPng(`${name} · ${label} by lead`, canvases, `${label}, cross-validated ${trainingText(data)}, 0.05°`), null);
  return root;
}

// 3. A forecast as issued: each lead against its own target, at 0.05°
export async function weekIssueMaps(data, geo, issue, method = "CCA", view = "total") {
  const item = data.issues.find(d => d.issued === issue) || data.issues[0];
  const names = {total: "Forecast total", observed: "Observed total", difference: "Forecast minus observed", category: "Most likely category", observedCategory: "Observed category"};
  const root = panel("week-issue-maps", `Issued ${item.label} · ${method} · ${names[view]}`,
    data.mapsHint || "Week 1 at the top, weeks 3-4 at the bottom. Totals are the 2000-2018 mean for that part of the season plus the calibrated anomaly; categories follow CPT's terciles of the training anomalies.");
  const tip = tooltip(root), note = loadingPanel(root), canvases = [];
  const loaded = await Promise.all(item.targets.map(t => Promise.all([weekField(data, `fc-${t.lead}-${method}-${t.start}`, "fc"), weekField(data, `obs-${t.days}-${t.start}`, "obs")])));
  // Flexible forecast ingredients, where the case provides them: the forecast scale and the climatology scale
  const flex = data.flex ? await Promise.all(item.targets.map(t => Promise.all([weekField(data, `flex-${t.lead}-${method}-${t.start}`, "flex"), weekField(data, data.flex.clim[t.lead], "flex")]))) : null;
  note.remove();
  const curves = el("div");
  const {nx, west, north, step} = data.grid;
  function drawCurves(i, k) {
    const t = item.targets[i], [f, o] = loaded[i], mu = f.total[k], sc = flex[i][0].scale[k], cmu = o.mean[k], cs = flex[i][1].scale[k], ob = o.total[k], nu = data.flex.dof[t.lead];
    if (![mu, sc, cmu, cs].every(Number.isFinite) || sc <= 0 || cs <= 0) return;
    const p = data.pixels[k], lo = west + (p % nx + .5) * step, la = north - (Math.floor(p / nx) + .5) * step;
    const place = `${num(lo, 3)}°E, ${la < 0 ? num(-la, 3) + "°S" : num(la, 3) + "°N"}`, chance = x => num(100 * tSf(x, nu, mu, sc), 0);
    curves.replaceChildren(exceedanceCurves({heading: `${leadName(data, leadOfKey(data, t.lead))} · ${method} flexible forecast at ${place}`,
      note: `Forecast centre ${num(mu, 0)} mm, ${data.training} mean ${num(cmu, 0)} mm, observed ${num(ob, 0)} mm. Chance of more than the mean: forecast ${chance(cmu)}%, climatology 50%.${Number.isFinite(ob) ? ` Chance of more than what was observed: forecast ${chance(ob)}%.` : ""}`,
      mu, s: sc, nu, cmu, cs, forecastLabel: `${method} forecast`, unit: `total in the target (${data.unit || "mm"})`,
      marks: [[cmu, `${data.training} mean`, MUTED, "4 3"], [ob, "observed", INK]]}));
  }
  const grid = el("div"), group = mapGroup(root); grid.style.display = "grid"; grid.style.gap = ".8rem";
  item.targets.forEach((t, i) => {
    const [f, o] = loaded[i], top = (data.rainMax || {})[t.days] || (t.days === 7 ? 200 : 400);
    const end = new Date(Date.parse(t.start + "T00:00:00Z") + (t.days - 1) * 864e5).toISOString().slice(0, 10);
    const cell = k => [["Forecast", num(f.total[k], 0) + " mm"], ["Observed", num(o.total[k], 0) + " mm"], ["2000-2018 mean", num(o.mean[k], 0) + " mm"],
      ["Most likely", Number.isNaN(f.category[k]) ? "–" : `${CATEGORY[f.category[k]][0]} (${num(f.probability[k], 0)}%)`],
      ["Observed category", Number.isNaN(o.category[k]) ? "–" : CATEGORY[o.category[k]][0]]];
    let values, colorOf, describe = (v, k) => cell(k);
    if (view === "total" || view === "observed") {values = view === "total" ? f.total : o.total; colorOf = v => pickRgb(RAIN, Math.sqrt(Math.max(0, v) / top));}
    else if (view === "difference") {values = f.total.map((v, k) => v - o.total[k]); colorOf = v => pickRgb(DIFF, (v + top / 2) / top); describe = (v, k) => [["Difference", num(v, 0) + " mm"], ...cell(k)];}
    else {values = view === "category" ? f.category : o.category; colorOf = v => CATEGORY_RGB[v];}
    const {card, canvas} = rasterCanvas(tip, data, geo, values, {group, title: `${leadName(data, leadOfKey(data, t.lead))} · ${fmtDate(t.start)} to ${fmtDate(end)}`, colorOf, describe, onPick: flex ? k => drawCurves(i, k) : undefined});
    grid.append(card); canvases.push(canvas);
  });
  root.append(grid);
  if (flex) {
    root.append(el("p", "story-hint", "Click or tap a pixel on any map, or focus a map and press Enter, to draw that target's flexible forecast below: the whole distribution of the forecast against climatology."), curves);
    let start = 0, best = Infinity;                       // start at the pixel nearest Jakarta, on the first target
    data.pixels.forEach((p, k) => {const d = (west + (p % nx + .5) * step - 106.85) ** 2 + (north - (Math.floor(p / nx) + .5) * step + 6.2) ** 2; if (d < best) {best = d; start = k;}});
    drawCurves(0, start);
  }
  let legendText;
  if (data.rainLegend && view !== "category" && view !== "observedCategory") {
    const m = Object.values(data.rainMax)[0];
    if (view === "difference") {legendText = `Forecast minus observed, ${data.rainLegend} (brown: forecast too dry, green: too wet)`; gradientLegend(root, DIFF, -m / 2, m / 2, legendText, 5);}
    else {legendText = `${data.rainLegend} (square-root colour scale, 0 to ${m}+)`; gradientLegend(root, RAIN, 0, m, legendText, 5);}
  }
  else if (view === "total" || view === "observed") {const m7 = (data.rainMax || {})[7] || 200, m14 = (data.rainMax || {})[14] || 400;
    legendText = `mm in the target window (square-root scale; 0 to ${m7}+ for one week, 0 to ${m14}+ for weeks 3-4)`; gradientLegend(root, RAIN, 0, m7, `mm in one week (weeks 3-4: 0 to ${m14})`, 5);}
  else if (view === "difference") {const m7 = (data.rainMax || {})[7] || 200, m14 = (data.rainMax || {})[14] || 400;
    legendText = `Forecast minus observed, mm (brown: forecast too dry, green: too wet; ±${m7 / 2} for one week, ±${m14 / 2} for weeks 3-4)`; gradientLegend(root, DIFF, -m7 / 2, m7 / 2, `Forecast minus observed, mm in one week (weeks 3-4: ±${m14 / 2})`, 5);}
  else {legendText = "Tercile categories"; categoryLegend(root, view === "category" ? "Colour shows the category with the highest forecast probability; hover for the probability." : null);}
  exportButtons(root, `week-issued-${item.issued}-${method}-${view}`, () => stackPng(`Issued ${item.label} · ${method} · ${names[view]}`, canvases, legendText), null);
  return root;
}

// 4. The season as a series: area-weighted weekly totals, observed vs forecast at each lead
export function weekSeries(data) {
  const s = data.series, n = s.observed.length, starts = s["week starting"] || s.start, keys = data.seriesLeads || ["week1", "week2", "week3", "week4"];
  const palette = ["#1f4fa3", "#4f8a5a", "#c48a1d", "#c8462b"], colors = Object.fromEntries(keys.map((k, i) => [k, palette[i]]));
  const column = k => s[`cca_total_${k}`] || s[`cca_total_lead${leadOfKey(data, k)}`];
  const unit = data.seriesUnit || "mm in 7 days";
  const root = panel("week-series", data.seriesTitle || "October-December 2023 · area-weighted weekly rainfall over Indonesia",
    data.seriesHint || "Bars: observed, by the week's first day (a Thursday). Dashed: 2000-2018 mean. Lines: CCA forecast totals made one to four weeks ahead.");
  const tip = tooltip(root), all = [...s.observed, ...s.mean_2000_2018, ...keys.flatMap(k => column(k))];
  const W = 900, H = 300, L = 60, R = 160, T = 20, B = 46, top = Math.ceil(Math.max(...all) / 20) * 20;
  const x = i => L + (i + .5) * (W - L - R) / n, y = v => T + (1 - v / top) * (H - T - B), bw = (W - L - R) / n * .6;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Area-weighted weekly rainfall, October-December 2023"});
  for (let v = 0; v <= top; v += top / 4) {svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, num(v, 0)));}
  svg.append(sv("text", {x: 14, y: T + (H - T - B) / 2, transform: `rotate(-90 14 ${T + (H - T - B) / 2})`, "text-anchor": "middle", class: "story-axis"}, unit));
  for (let i = 0; i < n; i++) {
    const r = sv("rect", {x: x(i) - bw / 2, y: y(s.observed[i]), width: bw, height: y(0) - y(s.observed[i]), fill: "#d9d3c7"});
    bind(r, tip, `${/pentad/.test(unit) ? "Pentad" : /dekad/.test(unit) ? "Dekad" : "Week"} from ${fmtDate(starts[i])}`, [["Observed", num(s.observed[i], 1) + " mm"], ["2000-2018 mean", num(s.mean_2000_2018[i], 1) + " mm"],
      ...keys.map(k => [`CCA, ${leadName(data, leadOfKey(data, k))}`, num(column(k)[i], 1) + " mm"])]);
    svg.append(r, sv("text", {x: x(i), y: H - B + 18, "text-anchor": "middle", class: "story-axis"}, fmtDate(starts[i])));
  }
  svg.append(sv("polyline", {points: s.mean_2000_2018.map((v, i) => `${x(i)},${y(v)}`).join(" "), fill: "none", stroke: MUTED, "stroke-dasharray": "5 4"}));
  keys.forEach((k, j) => {
    const v = column(k), name = `CCA, ${leadName(data, leadOfKey(data, k))}`;
    svg.append(sv("polyline", {points: v.map((d, i) => `${x(i)},${y(d)}`).join(" "), fill: "none", stroke: colors[k], "stroke-width": 2}));
    v.forEach((d, i) => {const c = sv("circle", {cx: x(i), cy: y(d), r: 4.5, fill: colors[k]}); bind(c, tip, `${name} · ${fmtDate(starts[i])}`, [["Forecast", num(d, 1) + " mm"], ["Observed", num(s.observed[i], 1) + " mm"]]); svg.append(c);});
    svg.append(sv("circle", {cx: W - R + 22, cy: T + 14 + j * 22, r: 6, fill: colors[k]}), sv("text", {x: W - R + 34, y: T + 18 + j * 22, class: "story-axis"}, name));
  });
  svg.append(sv("rect", {x: W - R + 16, y: T + 96, width: 12, height: 12, fill: "#d9d3c7"}), sv("text", {x: W - R + 34, y: T + 106, class: "story-axis"}, "observed"),
             sv("line", {x1: W - R + 14, x2: W - R + 30, y1: T + 124, y2: T + 124, stroke: MUTED, "stroke-dasharray": "5 4"}), sv("text", {x: W - R + 34, y: T + 128, class: "story-axis"}, "2000-2018 mean"));
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, "ond-2023-weekly-series", null, async () => svgBlob(svg));
  return root;
}

// ---------------------------------------------------------------------------------------
// Views for the multi-model cases: every member and the ensemble (MME), EOF and CCA modes,
// calibrated forecasts and the flexible forecast (probability of exceedance)

const BELOW = ramp(["#fde8d7", "#f4a261", "#c8551b", "#7a2e05"]), NEAR = ramp(["#ededea", "#b4b4ae", "#6f6f6a"]), ABOVE = ramp(["#dbe9f6", "#7fb0dc", "#2f6fb5", "#0b3a75"]);
const POE = ramp(["#8c510a", "#d8b365", "#f5f5f5", "#5ab4ac", "#01665e"]);
// The ensemble is drawn in the text colour, so it stays visible in the dark theme
const leadTick = (data, ld) => data.leadShort ? data.leadShort[data.leads.indexOf(ld)] : `Lead ${ld}`;
const periodWord = data => data.periodWord || (data.kind === "month" ? "month" : "season");
const modelColor = (data, m) => m === "MME" ? "currentColor" : (data.modelColors || {})[m] || INK;
const isMember = (data, model, lead) => model === "MME" || data.members[leadKey(data, lead)].includes(model);
const memberCount = (data, lead) => data.members[leadKey(data, lead)].length;
const modelTitle = (data, model, lead) => model === "MME" ? `MME (${lead === undefined ? "all members" : memberCount(data, lead) + " members"})` : model;

// Student's t and normal distributions, for the flexible forecast (same formulas as scipy's t.sf and norm.sf)
function lgamma(z) {
  const c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (z < .5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - lgamma(1 - z);
  z -= 1; let x = c[0]; for (let i = 1; i < 9; i++) x += c[i] / (z + i);
  const t = z + 7.5; return .5 * Math.log(2 * Math.PI) + (z + .5) * Math.log(t) - t + Math.log(x);
}
function betacf(a, b, x) {
  const tiny = 1e-300; let c = 1, d = 1 - (a + b) * x / (a + 1); if (Math.abs(d) < tiny) d = tiny; d = 1 / d; let h = d;
  for (let m = 1; m <= 300; m++) {
    let aa = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m));
    d = 1 + aa * d; if (Math.abs(d) < tiny) d = tiny; c = 1 + aa / c; if (Math.abs(c) < tiny) c = tiny; d = 1 / d; h *= d * c;
    aa = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1));
    d = 1 + aa * d; if (Math.abs(d) < tiny) d = tiny; c = 1 + aa / c; if (Math.abs(c) < tiny) c = tiny; d = 1 / d; const del = d * c; h *= del;
    if (Math.abs(del - 1) < 1e-12) break;
  }
  return h;
}
function ibeta(a, b, x) {
  if (x <= 0) return 0; if (x >= 1) return 1;
  const bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
  return x < (a + 1) / (a + b + 2) ? bt * betacf(a, b, x) / a : 1 - bt * betacf(b, a, 1 - x) / b;
}
export function tSf(x, nu, mu, s) {const z = (x - mu) / s, p = .5 * ibeta(nu / 2, .5, nu / (nu + z * z)); return z > 0 ? p : 1 - p;}
const tPdf = (x, nu, mu, s) => {const z = (x - mu) / s; return Math.exp(lgamma((nu + 1) / 2) - lgamma(nu / 2)) / Math.sqrt(nu * Math.PI) * Math.pow(1 + z * z / nu, -(nu + 1) / 2) / s;};
function erfc(x) {
  const z = Math.abs(x), t = 1 / (1 + .5 * z);
  const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (.37409196 + t * (.09678418 + t * (-.18628806 + t * (.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-.82215223 + t * .17087277)))))))));
  return x >= 0 ? r : 2 - r;
}
export const normSf = (x, mu, s) => .5 * erfc((x - mu) / s / Math.SQRT2);
const normPdf = (x, mu, s) => Math.exp(-.5 * ((x - mu) / s) ** 2) / (s * Math.sqrt(2 * Math.PI));

// The flexible forecast at one place: probability of exceedance and probability density, forecast against climatology.
// The forecast is a Student's t distribution (centre mu, scale s, nu degrees of freedom), the climatology a normal
// distribution (mean cmu, scale cs): PyCPT's construct_flex_fcst. `marks` are vertical lines [value, label, colour, dash].
export function exceedanceCurves({heading, note, mu, s, nu, cmu, cs, marks = [], forecastLabel = "forecast", unit = "season total (mm)"}) {
  const holder = el("div", "story-flex-curves");
  if (heading) holder.append(el("h4", null, heading));
  if (note) holder.append(el("p", "story-hint", note));
  const values = marks.map(m => m[0]).filter(Number.isFinite);
  const xmin = Math.max(0, Math.min(cmu - 3.2 * cs, mu - 3.2 * s, ...values)), xmax = Math.max(cmu + 3.2 * cs, mu + 3.2 * s, ...values.map(v => v * 1.03));
  const N = 200, xs = Array.from({length: N}, (_, i) => xmin + (xmax - xmin) * i / (N - 1));
  const W = 900, H = 260, L = 60, R = 190, T = 16, B = 40, x = v => L + (v - xmin) / (xmax - xmin) * (W - L - R);
  const frame = (yMax, yLabel, fmt) => {
    const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "img", "aria-label": `${yLabel}: ${forecastLabel} against climatology`}), y = v => T + (1 - v / yMax) * (H - T - B);
    for (let i = 0; i <= 4; i++) {const v = yMax * i / 4; svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); if (fmt) svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, fmt(v)));}
    for (let i = 0; i <= 5; i++) {const v = xmin + (xmax - xmin) * i / 5; svg.append(sv("text", {x: x(v), y: H - B + 18, "text-anchor": "middle", class: "story-axis"}, num(v, 0)));}
    svg.append(sv("text", {x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle", class: "story-axis"}, unit));
    svg.append(sv("text", {x: 14, y: T + (H - T - B) / 2, transform: `rotate(-90 14 ${T + (H - T - B) / 2})`, "text-anchor": "middle", class: "story-axis"}, yLabel));
    for (const [v, , c, dash] of marks) if (Number.isFinite(v)) svg.append(sv("line", {x1: x(v), x2: x(v), y1: T, y2: H - B, stroke: c || MUTED, "stroke-dasharray": dash || "none", "stroke-width": 1.3}));
    return {svg, y};
  };
  const key = svg => [[forecastLabel, METHOD_COLORS.PCR], ["climatology (normal)", METHOD_COLORS.CCA], ...marks.map(m => [m[1], m[2] || MUTED, m[3]])]
    .forEach(([name, c, dash], i) => {svg.append(sv("line", {x1: W - R + 12, x2: W - R + 32, y1: T + 14 + i * 22, y2: T + 14 + i * 22, stroke: c, "stroke-width": 2, "stroke-dasharray": dash || "none"}), sv("text", {x: W - R + 38, y: T + 18 + i * 22, class: "story-axis"}, name));});
  const a = frame(100, "probability of exceedance (%)", v => num(v, 0));
  a.svg.append(sv("polyline", {points: xs.map(v => `${x(v)},${a.y(normSf(v, cmu, cs) * 100)}`).join(" "), fill: "none", stroke: METHOD_COLORS.CCA, "stroke-width": 2}));
  a.svg.append(sv("polyline", {points: xs.map(v => `${x(v)},${a.y(tSf(v, nu, mu, s) * 100)}`).join(" "), fill: "none", stroke: METHOD_COLORS.PCR, "stroke-width": 2.4}));
  key(a.svg);
  const peak = Math.max(tPdf(mu, nu, mu, s), normPdf(cmu, cmu, cs)) * 1.08, b = frame(peak, "probability density", null);
  b.svg.append(sv("polyline", {points: xs.map(v => `${x(v)},${b.y(normPdf(v, cmu, cs))}`).join(" "), fill: "none", stroke: METHOD_COLORS.CCA, "stroke-width": 2}));
  b.svg.append(sv("polyline", {points: xs.map(v => `${x(v)},${b.y(tPdf(v, nu, mu, s))}`).join(" "), fill: "none", stroke: METHOD_COLORS.PCR, "stroke-width": 2.4}));
  key(b.svg);
  for (const [title, part] of [["Probability of exceedance", a], ["Probability density", b]]) {const scroll = el("div", "story-chart-scroll"); scroll.append(el("h4", null, title), part.svg); holder.append(scroll);}
  return holder;
}

function stackGrid() {const grid = el("div"); grid.style.display = "grid"; grid.style.gap = ".8rem"; return grid;}
function noteCard(title, text) {const card = el("div", "story-map-card"); card.append(el("h4", null, title), el("p", "story-hint", text)); return card;}

// M1. Skill by lead for every member and the ensemble
export function mmeSkillByLead(data, method = "CCA", metric = "Pearson") {
  const label = {Pearson: "Pearson correlation", "2AFC (%)": "2AFC (%)", "CV RPSS": "Cross-validated RPSS"}[metric], ref = metric === "2AFC (%)" ? 50 : 0;
  const root = panel("mme-skill-by-lead", `${method} · ${label} by lead · every member and the ensemble`,
    `Area-weighted mean over ${data.cellText}, cross-validated ${data.training}. Black: the ensemble (MME).${metric === "Pearson" ? " Dashed grey: the raw multi-model mean, no calibration." : ""} A line stops where a model has no forecast for that lead.`);
  const tip = tooltip(root), rows = data.skillTable.filter(r => r.method === method && Number.isFinite(r[metric]));
  const rawRows = metric === "Pearson" ? data.skillTable.filter(r => r.method === "raw" && r.model === "MME") : [];
  const vals = rows.concat(rawRows).map(r => r[metric]), pad = metric === "2AFC (%)" ? 2 : .04, lo = Math.min(ref, ...vals) - pad, hi = Math.max(ref, ...vals) + pad;
  const n = data.leads.length, W = 900, H = 360, L = 60, R = 190, T = 20, B = 56, x = i => L + (i + .5) * (W - L - R) / n, y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": `${label} by lead for every model`});
  for (let i = 0; i <= 4; i++) {const v = lo + (hi - lo) * i / 4; svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, num(v, metric === "2AFC (%)" ? 0 : 2)));}
  svg.append(sv("line", {x1: L, x2: W - R, y1: y(ref), y2: y(ref), stroke: "#9a9a94", "stroke-dasharray": "4 3"}));
  data.leads.forEach((ld, i) => {svg.append(sv("text", {x: x(i), y: H - B + 20, "text-anchor": "middle", class: "story-axis"}, leadTick(data, ld))); svg.append(sv("text", {x: x(i), y: H - B + 38, "text-anchor": "middle", class: "story-axis"}, target(data, ld).label));});
  const series = data.models.map(m => [m, rows.filter(r => r.model === m), false]);
  if (rawRows.length) series.push(["raw multi-model mean", rawRows, true]);
  series.forEach(([m, mine, dashed], k) => {
    const color = dashed ? MUTED : modelColor(data, m), bold = m === "MME";
    const pts = data.leads.map((ld, i) => [i, mine.find(r => r.lead === ld)]).filter(([, r]) => r);
    svg.append(sv("polyline", {points: pts.map(([i, r]) => `${x(i)},${y(r[metric])}`).join(" "), fill: "none", stroke: color, "stroke-width": bold ? 3 : 1.4, "stroke-dasharray": dashed ? "6 4" : "none"}));
    pts.forEach(([i, r]) => {const c = sv("circle", {cx: x(i), cy: y(r[metric]), r: bold ? 6 : 4.5, fill: dashed ? "white" : color, stroke: color, "stroke-width": 1.5});
      bind(c, tip, `${m} · ${dashed ? "no calibration" : method} · ${leadTick(data, r.lead)} · ${r.target}`, [[label, num(r[metric], metric === "2AFC (%)" ? 1 : 3)]]); svg.append(c);});
    svg.append(sv("line", {x1: W - R + 12, x2: W - R + 32, y1: T + 14 + k * 22, y2: T + 14 + k * 22, stroke: color, "stroke-width": bold ? 3 : 1.6, "stroke-dasharray": dashed ? "6 4" : "none"}), sv("text", {x: W - R + 38, y: T + 18 + k * 22, class: "story-axis", "font-weight": bold ? 700 : 400}, m));
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `mme-skill-${method}-${metric.replace(/\W+/g, "")}`, null, async () => svgBlob(svg));
  return root;
}

// M2. Skill maps of one model (or the ensemble), one per lead
export async function mmeSkillMaps(data, geo, model = "MME", method = "CCA", metric = "pearson") {
  if (method === "raw") metric = "pearson";
  const label = metric === "pearson" ? "Pearson correlation" : "Cross-validated RPSS";
  const how = method === "raw" ? "no calibration" : method;
  const root = panel("mme-skill-maps", `${modelTitle(data, model)} · ${how} · ${label} by lead`,
    `${method === "raw" ? "The model's own rainfall against the observations" : "Cross-validated"} over ${data.sample}. Hover, tap or use the arrow keys to read a pixel.`);
  const tip = tooltip(root), note = loadingPanel(root), canvases = [], use = data.leads.filter(ld => isMember(data, model, ld));
  const fields = await Promise.all(use.map(ld => weekField(data, `skill-${model}-${method}-${metric}-${leadKey(data, ld)}`, "skill")));
  note.remove();
  const grid = stackGrid(), group = mapGroup(root);
  data.leads.forEach(ld => {
    const i = use.indexOf(ld);
    if (i < 0) {grid.append(noteCard(leadName(data, ld), `${model} has no forecast this far ahead from ${data.issue.label}, so it is not in this lead's ensemble.`)); return;}
    const {card, canvas} = rasterCanvas(tip, data, geo, fields[i].value, {group, title: `${leadName(data, ld)} · ${modelTitle(data, model, ld)}`, colorOf: v => pickRgb(DIVERGE, (v + 1) / 2),
      describe: v => [[label, Number.isNaN(v) ? "no value" : num(v, 2)]]});
    grid.append(card); canvases.push(canvas);
  });
  root.append(grid);
  const legend = `${label} · ${metric === "pearson" ? "0 = no linear relationship" : "0 = no better than a climatological forecast built the same way (values below -1 drawn as -1)"}`;
  gradientLegend(root, DIVERGE, -1, 1, legend, 5);
  exportButtons(root, `mme-skill-${model}-${method}-${metric}`, () => stackPng(`${modelTitle(data, model)} · ${how} · ${label} by lead`, canvases, legend), null);
  return root;
}

// M3. Calibrated forecasts of one model (or the ensemble): probabilistic and deterministic, one map per lead
export async function mmeForecastMaps(data, geo, model = "MME", method = "CCA", view = "probability") {
  const names = {probability: "Most likely category and its probability", total: "Forecast total", anomaly: `Forecast minus the ${data.training} mean`,
    percent: `Forecast as % of the ${data.training} mean`, observed: "Observed total", observedAnomaly: `Observed minus the ${data.training} mean`, observedCategory: "Observed category"};
  const observedView = view.startsWith("observed");
  const root = panel("mme-forecast-maps", observedView ? `What happened · ${names[view]}` : `Issued ${data.issue.label} · ${modelTitle(data, model)} · ${method} · ${names[view]}`,
    `${leadTick(data, data.leads[0])} at the top. Each map is a different target ${periodWord(data)}. Hover a pixel for the three category probabilities, the forecast, the observation and the training mean.`);
  const tip = tooltip(root), note = loadingPanel(root), canvases = [], use = data.leads.filter(ld => observedView || isMember(data, model, ld));
  const loaded = await Promise.all(use.map(ld => Promise.all([observedView && model !== "MME" && !isMember(data, model, ld) ? null : weekField(data, `fc-${model}-${method}-${leadKey(data, ld)}`, "fc"), weekField(data, `obs-${leadKey(data, ld)}`, "obs")])));
  note.remove();
  const top = data.rainMax, grid = stackGrid(), half = top / 2, group = mapGroup(root);
  data.leads.forEach(ld => {
    const i = use.indexOf(ld);
    if (i < 0) {grid.append(noteCard(leadName(data, ld), `${model} has no forecast this far ahead from ${data.issue.label}.`)); return;}
    const [f, o] = loaded[i];
    const probs = k => {const b = f.below[k], a = f.above[k], m = 100 - b - a; return [b, m, a];};
    const cell = k => {
      const rows = [];
      if (f) {const p = probs(k); rows.push(["Below / near / above", Number.isNaN(p[0]) ? "–" : `${num(p[0], 0)}% / ${num(p[1], 0)}% / ${num(p[2], 0)}%`], ["Forecast", num(f.total[k], 0) + " mm"]);}
      rows.push([`${data.training} mean`, num(o.mean[k], 0) + " mm"]);
      if (f) rows.push(["Forecast anomaly", `${f.total[k] >= o.mean[k] ? "+" : ""}${num(f.total[k] - o.mean[k], 0)} mm`]);
      rows.push(["Observed", num(o.total[k], 0) + " mm"], ["Observed category", Number.isNaN(o.category[k]) ? "–" : CATEGORY[o.category[k]][0]]);
      return rows;
    };
    let values, colorOf;
    if (view === "probability") {
      values = new Float32Array(f.total.length);
      for (let k = 0; k < values.length; k++) {const p = probs(k); values[k] = Number.isNaN(p[0]) ? NaN : p.indexOf(Math.max(...p)) * 1000 + Math.max(...p);}
      colorOf = v => {const c = Math.floor(v / 1000), p = v - c * 1000; return pickRgb([BELOW, NEAR, ABOVE][c], (p - 33) / (c === 1 ? 27 : 52));};
    }
    else if (view === "total" || view === "observed") {values = view === "total" ? f.total : o.total; colorOf = v => pickRgb(RAIN, Math.sqrt(Math.max(0, v) / top));}
    else if (view === "anomaly" || view === "observedAnomaly") {const a = view === "anomaly" ? f.total : o.total; values = a.map((v, k) => v - o.mean[k]); colorOf = v => pickRgb(DIFF, (v + half) / top);}
    else if (view === "percent") {values = f.total.map((v, k) => o.mean[k] > 0 ? v / o.mean[k] * 100 : NaN); colorOf = v => pickRgb(DIFF, (v - 50) / 100);}
    else {values = o.category; colorOf = v => CATEGORY_RGB[v];}
    const {card, canvas} = rasterCanvas(tip, data, geo, values, {group, title: `${leadName(data, ld)}${observedView ? "" : " · " + modelTitle(data, model, ld)}`, colorOf, describe: (v, k) => cell(k)});
    grid.append(card); canvases.push(canvas);
  });
  root.append(grid);
  let legendText;
  if (view === "probability") {
    legendText = "Colour: the category with the highest probability; darker = more probable (33% to 85%, near normal 33% to 60%)";
    const bar = el("div", "story-legend");
    for (const [name, colors, hi] of [["Below normal", BELOW, 85], ["Near normal", NEAR, 60], ["Above normal", ABOVE, 85]]) {
      const strip = el("div", "story-gradient"); strip.style.background = `linear-gradient(to right,${colors.filter((_, i) => i % 16 === 0).join(",")})`;
      const ends = el("div", "story-legend-ends"); ends.append(el("span", null, `${name} 33%`), el("span", null, `${hi}%+`)); bar.append(strip, ends);
    }
    bar.append(el("p", null, legendText)); root.append(bar);
  }
  else if (view === "total" || view === "observed") {legendText = `${data.rainLegend} (square-root colour scale, 0 to ${top}+)`; gradientLegend(root, RAIN, 0, top, legendText, 5);}
  else if (view === "anomaly" || view === "observedAnomaly") {legendText = `Difference from the ${data.training} mean, ${data.rainLegend} (brown: drier, green: wetter)`; gradientLegend(root, DIFF, -half, half, legendText, 5);}
  else if (view === "percent") {legendText = `Forecast as % of the ${data.training} mean (100 = the mean)`; gradientLegend(root, DIFF, 50, 150, legendText, 5);}
  else {legendText = `Terciles of each target's ${data.training} values at each pixel`; categoryLegend(root, legendText);}
  exportButtons(root, `mme-forecast-${model}-${method}-${view}`, () => stackPng(`Issued ${data.issue.label} · ${modelTitle(data, model)} · ${method} · ${names[view]}`, canvases, legendText), null);
  return root;
}

// A coarse predictor field (one value per model grid cell) with coastlines
function gridCanvas(tip, geo, box, lat, lon, values, {title, colorOf, describe, group}) {
  const full = [box.west, box.east, box.south, box.north], dx = Math.abs(lon[1] - lon[0]), dy = Math.abs(lat[1] - lat[0]);
  const paint = (ctx, win, {pw, ph, x, y}) => {
    const cw = pw * dx / (win[1] - win[0]) + .7, ch = ph * dy / (win[3] - win[2]) + .7;
    lat.forEach((la, j) => lon.forEach((lo, i) => {
      const v = values[j * lon.length + i]; if (v === null) return;
      const c = colorOf(v); ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; ctx.fillRect(x(lo - dx / 2), y(la + dy / 2), cw, ch);
    }));
  };
  const locate = (lo, la) => {
    let i = -1, j = -1; lon.forEach((v, k) => {if (Math.abs(v - lo) <= dx / 2) i = k;}); lat.forEach((v, k) => {if (Math.abs(v - la) <= dy / 2) j = k;});
    if (i < 0 || j < 0 || values[j * lon.length + i] === null) return null;
    return {lon: lon[i], lat: lat[j], show: (e, pin) => tip.show(title, [["Longitude", num(lon[i], 1)], ["Latitude", num(lat[j], 1)], ...describe(values[j * lon.length + i])], e, pin)};
  };
  const map = zoomableMap(tip, geo, group || mapGroup(el("div")), full, title, "Hover or tap a cell; + and - zoom.", paint, locate, false);
  map.redraw();
  return {card: map.card, canvas: map.canvas};
}

const patternCache = new Map();
const loadPatterns = (data, key) => {
  if (!patternCache.has(data.base + key)) patternCache.set(data.base + key, fetch(`${data.base}patterns-${key}.json`).then(r => r.json()));
  return patternCache.get(data.base + key);
};

// M4. EOF patterns and CCA modes of one model at one lead: predictor map, predictand map, score series
export async function mmePatterns(data, geo, lead, model = "CFSv2", kind = "cca", mode = 1) {
  lead = Number(lead); mode = Number(mode);
  const key = leadKey(data, lead), what = kind === "eof" ? `EOF ${mode}` : `CCA mode ${mode}`;
  const root = panel("mme-patterns", `${model} · ${leadName(data, lead)} · ${what}`,
    `From the fit to all of ${data.sample}, not from the cross-validation folds. Loadings are CPT's, scaled so the largest absolute value on each map is 1; only sign and shape carry meaning.`);
  const tip = tooltip(root);
  if (!isMember(data, model, lead)) {root.append(el("p", "story-hint", `${model} has no forecast this far ahead from ${data.issue.label}, so there is no fit for this lead.`)); return root;}
  if (kind === "cca" && mode > 2) {root.append(el("p", "story-hint", "The fits keep two CCA modes; choose mode 1 or 2.")); return root;}
  const note = loadingPanel(root);
  const [all, yField] = await Promise.all([loadPatterns(data, key), kind === "eof" ? weekField(data, `yeof-${key}`, "yeof") : weekField(data, `ycca-${model}-${key}`, "ycca")]);
  note.remove();
  const p = all.models[model], color = v => pickRgb(DIVERGE, (v + 1) / 2);
  const xValues = (kind === "eof" ? p.xEof : p.xCca)[mode - 1], yValues = yField[`m${mode}`];
  const extra = kind === "eof" ? [`${num(p.xVariance[mode - 1], 1)}% of predictor variance`, `${num(p.yVariance[mode - 1], 1)}% of predictand variance`] : [`canonical correlation ${num(p.canonical[mode - 1], 2)}`, `canonical correlation ${num(p.canonical[mode - 1], 2)}`];
  const grid = stackGrid(), canvases = [], group = mapGroup(root);
  const a = gridCanvas(tip, geo, data.predictorBox, p.lat, p.lon, xValues, {group, title: `Predictor (${model} rainfall) · ${what} · ${extra[0]}`, colorOf: color, describe: v => [["Loading (scaled)", num(v, 2)]]});
  const b = rasterCanvas(tip, data, geo, yValues, {group, title: `Predictand (CHIRPS v3.0) · ${what} · ${extra[1]}`, colorOf: color, describe: v => [["Loading (scaled)", Number.isNaN(v) ? "no value" : num(v, 2)]]});
  grid.append(a.card, b.card); canvases.push(a.canvas, b.canvas); root.append(grid);
  gradientLegend(root, DIVERGE, -1, 1, "Loading, scaled to a largest absolute value of 1 on each map", 5);
  const xs = (kind === "eof" ? p.xEofScores : p.xCcaScores)[mode - 1], ys = (kind === "eof" ? p.yEofScores : p.yCcaScores)[mode - 1], years = all.years;
  const std = v => {const m = v.reduce((s, q) => s + q, 0) / v.length, sd = Math.sqrt(v.reduce((s, q) => s + (q - m) ** 2, 0) / v.length) || 1; return v.map(q => (q - m) / sd);};
  const X = std(xs), Y = std(ys), lim = Math.max(2.5, ...X.map(Math.abs), ...Y.map(Math.abs));
  const W = 900, H = 260, L = 60, R = 170, T = 20, B = 40, x = i => L + (i + .5) * (W - L - R) / years.length, y = v => T + (1 - (v + lim) / (2 * lim)) * (H - T - B);
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": `${what} scores by training year`});
  for (const v of [-2, -1, 0, 1, 2]) {svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: v ? "#ece8e0" : "#9a9a94"})); svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, String(v)));}
  years.forEach((yr, i) => {if (yr % 4 === 0 && (i === 0 || years[i - 1] !== yr)) svg.append(sv("text", {x: x(i), y: H - B + 18, "text-anchor": "middle", class: "story-axis"}, String(yr)));});
  [["predictor", X, METHOD_COLORS.CCA], ["predictand", Y, METHOD_COLORS.PCR]].forEach(([name, v, c], k) => {
    svg.append(sv("polyline", {points: v.map((d, i) => `${x(i)},${y(d)}`).join(" "), fill: "none", stroke: c, "stroke-width": years.length > 60 ? 1 : 1.8}));
    v.forEach((d, i) => {const dot = sv("circle", {cx: x(i), cy: y(d), r: years.length > 60 ? 2 : 4, fill: c}); bind(dot, tip, `${what} · ${name} score · ${all.labels ? all.labels[i] : years[i]}`, [["Standardised score", num(d, 2)]]); svg.append(dot);});
    svg.append(sv("circle", {cx: W - R + 18, cy: T + 14 + k * 22, r: 6, fill: c}), sv("text", {x: W - R + 30, y: T + 18 + k * 22, class: "story-axis"}, name));
  });
  svg.append(sv("text", {x: 14, y: T + (H - T - B) / 2, transform: `rotate(-90 14 ${T + (H - T - B) / 2})`, "text-anchor": "middle", class: "story-axis"}, "standardised score"));
  const scroll = el("div", "story-chart-scroll"); scroll.append(el("h4", null, `${what} · scores by ${all.labels ? "training target" : "training target year"}${kind === "cca" ? ` · correlation ${num(p.canonical[mode - 1], 2)}` : ""}`), svg); root.append(scroll);
  exportButtons(root, `mme-${kind}${mode}-${model}-${key}`, () => stackPng(`${model} · ${leadName(data, lead)} · ${what}`, canvases, "Loadings scaled to a largest absolute value of 1"), async () => svgBlob(svg));
  return root;
}

// M5. Flexible forecast of the ensemble: probability of exceeding a climatological percentile, with the curves at a chosen pixel
export async function mmeFlexible(data, geo, lead, percentile = 50) {
  lead = Number(lead); percentile = Number(percentile);
  const key = leadKey(data, lead), nu = data.flexDof[key], t = target(data, lead);
  const root = panel("mme-flexible", `MME (CCA) · chance that ${t.label} exceeds its ${percentile === 50 ? "median" : `${percentile}th percentile`} · ${leadName(data, lead)}`,
    `The threshold at each pixel is the ${percentile === 50 ? "median" : percentile + "th percentile"} of its ${data.training} totals, so climatology alone gives ${100 - percentile}% everywhere. Click or tap a pixel, or use the arrow keys, to draw its curves below.`);
  const tip = tooltip(root), note = loadingPanel(root);
  const [fx, q, o] = await Promise.all([weekField(data, `flex-${key}`, "flex"), weekField(data, `quant-${key}`, "quant"), weekField(data, `obs-${key}`, "obs")]);
  note.remove();
  const thr = q[`q${percentile}`], n = thr.length, poe = new Float32Array(n);
  for (let k = 0; k < n; k++) poe[k] = Number.isNaN(fx.mu[k]) ? NaN : tSf(thr[k], nu, fx.mu[k], fx.scale[k]) * 100;
  const charts = el("div");
  const {nx, west, north, step} = data.grid;
  function draw(k) {
    const p = data.pixels[k], lo = west + (p % nx + .5) * step, la = north - (Math.floor(p / nx) + .5) * step;
    const mu = fx.mu[k], s = fx.scale[k], cmu = fx.cmu[k], cs = fx.cscale[k], ob = o.total[k], th = thr[k];
    const xmin = Math.max(0, Math.min(cmu - 3 * cs, mu - 3 * s)), xmax = Math.max(cmu + 3 * cs, mu + 3 * s, ob * 1.05), N = 160, xs = Array.from({length: N}, (_, i) => xmin + (xmax - xmin) * i / (N - 1));
    charts.replaceChildren();
    const place = `${num(lo, 3)}°E, ${la < 0 ? num(-la, 3) + "°S" : num(la, 3) + "°N"}`;
    charts.append(el("h4", null, `Pixel ${place} · forecast centre ${num(mu, 0)} mm, ${data.training} mean ${num(cmu, 0)} mm, observed ${num(ob, 0)} mm`));
    charts.append(el("p", "story-hint", `Chance of exceeding ${num(th, 0)} mm (the ${percentile === 50 ? "median" : percentile + "th percentile"}): forecast ${num(tSf(th, nu, mu, s) * 100, 0)}%, climatology ${100 - percentile}%. Chance of exceeding the observed ${num(ob, 0)} mm: forecast ${num(tSf(ob, nu, mu, s) * 100, 0)}%.`));
    const W = 900, H = 250, L = 60, R = 200, T = 16, B = 40, x = v => L + (v - xmin) / (xmax - xmin) * (W - L - R);
    const frame = (yMax, yLabel, fmt) => {
      const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": yLabel}), y = v => T + (1 - v / yMax) * (H - T - B);
      for (let i = 0; i <= 4; i++) {const v = yMax * i / 4; svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); if (fmt) svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, fmt(v)));}
      for (let i = 0; i <= 5; i++) {const v = xmin + (xmax - xmin) * i / 5; svg.append(sv("text", {x: x(v), y: H - B + 18, "text-anchor": "middle", class: "story-axis"}, num(v, 0)));}
      svg.append(sv("text", {x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle", class: "story-axis"}, `${periodWord(data)} total (mm)`));
      svg.append(sv("text", {x: 14, y: T + (H - T - B) / 2, transform: `rotate(-90 14 ${T + (H - T - B) / 2})`, "text-anchor": "middle", class: "story-axis"}, yLabel));
      for (const [v, c, dash] of [[th, MUTED, "4 3"], [ob, INK, "none"]]) svg.append(sv("line", {x1: x(v), x2: x(v), y1: T, y2: H - B, stroke: c, "stroke-dasharray": dash, "stroke-width": 1.3}));
      return {svg, y};
    };
    const legend = (svg, items) => items.forEach(([name, c, dash], i) => {svg.append(sv("line", {x1: W - R + 12, x2: W - R + 32, y1: T + 14 + i * 22, y2: T + 14 + i * 22, stroke: c, "stroke-width": 2, "stroke-dasharray": dash || "none"}), sv("text", {x: W - R + 38, y: T + 18 + i * 22, class: "story-axis"}, name));});
    const a = frame(100, "probability of exceedance (%)", v => num(v, 0));
    a.svg.append(sv("polyline", {points: xs.map(v => `${x(v)},${a.y(normSf(v, cmu, cs) * 100)}`).join(" "), fill: "none", stroke: METHOD_COLORS.CCA, "stroke-width": 2}));
    a.svg.append(sv("polyline", {points: xs.map(v => `${x(v)},${a.y(tSf(v, nu, mu, s) * 100)}`).join(" "), fill: "none", stroke: METHOD_COLORS.PCR, "stroke-width": 2.4}));
    data.percentiles.forEach(pc => {const v = q[`q${pc}`][k]; if (v < xmin || v > xmax) return; const dot = sv("circle", {cx: x(v), cy: a.y(100 - pc), r: 5, fill: "#4f8a5a"}); bind(dot, tip, `${pc}th percentile of ${data.training}`, [["Total", num(v, 0) + " mm"], ["Exceeded in", `${100 - pc}% of ${data.sampleUnit || "training years"}`], ["Forecast chance of exceeding it", num(tSf(v, nu, mu, s) * 100, 0) + "%"]]); a.svg.append(dot);});
    legend(a.svg, [["MME forecast", METHOD_COLORS.PCR], ["climatology, fitted normal", METHOD_COLORS.CCA], ["climatology, percentiles", "#4f8a5a"], ["threshold", MUTED, "4 3"], ["observed", INK]]);
    const peak = Math.max(tPdf(mu, nu, mu, s), normPdf(cmu, cmu, cs)) * 1.08, b = frame(peak, "probability density", null);
    b.svg.append(sv("polyline", {points: xs.map(v => `${x(v)},${b.y(normPdf(v, cmu, cs))}`).join(" "), fill: "none", stroke: METHOD_COLORS.CCA, "stroke-width": 2}));
    b.svg.append(sv("polyline", {points: xs.map(v => `${x(v)},${b.y(tPdf(v, nu, mu, s))}`).join(" "), fill: "none", stroke: METHOD_COLORS.PCR, "stroke-width": 2.4}));
    legend(b.svg, [["MME forecast", METHOD_COLORS.PCR], ["climatology, fitted normal", METHOD_COLORS.CCA], ["threshold", MUTED, "4 3"], ["observed", INK]]);
    for (const [title, part] of [["Probability of exceedance", a], ["Probability density", b]]) {const scroll = el("div", "story-chart-scroll"); scroll.append(el("h4", null, title), part.svg); charts.append(scroll);}
  }
  const {card, canvas} = rasterCanvas(tip, data, geo, poe, {group: mapGroup(root), title: `Chance of exceeding the ${percentile === 50 ? "median" : percentile + "th percentile"} (%)`, colorOf: v => pickRgb(POE, v / 100),
    describe: (v, k) => [["Chance of exceeding", Number.isNaN(v) ? "no value" : num(v, 0) + "%"], ["Threshold", num(thr[k], 0) + " mm"], ["Forecast centre", num(fx.mu[k], 0) + " mm"], ["Observed", num(o.total[k], 0) + " mm"]],
    onPick: k => draw(k)});
  root.append(card);
  const legendText = `Chance of exceeding the threshold (%) · brown: drier than usual is more likely, green: wetter · ${100 - percentile}% = climatology`;
  gradientLegend(root, POE, 0, 100, legendText, 5);
  root.append(charts);
  let start = 0, best = Infinity;                       // start at the pixel nearest Jakarta
  data.pixels.forEach((p, k) => {const d = (west + (p % nx + .5) * step - 106.85) ** 2 + (north - (Math.floor(p / nx) + .5) * step + 6.2) ** 2; if (d < best) {best = d; start = k;}});
  draw(start);
  exportButtons(root, `mme-exceedance-${key}-p${percentile}`, () => stackPng(`MME (CCA) · chance that ${t.label} exceeds its ${percentile === 50 ? "median" : percentile + "th percentile"}`, [canvas], legendText), null);
  return root;
}

// M6. The forecasts as issued, scored against what happened, for every member and the ensemble
export function mmeScoresByLead(data, method = "CCA", metric = "hit") {
  const names = {hit: "Hit rate of the most likely category (%)", rpss: "RPSS against 33/34/33% odds", rmse: "RMSE of the deterministic forecast (mm)"};
  const key = {hit: "hit rate (%)", rpss: "RPSS", rmse: "RMSE (mm)"}[metric];
  const root = panel("mme-scores-by-lead", `Issued ${data.issue.label} · ${method} · ${names[metric]}`,
    (metric === "hit" ? "Grey squares: always forecasting the category that covered most of the area (chosen with hindsight). " : metric === "rpss" ? "0 is no better than 33/34/33% odds. " : "") + `One outcome per lead: this describes ${data.outcomeLabel || "2023-24"}, not skill.`);
  const tip = tooltip(root), rows = data.scores2023.filter(r => r.method === method), refs = data.references, n = data.leads.length;
  const vals = rows.map(r => r[key]).concat(metric === "hit" ? refs.map(r => r["reference hit rate (%)"]) : metric === "rpss" ? [0] : []);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * .12 || 1;
  const W = 900, H = 340, L = 70, R = 190, T = 20, B = 56, y = v => T + (1 - (v - (lo - pad)) / (hi - lo + 2 * pad)) * (H - T - B), x = i => L + (i + .5) * (W - L - R) / n;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": names[metric]});
  for (let i = 0; i <= 4; i++) {const v = lo - pad + (hi - lo + 2 * pad) * i / 4; svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, num(v, metric === "rpss" ? 2 : 0)));}
  if (metric === "rpss") svg.append(sv("line", {x1: L, x2: W - R, y1: y(0), y2: y(0), stroke: MUTED, "stroke-dasharray": "6 4"}));
  data.leads.forEach((ld, i) => {svg.append(sv("text", {x: x(i), y: H - B + 20, "text-anchor": "middle", class: "story-axis"}, leadTick(data, ld))); svg.append(sv("text", {x: x(i), y: H - B + 38, "text-anchor": "middle", class: "story-axis"}, target(data, ld).label));});
  if (metric === "hit") refs.forEach((r, i) => {const q = sv("rect", {x: x(i) - 8, y: y(r["reference hit rate (%)"]) - 8, width: 16, height: 16, fill: "#c9c6bd"}); bind(q, tip, `Reference · ${r.target}`, [["Always forecasting", r["reference category"]], ["Hit rate", num(r["reference hit rate (%)"], 1) + "%"]]); svg.append(q);});
  data.models.forEach((m, k) => {
    const color = modelColor(data, m), bold = m === "MME", pts = data.leads.map((ld, i) => [i, rows.find(r => r.lead === ld && r.model === m)]).filter(([, r]) => r);
    svg.append(sv("polyline", {points: pts.map(([i, r]) => `${x(i)},${y(r[key])}`).join(" "), fill: "none", stroke: color, "stroke-width": bold ? 3 : 1.2, opacity: bold ? 1 : .7}));
    pts.forEach(([i, r]) => {const c = sv("circle", {cx: x(i), cy: y(r[key]), r: bold ? 6 : 4.5, fill: color}); bind(c, tip, `${m} · ${method} · ${leadTick(data, r.lead)} · ${r.target}`, [[names[metric], num(r[key], metric === "rpss" ? 3 : 1)]]); svg.append(c);});
    svg.append(sv("line", {x1: W - R + 12, x2: W - R + 32, y1: T + 14 + k * 22, y2: T + 14 + k * 22, stroke: color, "stroke-width": bold ? 3 : 1.6}), sv("text", {x: W - R + 38, y: T + 18 + k * 22, class: "story-axis", "font-weight": bold ? 700 : 400}, m));
  });
  if (metric === "hit") svg.append(sv("rect", {x: W - R + 14, y: T + 8 + data.models.length * 22, width: 14, height: 14, fill: "#c9c6bd"}), sv("text", {x: W - R + 38, y: T + 20 + data.models.length * 22, class: "story-axis"}, "reference"));
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `mme-scores-${method}-${metric}`, null, async () => svgBlob(svg));
  return root;
}
