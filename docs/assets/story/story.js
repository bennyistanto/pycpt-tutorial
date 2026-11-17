import {exceedanceCurves, tSf, normSf} from "../leads/leads.js";
// Presentation only. Every aggregate score comes from the verified Python outputs.
const NS = "http://www.w3.org/2000/svg";
const INK = "#182e39", MUTED = "#566974";
const COLORS = {"Raw CFSv2":"#9b7164", Climatology:"#6b7280", CCA:"#147d92", PCR:"#c08325"};
let sequence = 0;
const el = (tag, cls, text) => {const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n;};
const sv = (tag, attrs={}, text) => {const n=document.createElementNS(NS,tag); for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v); if(text!==undefined)n.textContent=text; return n;};
const num = (v,d=1) => Number.isFinite(v) ? v.toLocaleString("en",{minimumFractionDigits:d,maximumFractionDigits:d}) : "—";
const periodLabel = p => p==="1983_2010" ? "1983–2010" : "1991–2020";
const method = id => id.startsWith("raw") ? "Raw CFSv2" : id.startsWith("climatology") ? "Climatology" : id.slice(0,3).toUpperCase();
const chosen = p => ["raw_cfsv2",`climatology_${p}`,`cca_${p}`,`pcr_${p}`];
const metricName = m => ({rmse:"RMSE",mae:"MAE",bias:"Bias"}[m] || m);
const palette = (colors,t) => colors[Math.max(0,Math.min(colors.length-1,Math.round(t*(colors.length-1))))];
document.addEventListener("keydown",e=>{if(e.key==="Escape")document.querySelectorAll('.story-tooltip').forEach(n=>n.dispatchEvent(new Event('story-dismiss')));});
document.addEventListener("pointerdown",e=>document.querySelectorAll('.story-tooltip:not([hidden])').forEach(n=>{if(!n.closest('.story-view')?.contains(e.target))n.dispatchEvent(new Event('story-dismiss'));}));

export function selectControl(label, options, value) {
  const form=el("form","story-control"), id=`story-select-${++sequence}`;
  const lab=el("label",null,label); lab.htmlFor=id;
  const select=el("select"); select.id=id; select.setAttribute("aria-label",label);
  for(const option of options) {const [v,l]=Array.isArray(option)?option:[option,option]; const n=el("option",null,l); n.value=v; select.append(n);}
  select.value=value; form.append(lab,select);
  Object.defineProperty(form,"value",{get:()=>select.value});
  select.addEventListener("change",()=>form.dispatchEvent(new Event("input",{bubbles:true})));
  form.addEventListener("submit",e=>e.preventDefault());
  return form;
}

function panel(id,title,hint) {
  const root=el("div","story-view"); root.dataset.view=id;
  root.append(el("h3","story-chart-title",title),el("p","story-hint",hint));
  const actions=el("div","story-export"),button=el("button",null,"Download current view (PNG)"),status=el("span","story-export-status");
  const formats=[[button,"PNG",currentViewPng]];
  if(!["rainfall","error-maps"].includes(id))formats.push([el("button",null,"Download current view (SVG)"),"SVG",currentViewSvg]);
  status.setAttribute("aria-live","polite");actions.append(...formats.map(([b])=>b),status);root.append(actions);
  for(const [button,format,create]of formats){button.type="button";button.onclick=async()=>{
    formats.forEach(([b])=>b.disabled=true);status.textContent=`Preparing ${format}…`;
    try{
      if(root.dataset.ready!=="true")throw new Error("Wait for the maps to finish loading, then try again.");
      await new Promise(resolve=>requestAnimationFrame(resolve));
      const image=await create(root),url=URL.createObjectURL(image),a=el("a");
      a.href=url;a.download=`pycpt-${id}-${root.dataset.exportKey||"current"}.${format.toLowerCase()}`;a.click();
      setTimeout(()=>URL.revokeObjectURL(url),60000);status.textContent=`${format} ready · includes the current selections and legend.`;
    }catch(error){status.textContent=`${format} could not be created: ${error.message}`;}
    finally{formats.forEach(([b])=>b.disabled=false);}
  };}
  root.dataset.ready="true";
  return root;
}

// Export the full chart, not its scrolled viewport or a screenshot of page controls.
// This composes presentation marks only; it never fits a model or changes scores.
function chartSvg(root) {
  const source=root.querySelector("svg.story-svg");if(!source)throw new Error("This chart is not ready yet.");
  const clone=source.cloneNode(true),box=source.viewBox.baseVal;
  clone.setAttribute("width",box.width);clone.setAttribute("height",box.height);
  // Keep explicit light/dark tile labels; do not inherit page hover/focus highlights.
  const style=sv("style",{},"text{font-family:Arial,sans-serif} .story-axis{font-size:12px;fill:#365461} .story-province-label{font-size:11px;fill:#365461} .story-cell-number{font-size:14px;font-weight:600}");
  clone.prepend(style);
  for(const mark of clone.querySelectorAll('[role="button"]')){mark.removeAttribute("role");mark.removeAttribute("tabindex");}
  return clone;
}

async function svgGraphic(root) {
  const clone=chartSvg(root),box=clone.viewBox.baseVal;
  const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:"image/svg+xml;charset=utf-8"}));
  const image=new Image();
  try{image.src=url;await image.decode();return {image,width:box.width,height:box.height};}
  finally{URL.revokeObjectURL(url);}
}

function textLines(ctx,text,width) {
  const lines=[];let line="";
  for(const word of text.split(/\s+/)){const next=line?`${line} ${word}`:word;if(line&&ctx.measureText(next).width>width){lines.push(line);line=word;}else line=next;}
  if(line)lines.push(line);return lines;
}

function currentViewSvg(root) {
  const chart=chartSvg(root),box=chart.viewBox.baseVal,pad=32,width=box.width+2*pad;
  const output=sv("svg",{width,role:"img","font-family":"Arial, sans-serif"});
  const title=root.querySelector(".story-chart-title").textContent;
  output.append(sv("title",{},title),sv("desc",{},"Current tutorial selections with labels and legends. Vector marks and editable text; no embedded raster images."));
  const background=sv("rect",{width,height:1,fill:"white"});output.append(background);
  const ctx=el("canvas").getContext("2d");let y=pad;
  function text(value,size,color=INK,gap=10){
    const weight=size>=22?600:400;ctx.font=`${weight} ${size}px Arial, sans-serif`;
    const lines=textLines(ctx,value,box.width),lineHeight=Math.ceil(size*1.4);
    for(const line of lines){output.append(sv("text",{x:pad,y:y+size,"font-size":size,"font-weight":weight,fill:color},line));y+=lineHeight;}
    y+=gap;
  }
  text(title,24);
  if(root.dataset.exportNote)text(root.dataset.exportNote,16,MUTED);
  for(const note of root.querySelectorAll(".story-support-note"))text(note.textContent,14,MUTED);
  chart.setAttribute("x",pad);chart.setAttribute("y",y);output.append(chart);y+=box.height+18;
  for(const node of root.querySelectorAll(".story-legend,.story-key")){
    if(node.exportLegend){
      const {colors,min,max,label}=node.exportLegend,barWidth=Math.min(440,box.width),id=`export-gradient-${++sequence}`;
      const defs=sv("defs"),gradient=sv("linearGradient",{id,x1:0,x2:1,y1:0,y2:0});
      const stops=colors.filter((_,i)=>i%16===0);stops.forEach((color,i)=>gradient.append(sv("stop",{offset:`${100*i/(stops.length-1)}%`,"stop-color":color})));
      defs.append(gradient);output.append(defs,sv("rect",{x:pad,y,width:barWidth,height:16,fill:`url(#${id})`}));
      for(const [t,v]of [[0,min],[.5,(min+max)/2],[1,max]])output.append(sv("text",{x:pad+t*barWidth,y:y+37,"font-size":14,fill:MUTED,"text-anchor":t===0?"start":t===1?"end":"middle"},num(v,0)));
      y+=52;text(label,14,MUTED);
    }else if(node.exportSeries){
      for(const {name,color,dashed}of node.exportSeries){
        output.append(sv("line",{x1:pad,x2:pad+24,y1:y+8,y2:y+8,stroke:color,"stroke-width":3,"stroke-dasharray":dashed?"5 4":"none"}),sv("text",{x:pad+34,y:y+14,"font-size":14,fill:INK},name));y+=25;
      }
    }else text(node.textContent,14,MUTED);
  }
  text("PyCPT tutorial · snapshot of the current view · verified saved outputs",12,MUTED,0);
  const height=y+pad;output.setAttribute("height",height);output.setAttribute("viewBox",`0 0 ${width} ${height}`);background.setAttribute("height",height);
  return new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n',new XMLSerializer().serializeToString(output)],{type:"image/svg+xml;charset=utf-8"});
}

async function currentViewPng(root) {
  const graphic=root.exportGraphic?await root.exportGraphic():await svgGraphic(root);
  const pad=32,width=graphic.width+pad*2,canvas=el("canvas"),scale=2,ctx=canvas.getContext("2d");
  const blocks=[];
  function text(text,size,color=INK,gap=10){
    ctx.font=`${size>=22?"600 ":""}${size}px Arial, sans-serif`;
    const lines=textLines(ctx,text,graphic.width),lineHeight=Math.ceil(size*1.4);
    blocks.push({height:lines.length*lineHeight+gap,draw:(c,y)=>{c.font=`${size>=22?"600 ":""}${size}px Arial, sans-serif`;c.fillStyle=color;lines.forEach((line,i)=>c.fillText(line,pad,y+i*lineHeight));}});
  }
  text(root.querySelector(".story-chart-title").textContent,24);
  if(root.dataset.exportNote)text(root.dataset.exportNote,16,MUTED);
  for(const note of root.querySelectorAll(".story-map-dates,.story-support-note"))text(note.textContent,14,MUTED);
  blocks.push({height:graphic.height+18,draw:(c,y)=>c.drawImage(graphic.image,pad,y,graphic.width,graphic.height)});
  for(const node of root.querySelectorAll(".story-legend,.story-key")){
    if(node.exportLegend){
      const {colors,min,max,label}=node.exportLegend,barWidth=Math.min(440,graphic.width);
      blocks.push({height:52,draw:(c,y)=>{
        const gradient=c.createLinearGradient(pad,0,pad+barWidth,0),stops=colors.filter((_,i)=>i%16===0);
        stops.forEach((color,i)=>gradient.addColorStop(i/(stops.length-1),color));c.fillStyle=gradient;c.fillRect(pad,y,barWidth,16);
        c.font="14px Arial, sans-serif";c.fillStyle=MUTED;
        for(const [t,v]of [[0,min],[.5,(min+max)/2],[1,max]]){c.textAlign=t===0?"left":t===1?"right":"center";c.fillText(num(v,0),pad+t*barWidth,y+23);}c.textAlign="left";
      }});text(label,14,MUTED);
    }else if(node.exportSeries){
      for(const {name,color,dashed}of node.exportSeries)blocks.push({height:25,draw:(c,y)=>{
        c.strokeStyle=color;c.lineWidth=3;c.setLineDash(dashed?[5,4]:[]);c.beginPath();c.moveTo(pad,y+8);c.lineTo(pad+24,y+8);c.stroke();c.setLineDash([]);
        c.font="14px Arial, sans-serif";c.fillStyle=INK;c.fillText(name,pad+34,y);
      }});
    }else text(node.textContent,14,MUTED);
  }
  text("PyCPT tutorial · snapshot of the current view · verified saved outputs",12,MUTED,0);
  const height=pad*2+blocks.reduce((h,b)=>h+b.height,0);canvas.width=width*scale;canvas.height=height*scale;
  ctx.scale(scale,scale);ctx.fillStyle="white";ctx.fillRect(0,0,width,height);ctx.textBaseline="top";
  let y=pad;for(const block of blocks){block.draw(ctx,y);y+=block.height;}
  return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error("The browser could not encode the image.")),"image/png"));
}

function tooltip(root) {
  const tip=el("div","story-tooltip"); tip.hidden=true; tip.setAttribute("role","tooltip");
  const readout=el("p","story-readout","Hover, tap, or use the arrow keys on a chart to inspect a value.");
  readout.setAttribute("aria-live","polite"); root.append(readout,tip);
  let pinned=false;
  const hide=()=>{tip.hidden=true;pinned=false;};
  tip.addEventListener('story-dismiss',hide);
  function show(title,entries,event,pin=false) {
    if(pinned&&!pin&&!['focus','keydown'].includes(event?.type))return;
    pinned=pin; tip.replaceChildren();
    const close=el("button","story-tip-close","×"); close.type="button"; close.setAttribute("aria-label","Dismiss detail"); close.onclick=hide;
    tip.append(close,el("strong",null,title));
    const dl=el("dl");
    for(const [k,v]of entries)dl.append(el("dt",null,k),el("dd",null,String(v)));
    tip.append(dl,el("small",null,"Tap to pin · Escape to dismiss")); tip.hidden=false;
    const r=event?.currentTarget?.getBoundingClientRect?.()||root.getBoundingClientRect();
    const x=event?.clientX||r.left+r.width/2, y=event?.clientY||r.top+15;
    tip.style.left=`${Math.max(8,Math.min(innerWidth-340,x+14))}px`;
    tip.style.top=`${Math.max(8,Math.min(innerHeight-tip.offsetHeight-8,y+14))}px`;
    readout.textContent=`${title} · ${entries.map(([k,v])=>`${k}: ${v}`).join(" · ")}`;
  }
  root.addEventListener("keydown",e=>{if(e.key==="Escape")hide();});
  root.addEventListener("pointerleave",()=>{if(!pinned)tip.hidden=true;});
  return {show,hide,get pinned(){return pinned;},leave:()=>{if(!pinned)tip.hidden=true;}};
}

function bindMark(node,tip,title,entries,raw) {
  node.setAttribute("role","button"); node.setAttribute("aria-label",`${title}. ${entries.map(v=>v.join(": ")).join(". ")}`);
  if(raw!==undefined)node.dataset.value=String(raw);
  node.addEventListener("pointerenter",e=>tip.show(title,entries,e));
  node.addEventListener("focus",e=>tip.show(title,entries,e));
  node.addEventListener("pointerleave",tip.leave);
  node.addEventListener("blur",tip.leave);
  node.addEventListener("click",e=>tip.show(title,entries,e,true));
  node.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();tip.show(title,entries,e,true);}});
}

function keyboardGrid(svg,marks,columns=12) {
  if(!marks.length)return;
  marks.forEach((n,i)=>n.setAttribute("tabindex",i?"-1":"0"));
  marks.forEach((n,i)=>n.addEventListener("keydown",e=>{
    const step={ArrowLeft:-1,ArrowRight:1,ArrowUp:-columns,ArrowDown:columns}[e.key];
    if(step===undefined)return; e.preventDefault();
    const j=Math.max(0,Math.min(marks.length-1,i+step));
    marks.forEach(m=>m.setAttribute("tabindex","-1")); marks[j].setAttribute("tabindex","0"); marks[j].focus();
  }));
}

function chartBox(root,width,height,label) {
  const scroll=el("div","story-chart-scroll");
  const svg=sv("svg",{viewBox:`0 0 ${width} ${height}`,width,height,role:"group","aria-label":label});
  svg.classList.add("story-svg"); scroll.append(svg); root.append(scroll,el("p","story-scroll-hint","On a narrow screen, swipe the chart sideways or use the data table below.")); return svg;
}

function legend(root,colors,min,max,label) {
  const bar=el("div","story-legend"); const strip=el("div","story-gradient");
  bar.exportLegend={colors,min,max,label};
  strip.style.background=`linear-gradient(to right,${colors.filter((_,i)=>i%16===0).join(",")})`;
  const ends=el("div","story-legend-ends"); ends.append(el("span",null,num(min,0)),el("span",null,num((min+max)/2,0)),el("span",null,num(max,0)));
  bar.append(strip,ends,el("p",null,label)); root.append(bar);
}

function seriesLegend(series){
  const key=el('div','story-key story-key-row');
  key.exportSeries=series;
  for(const {name,color,dashed}of series){const item=el('span','story-key-item'),swatch=el('span','story-key-swatch');swatch.style.borderTopColor=color;if(dashed)swatch.style.borderTopStyle='dashed';item.append(swatch,document.createTextNode(name));key.append(item);}
  return key;
}

function rowEntries(r) {
  const e=[["RMSE",`${num(r.rmse,2)} mm`],["MAE",`${num(r.mae,2)} mm`],["Bias",`${num(r.bias,2)} mm`]];
  if(r.gainClimatology!==undefined)e.push(["RMSE reduction vs climatology",`${num(r.gainClimatology,2)}%`]);
  return e;
}

export function sortableTable(rows,label,columns=null) {
  const details=el("details","story-table"); details.append(el("summary",null,"Explore the numbers · sortable table and CSV"));
  const body=el("div","story-table-body"), search=el("input"); search.type="search"; search.placeholder="Filter by season, province or method";
  search.setAttribute("aria-label",`Filter ${label} table`);
  const scroll=el("div","story-table-scroll"), table=el("table"), head=el("thead"), tbody=el("tbody"), tr=el("tr");
  table.setAttribute("aria-label",label); table.append(head,tbody); head.append(tr); scroll.append(table);
  const cols=columns || [...(rows[0]?.region!==undefined?[["region","Province"]]:[]),["season","Season"],["method","Method"],["training","Training"],["rmse","RMSE (mm)"],["mae","MAE (mm)"],["bias","Bias (mm)"]];
  const normalized=rows.map(r=>({...r,method:r.method||(r.variant?method(r.variant):""),training:r.training||(r.variant&&!r.variant.startsWith('raw')?periodLabel(r.variant.replace(/^(cca|pcr|climatology)_/,'')):"—")}));
  let sortKey=null,ascending=true,page=0; const size=25;
  const nav=el("div","story-table-nav"), status=el("span"), prev=el("button",null,"Previous"),next=el("button",null,"Next"),download=el("button",null,"Download filtered CSV");
  for(const b of [prev,next,download])b.type="button";
  nav.append(prev,status,next,download);
  function filtered(){
    const query=search.value.toLowerCase(); let data=normalized.filter(r=>Object.values(r).join(" ").toLowerCase().includes(query));
    if(sortKey)data.sort((a,b)=>((typeof a[sortKey]==="number"?a[sortKey]-b[sortKey]:String(a[sortKey]).localeCompare(String(b[sortKey]))))*(ascending?1:-1));
    return data;
  }
  function render(){
    const data=filtered(); page=Math.min(page,Math.max(0,Math.ceil(data.length/size)-1)); tbody.replaceChildren();
    for(const r of data.slice(page*size,(page+1)*size)){
      const row=el("tr"); for(const [k,,digits=2]of cols){const cell=el("td",null,typeof r[k]==="number"?num(r[k],digits):r[k]); if(typeof r[k]==="number")cell.dataset.value=String(r[k]); row.append(cell);} tbody.append(row);
    }
    status.textContent=data.length?`${page*size+1}–${Math.min((page+1)*size,data.length)} of ${data.length}`:"No matching rows";
    prev.disabled=page===0; next.disabled=(page+1)*size>=data.length;
    [...tr.children].forEach((th,i)=>th.setAttribute("aria-sort",cols[i][0]===sortKey?(ascending?"ascending":"descending"):"none"));
  }
  for(const [key,title]of cols){const th=el("th"),button=el("button",null,title); button.type="button"; button.onclick=()=>{ascending=sortKey===key?!ascending:true;sortKey=key;page=0;render();}; th.append(button);tr.append(th);}
  search.oninput=()=>{page=0;render();};prev.onclick=()=>{page--;render();};next.onclick=()=>{page++;render();};
  download.onclick=()=>{
    const quote=v=>'"'+String(v??"").replaceAll('"','""')+'"';
    const csv=[cols.map(c=>quote(c[1])).join(","),...filtered().map(r=>cols.map(([k])=>quote(r[k])).join(","))].join("\n");
    const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));const a=el("a");a.href=url;a.download=`${label.replaceAll(/[^a-z0-9]/gi,"-")}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
  };
  body.append(search,scroll,nav); details.append(body);details.addEventListener("toggle",()=>{if(details.open)render();});return details;
}

export function nationalHeatmap(data,metric="rmse") {
  const rows=data.national.filter(r=>chosen("1991_2020").includes(r.variant));
  const root=panel("national",`National ${metricName(metric)} · seasons centred on 2023`,"Hover or tap a cell. Use arrow keys after focusing the chart; press Enter to pin details.");
  root.dataset.exportKey=`${metric}-2023-1991-2020`;root.dataset.exportNote="1991–2020 training · full Indonesia · spatial errors on the common country-land support";
  const svg=chartBox(root,850,285,"Four methods across twelve seasons"), tip=tooltip(root), marks=[];
  const min=metric==="bias"?-Math.max(...rows.map(r=>Math.abs(r.bias))):0;
  const max=metric==="bias"?-min:Math.max(...rows.map(r=>r[metric]));
  const colors=data.palettes[metric==="bias"?"BrBG":"YlGnBu"];
  chosen("1991_2020").forEach((v,j)=>{
    svg.append(sv("text",{x:115,y:44+j*47,"text-anchor":"end",class:"story-axis"},method(v)));
    data.seasons.forEach((s,i)=>{
      const r=rows.find(a=>a.variant===v&&a.season===s), val=r[metric], x=125+i*59,y=16+j*47;
      const tile=sv("rect",{x,y,width:57,height:44,rx:2,fill:palette(colors,(val-min)/(max-min)),"data-season":s,"data-method":method(v)});
      bindMark(tile,tip,`${s} · ${method(v)}`,rowEntries(r),val); marks.push(tile);svg.append(tile);
      const label=sv("text",{x:x+28.5,y:y+28,"text-anchor":"middle",class:"story-cell-number",fill:((val-min)/(max-min))>.58?"white":INK},num(val,0)); label.style.pointerEvents="none";svg.append(label);
      if(j===3)svg.append(sv("text",{x:x+28,y:225,"text-anchor":"middle",class:"story-axis"},s));
    });
  });
  keyboardGrid(svg,marks);legend(root,colors,min,max,`${metricName(metric)} (mm) · ${metric==="bias"?"positive means too wet":"lower is better"}`);
  root.append(sortableTable(rows,"National seasonal scores"));return root;
}

export function gainBars(data,period="1991_2020") {
  const rows=data.national.filter(r=>[`cca_${period}`,`pcr_${period}`].includes(r.variant));
  const root=panel("gains",`Calibration versus climatology · ${periodLabel(period)} training`,"Positive bars have lower RMSE than matched climatology. Hover for RMSE and percentage reduction.");
  root.dataset.exportKey=`2023-${period.replaceAll("_","-")}`;root.dataset.exportNote="Seasons centred on 2023 · full Indonesia · positive RMSE reduction improves on matched climatology";
  const svg=chartBox(root,850,350,"Seasonal RMSE reductions for CCA and PCR"),tip=tooltip(root),marks=[];
  const low=Math.min(0,...rows.map(r=>r.gainClimatology))*1.1,high=Math.max(1,...rows.map(r=>r.gainClimatology))*1.15;
  const y=v=>285-(v-low)/(high-low)*255;
  for(let i=0;i<5;i++){const value=low+(high-low)*i/4,yy=y(value);svg.append(sv("line",{x1:60,x2:830,y1:yy,y2:yy,stroke:"#e4ebed"}),sv("text",{x:51,y:yy+4,"text-anchor":"end",class:"story-axis"},num(value,0)));}
  svg.append(sv("line",{x1:60,x2:830,y1:y(0),y2:y(0),stroke:INK}));
  data.seasons.forEach((s,i)=>{
    for(const [j,m]of ["cca","pcr"].entries()){
      const r=rows.find(r=>r.season===s&&r.variant===`${m}_${period}`),x=74+i*63+j*22,val=r.gainClimatology;
      const mark=sv("rect",{x,y:Math.min(y(val),y(0)),width:20,height:Math.max(1,Math.abs(y(val)-y(0))),fill:COLORS[m.toUpperCase()],rx:2,"data-season":s,"data-method":m.toUpperCase()});
      bindMark(mark,tip,`${s} · ${m.toUpperCase()} · ${periodLabel(period)}`,rowEntries(r),val);marks.push(mark);svg.append(mark);
    }
    svg.append(sv("text",{x:95+i*63,y:313,"text-anchor":"middle",class:"story-axis"},s));
  });
  keyboardGrid(svg,marks,2);root.append(seriesLegend(['CCA','PCR'].map(name=>({name,color:COLORS[name]}))),el('p','story-key','RMSE reduction (%)'),sortableTable(rows,"Climatology comparisons"));return root;
}

function lineChart(rows,seasons,title,id,seriesFn,metric="rmse") {
  const root=panel(id,title,"Hover, tap or focus a point to inspect its score. The table keeps all displayed series.");
  root.dataset.exportKey=`${metric}-${title.toLowerCase().replaceAll(/[^a-z0-9]+/g,"-").replace(/-$/,'')}`;
  root.dataset.exportNote=`${metricName(metric)} (mm) · ${id==="sensitivity"?"both training periods": "1991–2020 training"}`;
  const svg=chartBox(root,850,355,title),tip=tooltip(root),marks=[];
  const series=[...new Set(rows.map(seriesFn))],seriesColors=[];
  const min=metric==="bias"?Math.min(0,...rows.map(r=>r[metric])):0,max=Math.max(1,...rows.map(r=>r[metric]))*1.1;
  const x=i=>65+i*68, y=v=>287-(v-min)/(max-min)*250;
  for(let j=0;j<5;j++){const val=min+(max-min)*j/4,yy=y(val);svg.append(sv("line",{x1:65,x2:820,y1:yy,y2:yy,stroke:"#e4ebed"}),sv("text",{x:54,y:yy+4,"text-anchor":"end",class:"story-axis"},num(val,0)));}
  if(metric==='bias')svg.append(sv('line',{x1:65,x2:820,y1:y(0),y2:y(0),stroke:'#52616b','stroke-dasharray':'4 3'}));
  for(const [si,name]of series.entries()) {
    const group=rows.filter(r=>seriesFn(r)===name).sort((a,b)=>seasons.indexOf(a.season)-seasons.indexOf(b.season));
    const color=name.includes("1983")?"#798491":COLORS[method(group[0].variant)]||["#147d92","#c08325"][si%2];
    seriesColors.push({name,color,dashed:name.includes('1983')});
    const path=group.map((r,i)=>`${i?"L":"M"}${x(seasons.indexOf(r.season))},${y(r[metric])}`).join(" ");
    svg.append(sv("path",{d:path,fill:"none",stroke:color,"stroke-width":2,"stroke-dasharray":name.includes("1983")?"5 4":"none"}));
    for(const r of group){const mark=sv("circle",{cx:x(seasons.indexOf(r.season)),cy:y(r[metric]),r:5,fill:color,stroke:"white","stroke-width":1.5,"data-season":r.season,"data-series":name});bindMark(mark,tip,`${r.season} · ${name}`,rowEntries(r),r[metric]);svg.append(mark);marks.push(mark);}
  }
  seasons.forEach((s,i)=>svg.append(sv("text",{x:x(i),y:314,"text-anchor":"middle",class:"story-axis"},s)));
  svg.append(sv("text",{x:65,y:18,class:"story-axis"},`${metricName(metric)} (mm)`));
  keyboardGrid(svg,marks);root.append(seriesLegend(seriesColors),sortableTable(rows,title)); return root;
}

export function sensitivity(data,selected="CCA") {
  const m=selected.toLowerCase(), rows=data.national.filter(r=>r.variant.startsWith(m+"_"));
  return lineChart(rows,data.seasons,`${selected} training-period sensitivity · 2023-centred windows`,"sensitivity",r=>`${selected} · ${periodLabel(r.variant.slice(4))}`);
}

export function nationalContext(data,metric="rmse") {
  const rows=data.context.filter(r=>chosen("1991_2020").includes(r.variant));
  return lineChart(rows,data.seasons,"Original ending-year 2021–2024 pooled context","context",r=>method(r.variant),metric);
}

export function provinceView(data,region="all",period="1991_2020",context=false) {
  const names=data.support.filter(r=>r.isProvince).map(r=>r.name).sort();
  const all=(context?data.regionalContext:data.regional).filter(r=>chosen(period).includes(r.variant)&&names.includes(r.region));
  const time=context?"ending-year 2021–2024 pooled":"seasons centred on 2023";
  if(region!=="all"){
    const rows=all.filter(r=>r.region===region);
    const root=lineChart(rows,data.seasons,`${region} · ${time}`,context?"province-context":"province",r=>method(r.variant));
    const support=data.support.find(s=>s.name===region);
    root.dataset.exportKey=`${region.toLowerCase().replaceAll(/[^a-z0-9]+/g,"-")}-${period.replaceAll("_","-")}-${context?"2021-2024":"2023"}`;
    root.dataset.exportNote=`RMSE (mm) · ${periodLabel(period)} training`;
    root.insertBefore(el("p","story-support-note",`${periodLabel(period)} training · ${support.cells.toLocaleString('en')} pixels at 0.05° · ${num(support.weightPercent)}% of the scored area. Neighbouring pixels share weather; these are not independent samples.`),root.children[2]);return root;
  }
  const root=panel(context?"province-context":"province",`All 38 provinces · ${time}`,`${periodLabel(period)} training. Hover or tap a tile; use arrow keys when focused. Choose one province above for all four methods.`);
  root.dataset.exportKey=`all-provinces-${period.replaceAll("_","-")}-${context?"2021-2024":"2023"}`;root.dataset.exportNote=`${periodLabel(period)} training · province means of the 0.05° pixel errors`;
  const svg=chartBox(root,1140,1080,"CCA and PCR reductions across 38 provinces and twelve seasons"),tip=tooltip(root),marks=[];
  for(const [j,m]of ["cca","pcr"].entries()){
    const left=267+j*435;svg.append(sv("text",{x:left,y:25,class:"story-axis", "font-weight":"bold"},m.toUpperCase()));
    names.forEach((name,k)=>{
      const yy=38+k*25;
      if(j===0)svg.append(sv("text",{x:257,y:yy+17,"text-anchor":"end",class:"story-province-label"},name));
      data.seasons.forEach((s,i)=>{
        const r=all.find(r=>r.region===name&&r.season===s&&r.variant===`${m}_${period}`),value=r.gainClimatology;
        const tile=sv("rect",{x:left+i*35.5,y:yy,width:34.5,height:24,fill:palette(data.palettes.BrBG,(value+100)/200),"data-province":name,"data-season":s,"data-method":m.toUpperCase()});
        const support=data.support.find(a=>a.name===name);
        bindMark(tile,tip,`${name} · ${s} · ${m.toUpperCase()}`,[...rowEntries(r),["Pixels",support.cells.toLocaleString("en")]],value);marks.push(tile);svg.append(tile);
      });
    });
    data.seasons.forEach((s,i)=>svg.append(sv("text",{x:left+i*35.5+16,y:1008,"text-anchor":"middle",class:"story-axis",transform:`rotate(-40 ${left+i*35.5+16} 1008)`},s)));
  }
  keyboardGrid(svg,marks);legend(root,data.palettes.BrBG,-100,100,"RMSE reduction vs matched climatology (%) · brown worsens, green helps; values below −100% saturate in colour only");
  root.append(sortableTable(all,context?"Province pooled scores":"Province 2023 scores"));return root;
}

const mapCache=new WeakMap();
// The map manifest (grid, field order, province names), the pixel list, each pixel's province and the boundaries
async function mapAssets(files) {
  if(!mapCache.has(files))mapCache.set(files,(async()=>{
    const urls={};for(const [key,url] of Object.entries(files))urls[key]=await url;
    const entries=await Promise.all(Object.entries(urls).map(async([key,url])=>{
      const response=await fetch(url);if(!response.ok)throw new Error(`Cannot load local ${key} (${response.status})`);
      return [key,await response.json()];
    }));
    const loaded=Object.fromEntries(entries),paths={},base=new URL(".",new URL(urls.fields,location.href));
    const binary=async name=>{const r=await fetch(new URL(name,base));if(!r.ok)throw new Error(`Cannot load local ${name} (${r.status})`);return r.arrayBuffer();};
    const f=loaded.fields;
    f.pixels=new Int32Array(await binary("pixels.bin"));f.province=new Uint8Array(await binary("provinces.bin"));
    f.lookup=new Int32Array(f.grid.nx*f.grid.ny).fill(-1);f.pixels.forEach((p,i)=>{f.lookup[p]=i;});
    const seasons=new Map();
    // One season's maps: unsigned 16-bit whole millimetres, observed first, then the forecasts in f.order
    f.season=name=>{
      if(!seasons.has(name))seasons.set(name,(async()=>{
        const response=await fetch(new URL(`fields/${name}.bin.gz`,base));if(!response.ok)throw new Error(`Cannot load local ${name} maps (${response.status})`);
        let buffer=await response.arrayBuffer();const head=new Uint8Array(buffer,0,2);
        if(head[0]===0x1f&&head[1]===0x8b)buffer=await new Response(new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
        const n=f.grid.pixels,out={};f.order.forEach((key,k)=>{out[key]=new Uint16Array(buffer,k*n*2,n);});return out;
      })());
      return seasons.get(name);
    };
    // One season's forecast products: unsigned 16-bit values in f.productOrder (mm, tenths of a percent, category)
    const productSets=new Map();
    f.products=name=>{
      if(!productSets.has(name))productSets.set(name,(async()=>{
        const response=await fetch(new URL(`fields/${name}-products.bin.gz`,base));if(!response.ok)throw new Error(`Cannot load local ${name} forecast products (${response.status})`);
        let buffer=await response.arrayBuffer();const head=new Uint8Array(buffer,0,2);
        if(head[0]===0x1f&&head[1]===0x8b)buffer=await new Response(new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
        const n=f.grid.pixels,out={};f.productOrder.forEach((key,k)=>{out[key]=new Uint16Array(buffer,k*n*2,n);});return out;
      })());
      return productSets.get(name);
    };
    function appendGeometry(path,g){
      if(g.type==="GeometryCollection"){g.geometries.forEach(v=>appendGeometry(path,v));return;}
      const polygons=g.type==="Polygon"?[g.coordinates]:g.type==="MultiPolygon"?g.coordinates:[];
      for(const polygon of polygons)for(const ring of polygon){if(!ring.length)continue;path.moveTo(...ring[0]);for(let i=1;i<ring.length;i++)path.lineTo(...ring[i]);path.closePath();}
    }
    for(const key of ["indonesia","provinces","neighbours"]){const path=new Path2D();for(const f of loaded[key].features)appendGeometry(path,f.geometry);paths[key]=path;}
    loaded.paths=paths;return loaded;
  })());return mapCache.get(files);
}

// Linked zoom for the maps of one view: every map shares a zoom factor and a centre in longitude/latitude
function mapGroup() {
  const state = {k: 1, cx: null, cy: null}, maps = [], bar = el("div", "story-map-tools");
  const button = (label, title, run) => {const b = el("button", null, label); b.type = "button"; b.title = title; b.setAttribute("aria-label", title); b.onclick = run; bar.append(b); return b;};
  const zoomIn = button("+", "Zoom in", () => zoom(1.6)), zoomOut = button("−", "Zoom out", () => zoom(1 / 1.6));
  const resetView = () => {state.k = 1; state.cx = state.cy = null; apply();};
  const reset = button("Reset view", "Back to the full map", resetView);
  bar.append(el("span", "story-map-tools-note", "Zoom applies to every map in this view. Drag to move when zoomed · double-click or Ctrl + scroll to zoom."));
  let queued = false;
  // Buttons, keys and double-clicks redraw at once; a drag sends many moves, so those wait for the next frame
  function apply(later = false) {
    state.k = Math.max(1, Math.min(32, state.k)); if (state.k < 1.001) {state.k = 1; state.cx = state.cy = null;}   // 1.6 * 1.6 / 1.6 / 1.6 is not exactly 1
    zoomOut.disabled = reset.disabled = state.k === 1; zoomIn.disabled = state.k === 32;
    if (!later) {for (const m of maps) m.redraw(); return;}
    if (queued) return; queued = true;
    (document.hidden ? setTimeout : requestAnimationFrame)(() => {queued = false; for (const m of maps) m.redraw();});
  }
  function zoom(f, lon, lat, from) {
    const k = Math.max(1, Math.min(32, state.k * f)), ratio = k / state.k; if (ratio === 1) return;
    const [x0, x1, y0, y1] = (from || maps[0]).window(), cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    state.cx = lon === undefined ? cx : lon + (cx - lon) / ratio; state.cy = lat === undefined ? cy : lat + (cy - lat) / ratio;
    state.k = k; apply();
  }
  function pan(dLon, dLat, from) {
    const [x0, x1, y0, y1] = from.window(); state.cx = (x0 + x1) / 2 + dLon; state.cy = (y0 + y1) / 2 + dLat;
    const [a0, a1, b0, b1] = from.window(); state.cx = (a0 + a1) / 2; state.cy = (b0 + b1) / 2; apply(true);
  }
  zoomOut.disabled = reset.disabled = true;
  return {state, maps, bar, zoom, pan, reset: resetView};
}
// The part of a full extent [west, east, south, north] a map shows for the group's zoom and centre
function groupWindow(group, full) {
  const k = group.state.k, w = (full[1] - full[0]) / k, h = (full[3] - full[2]) / k;
  const cx = Math.max(full[0] + w / 2, Math.min(full[1] - w / 2, group.state.cx ?? (full[0] + full[1]) / 2));
  const cy = Math.max(full[2] + h / 2, Math.min(full[3] - h / 2, group.state.cy ?? (full[2] + full[3]) / 2));
  return [cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2];
}
const tickStep = span => [20, 10, 5, 2, 1, .5, .2, .1].find(s => span / s >= 3) || .1;
// Drag, double-click, Ctrl + scroll and + / - / 0 on one map; `at(event)` gives [longitude, latitude, inside the map]
function zoomGestures(canvas, group, self, at) {
  let last = null;
  canvas.addEventListener("pointerdown", e => {delete canvas.dataset.dragged; if (group.state.k > 1 && e.button === 0) {last = {clientX: e.clientX, clientY: e.clientY}; try {canvas.setPointerCapture(e.pointerId);} catch {}}});
  canvas.addEventListener("pointermove", e => {
    if (!last) return;
    if (Math.abs(e.clientX - last.clientX) + Math.abs(e.clientY - last.clientY) < 4 && !canvas.dataset.dragged) return;
    const a = at(last), b = at(e); canvas.dataset.dragged = "1"; last = {clientX: e.clientX, clientY: e.clientY};
    group.pan(a[0] - b[0], a[1] - b[1], self);
  });
  const release = e => {if (last) {last = null; try {canvas.releasePointerCapture(e.pointerId);} catch {}}};
  canvas.addEventListener("pointerup", release); canvas.addEventListener("pointercancel", release);
  canvas.addEventListener("dblclick", e => {const [lon, lat, inside] = at(e); if (inside) {e.preventDefault(); group.zoom(2, lon, lat, self);}});
  canvas.addEventListener("wheel", e => {if (!e.ctrlKey && !e.metaKey) return; e.preventDefault(); const [lon, lat, inside] = at(e); if (inside) group.zoom(e.deltaY < 0 ? 1.25 : .8, lon, lat, self);}, {passive: false});
  canvas.addEventListener("keydown", e => {
    if (e.key === "+" || e.key === "=") {e.preventDefault(); group.zoom(1.6, undefined, undefined, self);}
    else if (e.key === "-" || e.key === "_") {e.preventDefault(); group.zoom(1 / 1.6, undefined, undefined, self);}
    else if (e.key === "0") {e.preventDefault(); group.reset();}
  });
}

const CATEGORY_NAMES=["Below normal","Near normal","Above normal"];
const PRODUCT_TITLES={category:"Most likely category and its probability",anomaly:"Anomaly: difference from normal (mm)",percent:"Percent of normal",total:"Rainfall total (mm)"};
const mix=(a,b,t)=>"#"+[0,1,2].map(k=>Math.round(parseInt(a.slice(1+2*k,3+2*k),16)*(1-t)+parseInt(b.slice(1+2*k,3+2*k),16)*t).toString(16).padStart(2,"0")).join("");
// Colour of a tercile category at a probability in percent: brown for below, grey for near, green for above
function categoryColor(colors,k,probability){
  const t=Math.max(0,Math.min(1,(probability-35)/(k===1?20:50)));
  return k===1?mix("#d9d9d9","#6b6b6b",t):palette(colors,k===0?.36-.34*t:.64+.34*t);
}
function mapPanel(data,files,season,period,errorMode=false,product=null) {
  const seasons=season==="all"?data.seasons:[season];
  const root=panel(product?"forecast-products":errorMode?"error-maps":"rainfall",product?`${season} · ${product.method.toUpperCase()} forecast and what was observed · ${PRODUCT_TITLES[product.view]}`:errorMode?"Where calibration helps or worsens the local forecast":"Compare rainfall on the same map scale",
    "Hover or tap a pixel. Focus a map and use ← / → to step through scored pixels. Grey land is outside the study area.");
  root.dataset.ready="false"; root.dataset.state="waiting";
  root.querySelector('.story-export button').disabled=true;
  root.dataset.exportKey=`${season.toLowerCase()}-${period.replaceAll("_","-")}-2023${product?`-${product.method}-${product.view}`:""}`;root.dataset.exportNote=`${season==="all"?"All twelve seasons":season} · seasons centred on 2023 · ${periodLabel(period)} training · native 0.05° grid`;
  const status=el("p","story-map-status","Maps load when this section comes into view. All map files are local to the book.");root.append(status);
  let observer,resize,disposed=false,active=-1;
  root.dispose=()=>{disposed=true;observer?.disconnect();resize?.disconnect();};
  async function start(){
    observer?.disconnect();root.dataset.state="loading";status.textContent="Loading local map fields and boundaries…";
    try{
      const assets=await mapAssets(files);if(disposed)return;
      const f=assets.fields,{west,north,step,nx,ny,pixels:n}=f.grid,grid=el("div","story-map-grid"),cards=[];
      const values=Object.fromEntries(await Promise.all(seasons.map(async s=>[s,await f.season(s)])));if(disposed)return;
      const prod=product?Object.fromEntries(await Promise.all(seasons.map(async s=>[s,await f.products(s)]))):null;if(disposed)return;
      const probabilities=(q,m,i)=>["below","near","above"].map(c=>q[`${m}_${c}`][i]/10);
      const likely=p=>p[2]>p[0]?(p[2]>p[1]?2:1):(p[0]>=p[1]?0:1);
      // The colour of one pixel of a forecast-products map
      function productColor(card,i){
        const v=values[card.season],q=prod[card.season],total=v[card.variant][i],normal=q.normal[i],brbg=data.palettes.BrBG;
        if(product.view==="total")return palette(data.palettes.YlGnBu,total/f.rainLimits[card.season][period]);
        if(product.view==="anomaly"){const limit=f.anomalyLimits[card.season];return palette(brbg,(total-normal+limit)/(2*limit));}
        if(product.view==="percent")return palette(brbg,normal>0?(100*total/normal-40)/120:.5);
        if(card.variant==="observed")return categoryColor(brbg,q.observed_category[i],65);
        const p=probabilities(q,product.method,i),k=likely(p);return categoryColor(brbg,k,p[k]);
      }
      const lonOf=i=>west+(f.pixels[i]%nx+.5)*step,latOf=i=>north-(Math.floor(f.pixels[i]/nx)+.5)*step;
      const FULL=[west,west+nx*step,north-ny*step,north],aspect=(FULL[3]-FULL[2])/(FULL[1]-FULL[0]);
      const tip=tooltip(root);let request=0;
      const group=mapGroup(),view=()=>groupWindow(group,FULL);
      const shownValue=(card,i)=>{const v=values[card.season];return errorMode?Math.abs(v[`climatology_${period}`][i]-v.observed[i])-Math.abs(v[card.variant][i]-v.observed[i]):v[card.variant][i];};
      function inspect(index,event,pin=false){
        if(index<0||index>=n)return;
        if(tip.pinned&&!pin&&event?.type==='pointermove')return;
        active=index;const card=event?.currentTarget?cards.find(c=>c.canvas===event.currentTarget):cards[0];
        const selectedSeason=card?.season||seasons[0],v=values[selectedSeason];
        const entries=[["Province",f.provinces[f.province[index]]]];
        if(product){
          const q=prod[selectedSeason],normal=q.normal[index],share=x=>normal>0?`${num(100*x/normal,0)}% of normal`:"normal is 0 mm";
          entries.push(["Normal, 1991–2020 mean",`${num(normal,0)} mm`],["Tercile boundaries",`${num(q.tercile_lower[index],0)} and ${num(q.tercile_upper[index],0)} mm`],
            ["Observed",`${num(v.observed[index],0)} mm · ${num(v.observed[index]-normal,0)} mm · ${share(v.observed[index])} · ${CATEGORY_NAMES[q.observed_category[index]].toLowerCase()}`]);
          for(const m of ["cca","pcr"]){const total=v[`${m}_${period}`][index],p=probabilities(q,m,index);
            entries.push([`${m.toUpperCase()} forecast`,`${num(total,0)} mm · ${num(total-normal,0)} mm · ${share(total)}`],
              [`${m.toUpperCase()} below / near / above`,`${num(p[0],0)}% / ${num(p[1],0)}% / ${num(p[2],0)}% · most likely ${CATEGORY_NAMES[likely(p)].toLowerCase()}`]);}
        }else if(errorMode){
          const base=Math.abs(v[`climatology_${period}`][index]-v.observed[index]);
          entries.push(["Climatology absolute error",`${num(base,0)} mm`]);
          for(const m of ["cca","pcr"]){const ae=Math.abs(v[`${m}_${period}`][index]-v.observed[index]);entries.push([`${m.toUpperCase()} absolute error`,`${num(ae,0)} mm`],[`${m.toUpperCase()} reduction`,`${num(base-ae,0)} mm`]);}
        }else{
          entries.push(["Observed",`${num(v.observed[index],0)} mm`]);
          for(const key of chosen(period)){const value=v[key][index];entries.push([method(key),`${num(value,0)} mm (error ${num(value-v.observed[index],0)} mm)`]);}
        }
        tip.show(`${selectedSeason} · ${num(lonOf(index),3)}°E, ${num(latOf(index),3)}°N`,entries,event,pin);
        if(product&&pin)drawCurves(index,selectedSeason);
        if(!request)request=requestAnimationFrame(()=>{request=0;cards.forEach(c=>paint(c));});
      }
      // The flexible forecast at one pixel, under the maps: PyCPT's construct_flex_fcst conventions
      const curves=el("div","story-flex-holder");
      function drawCurves(index,s0=seasons[0]){
        if(!product)return;
        const v=values[s0],q=prod[s0],unit=f.flexible.scaleUnit,nu=f.flexible.degreesOfFreedom,m=product.method;
        const mu=v[`${m}_${period}`][index],sc=q[`${m}_scale`][index]*unit,cmu=q.normal[index],cs=q.climatology_scale[index]*unit,ob=v.observed[index],lo=q.tercile_lower[index],hi=q.tercile_upper[index];
        const lat=latOf(index),place=`${num(lonOf(index),3)}°E, ${lat<0?num(-lat,3)+"°S":num(lat,3)+"°N"} · ${f.provinces[f.province[index]]}`;
        const chance=x=>num(100*tSf(x,nu,mu,sc),0),usual=x=>num(100*normSf(x,cmu,cs),0);
        curves.replaceChildren(exceedanceCurves({heading:`${s0} · ${m.toUpperCase()} flexible forecast at ${place}`,
          note:`Forecast centre ${num(mu,0)} mm, 1991–2020 mean ${num(cmu,0)} mm, observed ${num(ob,0)} mm. Chance of more than the mean: forecast ${chance(cmu)}%, climatology ${usual(cmu)}%. Chance of more than the upper tercile boundary (${num(hi,0)} mm): forecast ${chance(hi)}%, climatology ${usual(hi)}%. Chance of more than what was observed: forecast ${chance(ob)}%.`,
          mu,s:sc,nu,cmu,cs,forecastLabel:`${m.toUpperCase()} forecast`,marks:[[lo,"lower tercile",MUTED,"4 3"],[hi,"upper tercile",MUTED,"2 3"],[ob,"observed",INK]]}));
      }
      function paint(card){
        const ctx=card.canvas.getContext("2d");ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,card.canvas.width,card.canvas.height);ctx.drawImage(card.base,0,0);
        if(active>=0){const w=view(),ratio=card.canvas.width/(w[1]-w[0]),size=Math.max(step*ratio,6);ctx.strokeStyle="#d42f47";ctx.lineWidth=Math.max(2,devicePixelRatio||1);
          ctx.strokeRect((lonOf(active)-w[0])*ratio-size/2,(w[3]-latOf(active))*ratio-size/2,size,size);}
      }
      // The field as an image with one image pixel per grid pixel, made once per map
      function raster(card){
        if(card.raster)return card.raster;
        const image=new ImageData(nx,ny),colors=data.palettes[errorMode?"BrBG":"YlGnBu"],limit=f.rainLimits[card.season][period];
        for(let i=0;i<n;i++){
          const value=product?0:shownValue(card,i),t=errorMode?(value+300)/600:value/limit,c=product?productColor(card,i):palette(colors,t);
          image.data.set([parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16),255],f.pixels[i]*4);
        }
        card.raster=el("canvas");card.raster.width=nx;card.raster.height=ny;card.raster.getContext("2d").putImageData(image,0,0);return card.raster;
      }
      function renderMap(card,canvas,width,dpr){
        const pw=Math.round(width*dpr),ph=Math.round(width*aspect*dpr);canvas.width=pw;canvas.height=ph;
        const ctx=canvas.getContext("2d");ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle="#f1f5f7";ctx.fillRect(0,0,pw,ph);const w=view(),scale=pw/(w[1]-w[0]);
        ctx.setTransform(scale,0,0,-scale,-w[0]*scale,w[3]*scale);
        ctx.fillStyle="#d6d8da";ctx.strokeStyle="#9ca3a8";ctx.lineWidth=.4*dpr/scale;ctx.fill(assets.paths.neighbours);ctx.stroke(assets.paths.neighbours);
        ctx.setTransform(1,0,0,1,0,0);ctx.imageSmoothingEnabled=false;
        ctx.drawImage(raster(card),(w[0]-west)/step,(north-w[3])/step,(w[1]-w[0])/step,(w[3]-w[2])/step,0,0,pw,ph);
        ctx.setTransform(scale,0,0,-scale,-w[0]*scale,w[3]*scale);
        for(const [key,color,lw]of [["provinces","#52616b",.35],["indonesia","#263943",.8]]){ctx.strokeStyle=color;ctx.lineWidth=lw*dpr/scale;ctx.stroke(assets.paths[key]);}
      }
      function draw(card){
        const width=Math.max(230,Math.floor(card.canvas.getBoundingClientRect().width)),dpr=Math.min(devicePixelRatio||1,2);
        const w=view(),key=w.map(v=>v.toFixed(4)).join();
        if(card.base.width===Math.round(width*dpr)&&card.base.height===Math.round(width*aspect*dpr)&&card.viewKey===key)return;
        card.viewKey=key;renderMap(card,card.base,width,dpr);card.canvas.width=card.base.width;card.canvas.height=card.base.height;paint(card);
        const deg=(v,p,q)=>`${Math.abs(v).toFixed(group.state.k>1?1:0)}°${v<0?q:p}`;
        card.coords.textContent=`${deg(w[0],"E","W")}                         ${deg((w[0]+w[1])/2,"E","W")}                         ${deg(w[1],"E","W")} · ${deg(w[2],"N","S")}–${deg(w[3],"N","S")}`;
        card.canvas.style.touchAction=group.state.k>1?"none":"pan-y";card.canvas.style.cursor=group.state.k>1?"grab":"crosshair";
      }
      for(const s of seasons){
        const date=data.calendar.find(c=>c.season===s);
        const variants=product?[`${product.method}_${period}`,"observed"]:errorMode?[`cca_${period}`,`pcr_${period}`]:["observed",...chosen(period)];
        if(!errorMode){const dates=el("p","story-map-dates",`${s}: ${date.start} to ${date.end} · issued ${date.issue} · ${periodLabel(period)} training · source ending-year ${date.sourceYear}`);root.insertBefore(dates,status);}
        for(const variant of variants){
          const title=variant==="observed"?"Observed · CHIRPS v3.0":method(variant),box=el("div","story-map-card"),canvas=el("canvas"),base=el("canvas");
          box.append(el("h4",null,errorMode?`${s} · ${title}`:title));canvas.setAttribute("tabindex","0");canvas.setAttribute("role","img");canvas.setAttribute("aria-label",`${s} ${title} map. Left and right arrows inspect scored pixels; Enter pins details; + and - zoom.`);
          canvas.style.aspectRatio=`${FULL[1]-FULL[0]}/${FULL[3]-FULL[2]}`;
          canvas.dataset.mapVariant=variant;canvas.dataset.season=s;const coords=el("p","story-map-coords","");box.append(canvas,coords);grid.append(box);
          const card={canvas,base,variant,season:s,coords};cards.push(card);
          const at=e=>{const r=canvas.getBoundingClientRect(),w=view(),fx=(e.clientX-r.left)/r.width,fy=(e.clientY-r.top)/r.height;return [w[0]+(w[1]-w[0])*fx,w[3]-(w[3]-w[2])*fy,fx>=0&&fx<=1&&fy>=0&&fy<=1];};
          const self={redraw:()=>draw(card),window:view};group.maps.push(self);zoomGestures(canvas,group,self,at);
          function hit(e,pin=false){if(canvas.dataset.dragged){if(pin)delete canvas.dataset.dragged;return;}const [lon,lat]=at(e);
            const col=Math.floor((lon-west)/step),row=Math.floor((north-lat)/step),index=col>=0&&col<nx&&row>=0&&row<ny?f.lookup[row*nx+col]:-1;
            if(index>=0)inspect(index,e,pin);else if(!pin)tip.leave();}
          canvas.addEventListener("pointermove",e=>hit(e));canvas.addEventListener("pointerleave",tip.leave);canvas.addEventListener("click",e=>hit(e,true));
          canvas.addEventListener("keydown",e=>{if(["ArrowLeft","ArrowRight","Enter"," "].includes(e.key)){e.preventDefault();const delta=e.key==="ArrowLeft"?-1:e.key==="ArrowRight"?1:0;inspect(Math.max(0,Math.min(n-1,(active<0?0:active)+delta)),e,delta===0);}});
        }
      }
      status.replaceWith(grid);grid.before(group.bar);
      root.exportGraphic=async()=>{
        const width=1200,gap=24,cardWidth=(width-gap)/2,mapHeight=cardWidth*aspect,rowHeight=Math.ceil(mapHeight)+68,height=Math.ceil(cards.length/2)*rowHeight;
        const canvas=el("canvas");canvas.width=width*2;canvas.height=height*2;const ctx=canvas.getContext("2d");ctx.scale(2,2);ctx.fillStyle="white";ctx.fillRect(0,0,width,height);ctx.textBaseline="top";
        for(const [i,card]of cards.entries()){
          const x=(i%2)*(cardWidth+gap),y=Math.floor(i/2)*rowHeight,map=el("canvas");renderMap(card,map,cardWidth,2);
          ctx.fillStyle=INK;ctx.font="600 18px Arial, sans-serif";ctx.fillText(`${card.season} · ${card.variant==="observed"?"Observed · CHIRPS v3.0":method(card.variant)}`,x,y);
          ctx.drawImage(map,x,y+28,cardWidth,mapHeight);ctx.font="12px Arial, sans-serif";ctx.fillStyle=MUTED;ctx.fillText(`${card.coords.textContent.replace(/\s+/g," ")} · grey land outside study area`,x,y+mapHeight+36);
          // Yield between maps so large atlases keep the page and download UI responsive.
          await new Promise(resolve=>setTimeout(resolve,0));
        }return {image:canvas,width,height};
      };
      if(product){
        const s0=seasons[0],brbg=data.palettes.BrBG;
        if(product.view==="total")legend(root,data.palettes.YlGnBu,0,f.rainLimits[s0][period],"Seasonal rainfall (mm). Both maps share one scale; the highest 1% is colour-saturated only.");
        else if(product.view==="anomaly")legend(root,brbg,-f.anomalyLimits[s0],f.anomalyLimits[s0],"Total minus the 1991–2020 normal (mm): brown is drier than normal, green wetter. The scale stops at the 99th percentile; details keep full values.");
        else if(product.view==="percent")legend(root,brbg,40,160,"Total as a percentage of the 1991–2020 normal. Colours saturate below 40% and above 160%; details keep full values.");
        else{
          const bar=el("div","story-legend story-category-legend");
          for(const [k,name] of CATEGORY_NAMES.entries()){const item=el("div","story-category-item"),strip=el("div","story-gradient"),top=k===1?55:85;
            strip.style.background=`linear-gradient(to right,${[35,45,55,65,75,85].filter(x=>x<=top).map(x=>categoryColor(brbg,k,x)).join(",")})`;
            const ends=el("div","story-legend-ends");ends.append(el("span",null,"35%"),el("span",null,name),el("span",null,`${top}%+`));item.append(strip,ends);bar.append(item);}
          bar.append(el("p",null,"Forecast map: the most likely tercile category, darker where its probability is higher. Observed map: the category that occurred. Probabilities are CPT's own and are not verified here."));root.append(bar);
        }
      }
      const max=errorMode?300:f.rainLimits[seasons[0]][period];if(!product)legend(root,data.palettes[errorMode?"BrBG":"YlGnBu"],errorMode?-300:0,max,errorMode?"Absolute-error reduction vs climatology (mm): positive helps. Colours saturate beyond ±300 mm; details retain full values.":"Seasonal rainfall (mm). All five maps share the selected season's scale; the highest 1% is colour-saturated only.");
      if(product){
        root.append(el("p","story-hint","Click or tap a pixel, or focus a map and press Enter, to draw its flexible forecast here: the full distribution of the forecast against climatology."),curves);
        let start=0,best=Infinity;for(let i=0;i<n;i++){const d=(lonOf(i)-106.85)**2+(latOf(i)+6.2)**2;if(d<best){best=d;start=i;}}      // start near Jakarta
        drawCurves(start);
      }
      if(!errorMode&&!product){
        const v=values[seasons[0]],dates=data.calendar.find(c=>c.season===seasons[0]);
        // The table is built only when it is opened: one row per pixel
        const holder=el("details","story-table"),summary=el("summary",null,`${seasons[0]} pixel values (${n.toLocaleString("en")} rows)`);holder.append(summary);root.append(holder);
        holder.addEventListener("toggle",()=>{if(!holder.open||holder.dataset.built)return;holder.dataset.built="1";
          const rows=Array.from({length:n},(_,i)=>({season:seasons[0],training:periodLabel(period),targetStart:dates.start,targetEnd:dates.end,longitude:lonOf(i),latitude:latOf(i),region:f.provinces[f.province[i]],observed:v.observed[i],raw:v.raw_cfsv2[i],climatology:v[`climatology_${period}`][i],cca:v[`cca_${period}`][i],pcr:v[`pcr_${period}`][i]}));
          const table=sortableTable(rows,`${seasons[0]} pixel values`,[["season","Season"],["training","Training"],["targetStart","Target starts"],["targetEnd","Target ends"],["longitude","Longitude",3],["latitude","Latitude",3],["region","Province"],["observed","Observed (mm)"],["raw","Raw (mm)"],["climatology","Climatology (mm)"],["cca","CCA (mm)"],["pcr","PCR (mm)"]]);
          table.open=true;holder.replaceWith(table);});
      }
      resize=new ResizeObserver(()=>cards.forEach(draw));resize.observe(root);cards.forEach(draw);root.dataset.ready="true";root.dataset.state="ready";root.querySelector('.story-export button').disabled=false;
    }catch(error){status.textContent=`Map could not load: ${error.message}. Use the static figure or NetCDF links below.`;root.dataset.state="error";}
  }
  if(typeof IntersectionObserver!=="undefined"){observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))start();},{rootMargin:"250px"});observer.observe(root);}else queueMicrotask(start);
  return root;
}

export function rainfallMaps(data,files,season="OND",period="1991_2020"){return mapPanel(data,files,season,period,false);}
export function errorMaps(data,files,season="JJA",period="1991_2020"){return mapPanel(data,files,season,period,true);}
// The forecast as a user reads it, beside what was observed: view is "category", "anomaly", "percent" or "total"
export function forecastMaps(data,files,season="OND",method="cca",view="category"){return mapPanel(data,files,season,"1991_2020",false,{method,view});}
