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
const unitText = data => ({month: "mm in the month", season: "mm in the season"}[data.target?.kind] || "mm per dekad");
const trainingText = data => data.target ? "1991-2020" : "2000-2018";
const sampleText = data => data.target ? "the 30 training years, 1991-2020" : "the 171 training dekads of 2000-2018";
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
    `Area-weighted mean over Indonesia's 3,240 cells. ${rawTitle(data)} involves no fitting, so it is scored by correlation only.`);
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
// Views for the monthly and seasonal cases (one target, six start dates)

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthIndex = s => {const d = new Date(s + "T00:00:00Z"); return d.getUTCFullYear() * 12 + d.getUTCMonth();};

// 6. When each forecast starts, relative to the target month or season
export function startTimeline(data, lead) {
  lead = Number(lead);
  const root = panel("start-timeline", `${data.target.label}: forecasts started one to six months before`,
    "Each dot is a start date (the model run used); the block is the target. Hover for dates and the lead.");
  const tip = tooltip(root), first = Math.min(...data.leadStarts.map(monthIndex)), last = monthIndex(data.target.end);
  const W = 900, H = 170, L = 40, R = 30, x = m => L + (m - first) / (last - first) * (W - L - R);
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Start dates and the target"});
  svg.append(sv("line", {x1: L, x2: W - R, y1: 120, y2: 120, stroke: LINE}));
  for (let m = first; m <= last; m++) {
    svg.append(sv("line", {x1: x(m), x2: x(m), y1: 115, y2: 125, stroke: LINE}));
    if (m < last) svg.append(sv("text", {x: (x(m) + x(m + 1)) / 2, y: 145, "text-anchor": "middle", class: "story-axis"}, MONTHS[m % 12]));
  }
  const t0 = monthIndex(data.target.start), target = sv("g");
  target.append(sv("rect", {x: x(t0), y: 40, width: x(last) - x(t0) - 2, height: 40, rx: 6, fill: "#1f4fa3", opacity: .85}));
  target.append(sv("text", {x: (x(t0) + x(last)) / 2, y: 65, "text-anchor": "middle", fill: "white", "font-size": 14, "font-weight": 600}, data.target.label));
  bind(target, tip, "Target", [["Period", data.target.label]]); svg.append(target);
  data.leads.forEach((ld, i) => {
    const m = monthIndex(data.leadStarts[i]), on = ld === lead;
    const g = sv("g"); g.append(sv("circle", {cx: x(m), cy: 120, r: on ? 9 : 6, fill: on ? "#c48a1d" : "#9a9a94"}));
    if (on) {
      g.append(sv("line", {x1: x(m), x2: x(t0), y1: 100, y2: 100, stroke: "#c48a1d", "stroke-width": 2, "marker-end": "none"}));
      g.append(sv("text", {x: (x(m) + x(t0)) / 2, y: 94, "text-anchor": "middle", class: "story-axis", "font-weight": 600}, leadName(data, ld)));
    }
    bind(g, tip, leadName(data, ld), [["Start", fmtDate(data.leadStarts[i]) + " " + data.leadStarts[i].slice(0, 4)], ["Target", data.target.label]]);
    svg.append(g);
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `start-timeline-${lead}`, null, async () => svgBlob(svg));
  return root;
}

// 7. The 2023 forecasts at every lead, one column, with the observation on top
export function leadForecastMaps(data, geo, method = "CCA", view = "total") {
  const names = {total: "forecast total", difference: "forecast minus observed", category: "most likely category"};
  const root = panel("lead-forecast-maps", `${data.target.label} · ${method} · ${names[view]} at each lead`,
    "The observation is at the top, then the forecasts from one to six months ahead. Hover a cell for every value.");
  const tip = tooltip(root), canvases = [], grid = el("div"); grid.style.display = "grid"; grid.style.gap = ".8rem";
  const obs = data.observed, top = rainMax(data);
  const cell = (k, f) => [["Observed", num(obs.total[k], 0) + " mm"], ["1991-2020 mean", num(obs.mean[k], 0) + " mm"],
    ["Observed category", obs.category[k] === null ? "–" : CATEGORY[obs.category[k]][0]],
    ...(f ? [["Forecast", num(f.total[k], 0) + " mm"], ["Most likely", f.category[k] === null ? "–" : `${CATEGORY[f.category[k]][0]} (${num(f.probability[k], 0)}%)`]] : [])];
  const rain = v => pick(RAIN, Math.sqrt(Math.max(0, v) / top)), cat = v => CATEGORY[v][1], diff = v => pick(DIFF, (v + top / 2) / top);
  const first = view === "category" ? {values: obs.category, colorOf: cat} : {values: obs.total, colorOf: rain};
  const o = mapCanvas(tip, data, geo, first.values, {title: `Observed · ${data.target.label}`, colorOf: first.colorOf, describe: (v, k) => cell(k, null)});
  grid.append(o.card); canvases.push(o.canvas);
  data.leads.forEach((ld, i) => {
    const f = data.forecasts[ld][method];
    const values = view === "total" ? f.total : view === "category" ? f.category
      : f.total.map((v, k) => v === null || obs.total[k] === null ? null : v - obs.total[k]);
    const colorOf = view === "total" ? rain : view === "category" ? cat : diff;
    const {card, canvas} = mapCanvas(tip, data, geo, values, {title: `${leadName(data, ld)} · started ${fmtDate(data.leadStarts[i])}`, colorOf,
      describe: (v, k) => view === "difference" ? [["Difference", num(v, 0) + " mm"], ...cell(k, f)] : cell(k, f)});
    grid.append(card); canvases.push(canvas);
  });
  root.append(grid);
  let legendText;
  if (view === "category") {legendText = "Tercile categories"; categoryLegend(root, "Top map: observed category. Below: the category with the highest forecast probability.");}
  else if (view === "difference") {legendText = `Top map: observed total. Below: forecast minus observed (${unitText(data)}; brown too dry, green too wet)`;
    gradientLegend(root, RAIN, 0, top, `Observed total, ${unitText(data)} (square-root scale)`, 4); gradientLegend(root, DIFF, -top / 2, top / 2, "Forecast minus observed (mm)", 5);}
  else {legendText = `${unitText(data)} (square-root colour scale, 0 to ${top}+)`; gradientLegend(root, RAIN, 0, top, legendText, 4);}
  exportButtons(root, `forecasts-${method}-${view}`, () => stackPng(`${data.target.label} · ${method} · ${names[view]}`, canvases, legendText), null);
  return root;
}

// 8. The 2023 outcome by lead: mean forecast vs observed, hit rate, RPSS
export function scoresByLead(data, metric = "mean") {
  const names = {mean: "Area-weighted forecast total", hit: "Hit rate of the most likely category (%)", rpss: "RPSS against climatological odds"};
  const key = {mean: "mean forecast (mm)", hit: "hit rate (%)", rpss: "RPSS 2023"}[metric];
  const root = panel("scores-by-lead", `${data.target.label} · ${names[metric]}`,
    metric === "mean" ? "Dashed: observed area-weighted total; dotted: the 1991-2020 mean." :
    metric === "hit" ? "Dashed: always forecasting the most frequent observed category." : "0 is no better than 33/34/33% odds. One target: this rewards leaning the right way in 2023, not skill in general.");
  const tip = tooltip(root), rows = data.scores2023, n = data.leads.length;
  let ref = null, ref2 = null;
  if (metric === "mean") {ref = areaMean(data, data.observed.total); ref2 = areaMean(data, data.observed.mean);}
  if (metric === "hit") {const sh = [0, 1, 2].map(c => areaMean(data, data.observed.category.map(v => v === null ? null : (v === c ? 100 : 0)))); ref = Math.max(...sh);}
  if (metric === "rpss") ref = 0;
  const vals = rows.map(r => r[key]).concat([ref, ref2].filter(v => v !== null)), lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * .15 || 1;
  const W = 900, H = 300, L = 70, R = 150, T = 20, B = 50, y = v => T + (1 - (v - (lo - pad)) / (hi - lo + 2 * pad)) * (H - T - B), x = i => L + (i + .5) * (W - L - R) / n;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": names[metric]});
  for (let i = 0; i <= 4; i++) {const v = lo - pad + (hi - lo + 2 * pad) * i / 4; svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ece8e0"})); svg.append(sv("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "story-axis"}, num(v, metric === "rpss" ? 2 : 0)));}
  for (const [v, dash, label] of [[ref, "6 4", metric === "mean" ? "observed" : metric === "hit" ? "reference" : "no skill"], [ref2, "2 3", "1991-2020 mean"]]) {
    if (v === null) continue;
    svg.append(sv("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: MUTED, "stroke-dasharray": dash}), sv("text", {x: W - R + 8, y: y(v) + 4, class: "story-axis"}, `${label} ${num(v, metric === "rpss" ? 2 : 1)}`));
  }
  data.leads.forEach((ld, i) => svg.append(sv("text", {x: x(i), y: H - B + 20, "text-anchor": "middle", class: "story-axis"}, leadName(data, ld).replace(" ahead", ""))));
  ["CCA", "PCR"].forEach((m, k) => {
    const pts = data.leads.map(ld => rows.find(r => r.lead === ld && r.method === m));
    svg.append(sv("polyline", {points: pts.map((r, i) => `${x(i) + (k - .5) * 14},${y(r[key])}`).join(" "), fill: "none", stroke: METHOD_COLORS[m], "stroke-width": 1.3, opacity: .5}));
    pts.forEach((r, i) => {const c = sv("circle", {cx: x(i) + (k - .5) * 14, cy: y(r[key]), r: 6, fill: METHOD_COLORS[m]}); bind(c, tip, `${m} · ${leadName(data, r.lead)}`, [[names[metric], num(r[key], metric === "rpss" ? 3 : 1)]]); svg.append(c);});
    svg.append(sv("circle", {cx: W - R + 14, cy: T + 60 + k * 22, r: 6, fill: METHOD_COLORS[m]}), sv("text", {x: W - R + 26, y: T + 64 + k * 22, class: "story-axis"}, m));
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, `scores-${metric}`, null, async () => svgBlob(svg));
  return root;
}

// 9. Season vs month: CCA and raw correlation at each lead
export function compareScales(data) {
  const root = panel("compare-scales", "Area-weighted mean correlation · OND (filled) and November (open)",
    "The same model, observations, grid, settings and lead definition. CCA is cross-validated; the raw model involves no fitting.");
  const tip = tooltip(root), rows = data.comparison, n = data.leads.length;
  const vals = rows.flatMap(r => [r["Pearson, OND"], r["Pearson, November"]]), lo = Math.min(0, ...vals) - .05, hi = Math.max(...vals) + .05;
  const W = 900, H = 90 + n * 62, L = 150, R = 190, T = 20, B = 40, x = v => L + (v - lo) / (hi - lo) * (W - L - R), y = (i, k) => T + (i + .5) * (H - T - B) / n + (k - .5) * 18;
  const svg = sv("svg", {viewBox: `0 0 ${W} ${H}`, class: "story-svg", role: "group", "aria-label": "Seasonal and monthly correlation by lead"});
  for (let i = 0; i <= 4; i++) {const v = lo + (hi - lo) * i / 4; svg.append(sv("line", {x1: x(v), x2: x(v), y1: T, y2: H - B, stroke: "#ece8e0"})); svg.append(sv("text", {x: x(v), y: H - B + 18, "text-anchor": "middle", class: "story-axis"}, num(v, 2)));}
  data.leads.forEach((ld, i) => svg.append(sv("text", {x: L - 12, y: y(i, .5) + 4, "text-anchor": "end", class: "story-axis"}, leadName(data, ld))));
  [["CCA", METHOD_COLORS.CCA], [rawName(data), METHOD_COLORS.raw]].forEach(([m, color], k) => {
    data.leads.forEach((ld, i) => {
      const r = rows.find(q => q.lead === ld && q.method === m), a = r["Pearson, November"], b = r["Pearson, OND"];
      svg.append(sv("line", {x1: x(a), x2: x(b), y1: y(i, k), y2: y(i, k), stroke: color, opacity: .5}));
      const open = sv("circle", {cx: x(a), cy: y(i, k), r: 6, fill: "white", stroke: color, "stroke-width": 2}), full = sv("circle", {cx: x(b), cy: y(i, k), r: 6, fill: color});
      for (const c of [open, full]) bind(c, tip, `${m} · ${leadName(data, ld)}`, [["OND", num(b, 3)], ["November", num(a, 3)], ["OND minus November", num(b - a, 3)]]);
      svg.append(open, full);
    });
    svg.append(sv("circle", {cx: W - R + 18, cy: T + 14 + k * 44, r: 6, fill: color}), sv("text", {x: W - R + 30, y: T + 18 + k * 44, class: "story-axis"}, `${m}, OND`),
               sv("circle", {cx: W - R + 18, cy: T + 36 + k * 44, r: 6, fill: "white", stroke: color, "stroke-width": 2}), sv("text", {x: W - R + 30, y: T + 40 + k * 44, class: "story-axis"}, `${m}, November`));
  });
  const scroll = el("div", "story-chart-scroll"); scroll.append(svg); root.append(scroll);
  exportButtons(root, "seasonal-vs-monthly", null, async () => svgBlob(svg));
  return root;
}
