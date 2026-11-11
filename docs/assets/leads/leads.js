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
    for (const [part, type, partScale] of data.layout[kind]) {
      const Type = {i16: Int16Array, u16: Uint16Array, u8: Uint8Array}[type], missing = {i16: -32768, u16: 65535, u8: 255}[type];
      const raw = new Type(buffer, offset, n), s = partScale || scale, values = new Float32Array(n);
      for (let i = 0; i < n; i++) values[i] = raw[i] === missing ? NaN : raw[i] / s;
      out[part] = values; offset += raw.byteLength;
    }
    return out;
  });
  fieldCache.set(name, promise);
  return promise;
}

const leadKey = (data, lead) => data.leadKeys[data.leads.indexOf(lead)];
const leadOfKey = (data, key) => data.leads[data.leadKeys.indexOf(key)];

// One 0.05° map: the field is drawn as an image (one image pixel per grid pixel), boundaries on top
function rasterCanvas(tip, data, geo, values, {title, colorOf, describe}) {
  const card = el("div", "story-map-card"), canvas = el("canvas"); card.append(el("h4", null, title), canvas);
  canvas.dataset.title = title; canvas.tabIndex = 0; canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `${title}. Hover or tap a pixel; arrow keys move between pixels.`);
  const {west, north, step, nx, ny} = data.grid, extent = [west, west + nx * step, north - ny * step, north];
  const W = 960, L = 56, R = 16, T = 16, B = 46;
  const pw = W - L - R, ph = pw * (extent[3] - extent[2]) / (extent[1] - extent[0]), H = Math.ceil(ph + T + B);
  canvas.width = W; canvas.height = H; canvas.style.aspectRatio = `${W}/${H}`;
  const ctx = canvas.getContext("2d"), x = v => L + (v - extent[0]) / (extent[1] - extent[0]) * pw, y = v => T + (extent[3] - v) / (extent[3] - extent[2]) * ph;
  ctx.fillStyle = "white"; ctx.fillRect(0, 0, W, H); ctx.save(); ctx.beginPath(); ctx.rect(L, T, pw, ph); ctx.clip();
  const drawLayer = (layer, fill) => {
    for (const f of layer.features) for (const ring of rings(f.geometry)) {
      ctx.beginPath(); ring.forEach((p, i) => i ? ctx.lineTo(x(p[0]), y(p[1])) : ctx.moveTo(x(p[0]), y(p[1]))); ctx.closePath();
      if (fill) {ctx.fillStyle = "#eceae4"; ctx.fill();} ctx.strokeStyle = "#7d8580"; ctx.lineWidth = .6; ctx.stroke();
    }
  };
  drawLayer(geo.neighbours, true); drawLayer(geo.indonesia, true);
  const image = new ImageData(nx, ny);
  data.pixels.forEach((p, k) => {
    const v = values[k]; if (Number.isNaN(v)) return;
    const c = colorOf(v); image.data.set([c[0], c[1], c[2], 255], p * 4);
  });
  const raster = el("canvas"); raster.width = nx; raster.height = ny; raster.getContext("2d").putImageData(image, 0, 0);
  ctx.imageSmoothingEnabled = false; ctx.drawImage(raster, L, T, pw, ph);
  drawLayer(geo.provinces, false); ctx.restore();
  ctx.strokeStyle = LINE; ctx.strokeRect(L, T, pw, ph); ctx.fillStyle = MUTED; ctx.font = "20px Arial"; ctx.textAlign = "center";
  for (let lo = 100; lo <= 140; lo += 10) ctx.fillText(`${lo}°E`, x(lo), T + ph + 30);
  ctx.textAlign = "right"; for (const la of [-10, -5, 0, 5]) ctx.fillText(la < 0 ? `${-la}°S` : la > 0 ? `${la}°N` : "0°", L - 6, y(la) + 6);
  let current = 0;
  const centre = k => {const p = data.pixels[k]; return [west + (p % nx + .5) * step, north - (Math.floor(p / nx) + .5) * step];};
  function show(k, e, pin = false) {
    if (k === undefined || k < 0) return; current = k; const [lo, la] = centre(k);
    tip.show(title, [["Longitude", num(lo, 3)], ["Latitude", num(la, 3)], ...describe(values[k], k)], e, pin);
  }
  function hit(e, pin = false) {
    const b = canvas.getBoundingClientRect(), px = (e.clientX - b.left) * W / b.width, py = (e.clientY - b.top) * H / b.height;
    const col = Math.floor((px - L) / pw * nx), row = Math.floor((py - T) / ph * ny);
    const k = col >= 0 && col < nx && row >= 0 && row < ny ? data.lookup[row * nx + col] : -1;
    if (k >= 0) show(k, e, pin); else tip.leave();
  }
  canvas.addEventListener("pointermove", e => hit(e)); canvas.addEventListener("click", e => hit(e, true)); canvas.addEventListener("pointerleave", tip.leave);
  canvas.addEventListener("focus", e => show(current, e));
  canvas.addEventListener("keydown", e => {
    const d = {ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[e.key]; if (!d) return; e.preventDefault();
    const p = data.pixels[current], col = p % nx, row = Math.floor(p / nx);
    for (let s = 1; s < 200; s++) {
      const c = col + d[0] * s, r = row + d[1] * s; if (c < 0 || c >= nx || r < 0 || r >= ny) break;
      const k = data.lookup[r * nx + c]; if (k >= 0) {show(k, e, true); return;}
    }
  });
  return {card, canvas};
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
  const grid = el("div"); grid.style.display = "grid"; grid.style.gap = ".8rem";
  data.leads.forEach((lead, i) => {
    const values = fields[i].value;
    const {card, canvas} = rasterCanvas(tip, data, geo, values, {title: leadName(data, lead), colorOf: v => pickRgb(DIVERGE, (v - lo) / (hi - lo)),
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
  note.remove();
  const grid = el("div"); grid.style.display = "grid"; grid.style.gap = ".8rem";
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
    const {card, canvas} = rasterCanvas(tip, data, geo, values, {title: `${leadName(data, leadOfKey(data, t.lead))} · ${fmtDate(t.start)} to ${fmtDate(end)}`, colorOf, describe});
    grid.append(card); canvases.push(canvas);
  });
  root.append(grid);
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
    bind(r, tip, `Week from ${fmtDate(starts[i])}`, [["Observed", num(s.observed[i], 1) + " mm"], ["2000-2018 mean", num(s.mean_2000_2018[i], 1) + " mm"],
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
