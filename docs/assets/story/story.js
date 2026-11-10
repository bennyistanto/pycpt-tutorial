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
    root.insertBefore(el("p","story-support-note",`${periodLabel(period)} training · ${support.cells} contributing coarse cells · largest cell ${num(support.largestCellPercent)}% of province weight. Shared coarse-cell errors; these are not independent samples.`),root.children[2]);return root;
  }
  const root=panel(context?"province-context":"province",`All 38 provinces · ${time}`,`${periodLabel(period)} training. Hover or tap a tile; use arrow keys when focused. Choose one province above for all four methods.`);
  root.dataset.exportKey=`all-provinces-${period.replaceAll("_","-")}-${context?"2021-2024":"2023"}`;root.dataset.exportNote=`${periodLabel(period)} training · shared coarse-cell errors partitioned by native province weights`;
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
        bindMark(tile,tip,`${name} · ${s} · ${m.toUpperCase()}`,[...rowEntries(r),["Coarse cells",support.cells],["Largest cell share",`${num(support.largestCellPercent)}%`]],value);marks.push(tile);svg.append(tile);
      });
    });
    data.seasons.forEach((s,i)=>svg.append(sv("text",{x:left+i*35.5+16,y:1008,"text-anchor":"middle",class:"story-axis",transform:`rotate(-40 ${left+i*35.5+16} 1008)`},s)));
  }
  keyboardGrid(svg,marks);legend(root,data.palettes.BrBG,-100,100,"RMSE reduction vs matched climatology (%) · brown worsens, green helps; values below −100% saturate in colour only");
  root.append(sortableTable(all,context?"Province pooled scores":"Province 2023 scores"));return root;
}

const mapCache=new WeakMap();
async function mapAssets(files) {
  if(!mapCache.has(files))mapCache.set(files,(async()=>{
    const entries=await Promise.all(Object.entries(files).map(async([key,url])=>{
      const response=await fetch(await url);if(!response.ok)throw new Error(`Cannot load local ${key} (${response.status})`);
      return [key,await response.json()];
    }));
    const loaded=Object.fromEntries(entries),paths={};
    function appendGeometry(path,g){
      if(g.type==="GeometryCollection"){g.geometries.forEach(v=>appendGeometry(path,v));return;}
      const polygons=g.type==="Polygon"?[g.coordinates]:g.type==="MultiPolygon"?g.coordinates:[];
      for(const polygon of polygons)for(const ring of polygon){if(!ring.length)continue;path.moveTo(...ring[0]);for(let i=1;i<ring.length;i++)path.lineTo(...ring[i]);path.closePath();}
    }
    for(const key of ["indonesia","provinces","neighbours"]){const path=new Path2D();for(const f of loaded[key].features)appendGeometry(path,f.geometry);paths[key]=path;}
    loaded.paths=paths;return loaded;
  })());return mapCache.get(files);
}

function mapPanel(data,files,season,period,errorMode=false) {
  const seasons=season==="all"?data.seasons:[season];
  const root=panel(errorMode?"error-maps":"rainfall",errorMode?"Where calibration helps or worsens the local forecast":"Compare rainfall on the same map scale",
    "Hover or tap a country-land cell. Focus a map and use ← / → to step through scored cells. Grey land is outside the study area.");
  root.dataset.ready="false"; root.dataset.state="waiting";
  root.querySelector('.story-export button').disabled=true;
  root.dataset.exportKey=`${season.toLowerCase()}-${period.replaceAll("_","-")}-2023`;root.dataset.exportNote=`${season==="all"?"All twelve seasons":season} · seasons centred on 2023 · ${periodLabel(period)} training · 0.25° grid`;
  const status=el("p","story-map-status","Maps load when this section comes into view. All map files are local to the book.");root.append(status);
  let observer,resize,disposed=false,active=-1;
  root.dispose=()=>{disposed=true;observer?.disconnect();resize?.disconnect();};
  async function start(){
    observer?.disconnect();root.dataset.state="loading";status.textContent="Loading local map fields and boundaries…";
    try{
      const assets=await mapAssets(files);if(disposed)return;
      const f=assets.fields,grid=el("div","story-map-grid"),cards=[];
      const lookup=new Int32Array(76*192).fill(-1);f.cells.forEach((c,i)=>lookup[c.row*192+c.col]=i);
      const tip=tooltip(root);let request=0;
      function inspect(index,event,pin=false){
        if(index<0||index>=f.cells.length)return;
        if(tip.pinned&&!pin&&event?.type==='pointermove')return;
        active=index;const cell=f.cells[index],card=event?.currentTarget?cards.find(c=>c.canvas===event.currentTarget):cards[0];
        const selectedSeason=card?.season||seasons[0],values=f.fields[selectedSeason];
        const entries=[["Native weight shares",cell.shares.map(([n,w])=>`${n} ${num(100*w,1)}%`).join("; ")]];
        if(errorMode){
          const base=Math.abs(values[`climatology_${period}`][index]-values.observed[index]);
          entries.push(["Climatology absolute error",`${num(base,2)} mm`]);
          for(const m of ["cca","pcr"]){const ae=Math.abs(values[`${m}_${period}`][index]-values.observed[index]);entries.push([`${m.toUpperCase()} absolute error`,`${num(ae,2)} mm`],[`${m.toUpperCase()} reduction`,`${num(base-ae,2)} mm`]);}
        }else{
          entries.push(["Observed",`${num(values.observed[index],2)} mm`]);
          for(const v of chosen(period)){const value=values[v][index];entries.push([method(v),`${num(value,2)} mm (error ${num(value-values.observed[index],2)} mm)`]);}
        }
        tip.show(`${selectedSeason} · ${num(cell.lon,3)}°E, ${num(cell.lat,3)}°N`,entries,event,pin);
        if(!request)request=requestAnimationFrame(()=>{request=0;cards.forEach(c=>paint(c));});
      }
      function paint(card){
        const ctx=card.canvas.getContext("2d");ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,card.canvas.width,card.canvas.height);ctx.drawImage(card.base,0,0);
        if(active>=0){const cell=f.cells[active],ratio=card.canvas.width/48;ctx.strokeStyle="#d42f47";ctx.lineWidth=Math.max(2,devicePixelRatio||1);ctx.strokeRect((cell.lon-.125-94)*ratio,(7-cell.lat-.125)*ratio,.25*ratio,.25*ratio);}
      }
      function renderMap(card,canvas,width,dpr){
        const pw=Math.round(width*dpr),ph=Math.round(width*19/48*dpr);canvas.width=pw;canvas.height=ph;
        const ctx=canvas.getContext("2d");ctx.fillStyle="#f1f5f7";ctx.fillRect(0,0,pw,ph);const scale=pw/48;
        ctx.setTransform(scale,0,0,-scale,-94*scale,7*scale);
        ctx.fillStyle="#d6d8da";ctx.strokeStyle="#9ca3a8";ctx.lineWidth=.4*dpr/scale;ctx.fill(assets.paths.neighbours);ctx.stroke(assets.paths.neighbours);
        const fields=f.fields[card.season],base=fields[`climatology_${period}`],truth=fields.observed,values=fields[card.variant];
        for(let i=0;i<f.cells.length;i++){
          const c=f.cells[i],value=errorMode?Math.abs(base[i]-truth[i])-Math.abs(values[i]-truth[i]):values[i];
          const t=errorMode?(value+300)/600:value/f.rainLimits[card.season][period];ctx.fillStyle=palette(data.palettes[errorMode?"BrBG":"YlGnBu"],t);ctx.fillRect(c.lon-.125,c.lat-.125,.2505,.2505);
        }
        for(const [key,color,lw]of [["provinces","#52616b",.35],["indonesia","#263943",.8]]){ctx.strokeStyle=color;ctx.lineWidth=lw*dpr/scale;ctx.stroke(assets.paths[key]);}
      }
      function draw(card){
        const width=Math.max(230,Math.floor(card.canvas.getBoundingClientRect().width)),dpr=Math.min(devicePixelRatio||1,2);
        if(card.base.width===Math.round(width*dpr)&&card.base.height===Math.round(width*19/48*dpr))return;
        renderMap(card,card.base,width,dpr);card.canvas.width=card.base.width;card.canvas.height=card.base.height;paint(card);
      }
      for(const s of seasons){
        const date=data.calendar.find(c=>c.season===s);
        const variants=errorMode?[`cca_${period}`,`pcr_${period}`]:["observed",...chosen(period)];
        if(!errorMode){const dates=el("p","story-map-dates",`${s}: ${date.start} to ${date.end} · issued ${date.issue} · ${periodLabel(period)} training · source ending-year ${date.sourceYear}`);root.insertBefore(dates,status);}
        for(const variant of variants){
          const title=variant==="observed"?"Observed · CHIRPS3":method(variant),box=el("div","story-map-card"),canvas=el("canvas"),base=el("canvas");
          box.append(el("h4",null,errorMode?`${s} · ${title}`:title));canvas.setAttribute("tabindex","0");canvas.setAttribute("role","img");canvas.setAttribute("aria-label",`${s} ${title} map. Left and right arrows inspect scored country cells; Enter pins details.`);
          canvas.dataset.mapVariant=variant;canvas.dataset.season=s;box.append(canvas,el("p","story-map-coords","94°E                         118°E                         142°E · 12°S–7°N"));grid.append(box);
          const card={canvas,base,variant,season:s};cards.push(card);
          function hit(e,pin=false){const r=canvas.getBoundingClientRect(),lon=94+48*(e.clientX-r.left)/r.width,lat=7-19*(e.clientY-r.top)/r.height;
            const col=Math.floor((lon-94)/.25),row=Math.floor((7-lat)/.25),index=col>=0&&col<192&&row>=0&&row<76?lookup[row*192+col]:-1;
            if(index>=0)inspect(index,e,pin);else if(!pin)tip.leave();}
          canvas.addEventListener("pointermove",e=>hit(e));canvas.addEventListener("pointerleave",tip.leave);canvas.addEventListener("click",e=>hit(e,true));
          canvas.addEventListener("keydown",e=>{if(["ArrowLeft","ArrowRight","Enter"," "].includes(e.key)){e.preventDefault();const delta=e.key==="ArrowLeft"?-1:e.key==="ArrowRight"?1:0;inspect(Math.max(0,Math.min(f.cells.length-1,(active<0?0:active)+delta)),e,delta===0);}});
        }
      }
      status.replaceWith(grid);
      root.exportGraphic=async()=>{
        const width=1200,gap=24,cardWidth=(width-gap)/2,mapHeight=cardWidth*19/48,rowHeight=Math.ceil(mapHeight)+68,height=Math.ceil(cards.length/2)*rowHeight;
        const canvas=el("canvas");canvas.width=width*2;canvas.height=height*2;const ctx=canvas.getContext("2d");ctx.scale(2,2);ctx.fillStyle="white";ctx.fillRect(0,0,width,height);ctx.textBaseline="top";
        for(const [i,card]of cards.entries()){
          const x=(i%2)*(cardWidth+gap),y=Math.floor(i/2)*rowHeight,map=el("canvas");renderMap(card,map,cardWidth,2);
          ctx.fillStyle=INK;ctx.font="600 18px Arial, sans-serif";ctx.fillText(`${card.season} · ${card.variant==="observed"?"Observed · CHIRPS3":method(card.variant)}`,x,y);
          ctx.drawImage(map,x,y+28,cardWidth,mapHeight);ctx.font="12px Arial, sans-serif";ctx.fillStyle=MUTED;ctx.fillText("94°E–142°E · 12°S–7°N · grey land outside study area",x,y+mapHeight+36);
          // Yield between maps so large atlases keep the page and download UI responsive.
          await new Promise(resolve=>requestAnimationFrame(resolve));
        }return {image:canvas,width,height};
      };
      const max=errorMode?300:f.rainLimits[seasons[0]][period];legend(root,data.palettes[errorMode?"BrBG":"YlGnBu"],errorMode?-300:0,max,errorMode?"Absolute-error reduction vs climatology (mm): positive helps. Colours saturate beyond ±300 mm; details retain full values.":"Seasonal rainfall (mm). All five maps share the selected season's scale; the highest 1% is colour-saturated only.");
      if(!errorMode){
        const values=f.fields[seasons[0]],dates=data.calendar.find(c=>c.season===seasons[0]),rows=f.cells.map((cell,i)=>({season:seasons[0],training:periodLabel(period),targetStart:dates.start,targetEnd:dates.end,longitude:cell.lon,latitude:cell.lat,region:cell.shares.map(([name,w])=>`${name} (${num(100*w,2)}%)`).join("; "),observed:values.observed[i],raw:values.raw_cfsv2[i],climatology:values[`climatology_${period}`][i],cca:values[`cca_${period}`][i],pcr:values[`pcr_${period}`][i]}));
        root.append(sortableTable(rows,`${seasons[0]} grid values`,[["season","Season"],["training","Training"],["targetStart","Target starts"],["targetEnd","Target ends"],["longitude","Longitude",3],["latitude","Latitude",3],["region","Native province shares"],["observed","Observed (mm)"],["raw","Raw (mm)"],["climatology","Climatology (mm)"],["cca","CCA (mm)"],["pcr","PCR (mm)"]]));
      }
      resize=new ResizeObserver(()=>cards.forEach(draw));resize.observe(root);cards.forEach(draw);root.dataset.ready="true";root.dataset.state="ready";root.querySelector('.story-export button').disabled=false;
    }catch(error){status.textContent=`Map could not load: ${error.message}. Use the static figure or NetCDF links below.`;root.dataset.state="error";}
  }
  if(typeof IntersectionObserver!=="undefined"){observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))start();},{rootMargin:"250px"});observer.observe(root);}else queueMicrotask(start);
  return root;
}

export function rainfallMaps(data,files,season="OND",period="1991_2020"){return mapPanel(data,files,season,period,false);}
export function errorMaps(data,files,season="JJA",period="1991_2020"){return mapPanel(data,files,season,period,true);}
