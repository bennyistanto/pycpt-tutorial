// Shared presentation primitives adapted from ../story/story.js; case-one runtime is unchanged.
// Presentation only. Every aggregate score comes from the verified Python outputs.
const NS = "http://www.w3.org/2000/svg";
const INK = "#182e39", MUTED = "#566974";
const COLORS = {"Raw CFSv2":"#9b7164", Climatology:"#6b7280", CCA:"#147d92", PCR:"#c08325"};
let sequence = 0;
const el = (tag, cls, text) => {const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n;};
const sv = (tag, attrs={}, text) => {const n=document.createElementNS(NS,tag); for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v); if(text!==undefined)n.textContent=text; return n;};
const num = (v,d=1) => Number.isFinite(v) ? (Math.abs(v)<.5*10**(-d)?0:v).toLocaleString("en",{minimumFractionDigits:d,maximumFractionDigits:d}) : "—";
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
      const image=await (format==="SVG"&&root.exportSvg?root.exportSvg():create(root)),url=URL.createObjectURL(image),a=el("a");
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
  for(const note of root.querySelectorAll(".story-support-note"))if(note.textContent!==root.dataset.exportNote)text(note.textContent,14,MUTED);
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
  for(const note of root.querySelectorAll(".story-map-dates,.story-support-note"))if(note.textContent!==root.dataset.exportNote)text(note.textContent,14,MUTED);
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
  const body=el("div","story-table-body"), search=el("input"); search.type="search"; search.placeholder="Filter rows";
  search.setAttribute("aria-label",`Filter ${label} table`);
  const scroll=el("div","story-table-scroll"), table=el("table"), head=el("thead"), tbody=el("tbody"), tr=el("tr");
  table.setAttribute("aria-label",label); table.append(head,tbody); head.append(tr); scroll.append(table);
  const titles={season:'Season',verification:'Verification sample',method:'Method',year:'Training year',mode:'Mode',side:'Field',diagnostic:'Diagnostic',longitude:'Longitude',latitude:'Latitude',correlation:'Field–score correlation',variance_percent:'Variance (%)',cumulative_percent:'Cumulative variance (%)',retained:'Retained',view:'Field',value_mm:'Value (mm)',rmse:'RMSE (mm)',mae:'MAE (mm)',bias:'Bias (mm)'};
  const digits=k=>['year','mode'].includes(k)?0:['longitude','latitude'].includes(k)?3:['correlation','variance_percent','cumulative_percent'].includes(k)?6:2;
  const cols=columns || Object.keys(rows[0]||{}).map(k=>[k,titles[k]||k,digits(k)]);
  const normalized=rows.map(r=>({...r}));
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

const FIT_METHODS=['Raw CFSv2','Climatology','CCA','PCR'];
const FIT_COLORS=['#9b7164','#6b7280','#147d92','#c08325'];
const VERIFICATION={forecast_2023:'2023 forecasts',cross_validation:'CV5 diagnostics · 1991–2020'};
const metricText=m=>({rmse:'RMSE',mae:'MAE',bias:'Bias'}[m]);
function axis(svg,x1,y1,x2,y2){svg.append(sv('line',{x1,y1,x2,y2,stroke:'#adbdbf','stroke-width':1}));}
function tick(svg,x,y,text,anchor='middle'){svg.append(sv('text',{x,y,'text-anchor':anchor,class:'story-axis'},text));}

export function inputSummary(data,season='OND'){
  const root=el('div','story-view');root.dataset.view='fitting-inputs';
  root.append(el('h3','story-chart-title',`${season} · distinguish X, Y and F`));
  const rows=data.inputs.filter(r=>r.season===season);
  const table=sortableTable(rows,`${season} fitting inputs`,[['role','Input role'],['samples','Samples',0],['grid','Grid'],['complete_locations','Complete locations',0],['units','Units'],['target_starts','First target starts'],['target_ends','Last target ends']]);
  table.open=true;root.append(table);return root;
}

export function fittingScores(data,metric='rmse',verification='forecast_2023'){
  const rows=data.scores.filter(r=>r.verification===verification),title=`${VERIFICATION[verification]} · ${metricText(metric)}`;
  const root=panel('fitting-scores',title,'Hover, tap or focus a bar. All scores use the same 3,240 country-land cells.');
  root.dataset.exportKey=`${verification}-${metric}`;root.dataset.exportNote=verification==='forecast_2023'?data.notes.forecast:data.notes.cv;
  const svg=chartBox(root,850,390,title),tip=tooltip(root),marks=[];
  const vals=rows.map(r=>r[metric]),min=Math.min(0,...vals)*1.15,max=Math.max(0,...vals)*1.15||1;
  const y=v=>330-(v-min)/(max-min)*280;
  for(let i=0;i<=5;i++){const v=min+(max-min)*i/5;axis(svg,70,y(v),820,y(v));tick(svg,60,y(v)+4,num(v,0),'end');}
  tick(svg,75,22,`${metricText(metric)} (mm)`,'start');axis(svg,70,y(0),820,y(0));
  for(const [s,season]of data.seasons.entries()){
    tick(svg,265+s*370,363,season);
    for(const [m,method]of FIT_METHODS.entries()){
      const r=rows.find(r=>r.season===season&&r.method===method),x=135+s*370+m*65;
      const bar=sv('rect',{x,y:Math.min(y(r[metric]),y(0)),width:48,height:Math.max(1,Math.abs(y(r[metric])-y(0))),fill:FIT_COLORS[m]});
      bindMark(bar,tip,`${season} · ${method}`,[["Verification",VERIFICATION[verification]],["RMSE",`${num(r.rmse,2)} mm`],["MAE",`${num(r.mae,2)} mm`],["Bias",`${num(r.bias,2)} mm`]],r[metric]);
      marks.push(bar);svg.append(bar);tick(svg,x+24,r[metric]>=0?y(r[metric])-7:y(r[metric])+17,num(r[metric],1));
    }
  }
  keyboardGrid(svg,marks,4);root.append(seriesLegend(FIT_METHODS.map((name,i)=>({name,color:FIT_COLORS[i]}))),el('p','story-support-note',root.dataset.exportNote),sortableTable(rows.map(r=>({...r,verification:VERIFICATION[r.verification]})),'Fitting case national scores'));
  return root;
}

export function fittingScree(data,season='OND',side='predictor',view='variance'){
  const d=data.diagnostics[season][side],values=d[view],title=`${season} · ${side} EOF ${view==='variance'?'variance':'cumulative variance'}`;
  const root=panel('fitting-scree',title,'The spectrum has 30 entries. Exactly three EOFs were retained; variance retention is not forecast skill.');
  root.dataset.exportKey=`${season}-${side}-${view}`;root.dataset.exportNote='Full-training 1991–2020 spectrum · fixed three EOFs · no mode search.';
  const svg=chartBox(root,900,365,title),tip=tooltip(root),marks=[];
  const max=view==='variance'?Math.max(...values)*1.15:100,y=v=>305-v/max*260;
  for(let i=0;i<=5;i++){const v=max*i/5;axis(svg,65,y(v),875,y(v));tick(svg,55,y(v)+4,num(v,0),'end');}
  tick(svg,65,22,'Variance (%)','start');
  const rows=values.map((value,i)=>({season,side,mode:i+1,variance_percent:d.variance[i],cumulative_percent:d.cumulative[i],retained:i<3?'Yes':'No'}));
  for(const [i,r]of rows.entries()){
    const x=72+i*26.3,bar=sv('rect',{x,y:y(values[i]),width:21,height:Math.max(1,305-y(values[i])),fill:i<3?'#147d92':'#c8d5d1'});
    bindMark(bar,tip,`EOF ${i+1}`,[["Variance",`${num(r.variance_percent,4)}%`],["Cumulative",`${num(r.cumulative_percent,4)}%`],["Retained",r.retained]],values[i]);marks.push(bar);svg.append(bar);
    if(i<3||(i+1)%5===0)tick(svg,x+10.5,328,String(i+1));
  }
  tick(svg,450,355,'EOF mode · green bars are the three retained modes');keyboardGrid(svg,marks,30);
  root.append(el('p','story-support-note',root.dataset.exportNote),sortableTable(rows,'EOF variance spectrum'));return root;
}

function linePlot(root,series,title,{domain=[1991,2020],ylabel='RMSE (mm)',width=900,height=335}={}){
  const svg=chartBox(root,width,height,title),tip=tooltip(root),marks=[];
  const all=series.flatMap(s=>s.points.map(p=>p.value)),min=Math.min(0,...all),max=Math.max(...all),span=max-min||1;
  const left=68,right=width-24,top=36,bottom=height-58;
  const x=v=>left+(v-domain[0])/(domain[1]-domain[0])*(right-left),y=v=>bottom-(v-min)/span*(bottom-top);
  for(let i=0;i<=4;i++){const v=min+span*i/4;axis(svg,left,y(v),right,y(v));tick(svg,left-9,y(v)+4,num(v,1),'end');}
  for(const year of [1991,1995,2000,2005,2010,2015,2020])tick(svg,x(year),height-33,String(year));
  tick(svg,left,18,ylabel,'start');tick(svg,width/2,height-7,'Training target year');
  for(const s of series){
    svg.append(sv('polyline',{points:s.points.map(p=>`${x(p.year)},${y(p.value)}`).join(' '),fill:'none',stroke:s.color,'stroke-width':1.8}));
    for(const p of s.points){const mark=sv('circle',{cx:x(p.year),cy:y(p.value),r:3.7,fill:s.color,stroke:'white','stroke-width':.5});
      bindMark(mark,tip,`${s.name} · ${p.year}`,p.entries||[['Value',num(p.value,4)]],p.value);marks.push(mark);svg.append(mark);}
  }
  keyboardGrid(svg,marks,30);return svg;
}

export function fittingCv(data,season='OND',metric='rmse'){
  const rows=data.yearly.filter(r=>r.season===season),title=`${season} · CV-year spatial ${metricText(metric)}`;
  const root=panel('fitting-cv',title,'Inspect years, methods and residuals; these are deterministic within-training diagnostics.');
  root.dataset.exportKey=`${season}-${metric}`;root.dataset.exportNote=data.notes.cv;
  linePlot(root,FIT_METHODS.map((name,i)=>({name,color:FIT_COLORS[i],points:rows.filter(r=>r.method===name).map(r=>({year:r.year,value:r[metric],entries:[['RMSE',`${num(r.rmse,2)} mm`],['MAE',`${num(r.mae,2)} mm`],['Bias',`${num(r.bias,2)} mm`]]}))})),title,{ylabel:`${metricText(metric)} (mm)`});
  root.append(seriesLegend(FIT_METHODS.map((name,i)=>({name,color:FIT_COLORS[i]}))),el('p','story-support-note',data.notes.cv),sortableTable(rows,'CV year scores'));return root;
}

function rgb(c){return [1,3,5].map(i=>parseInt(c.slice(i,i+2),16));}
function mix(a,b,t){return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*t)).join(',')})`;}
const DIVERGE=Array.from({length:257},(_,i)=>i<=128?mix(rgb('#2166ac'),rgb('#f7f7f7'),i/128):mix(rgb('#f7f7f7'),rgb('#b2182b'),(i-128)/128));
const ERROR=Array.from({length:257},(_,i)=>mix(rgb('#fff7bc'),rgb('#b2182b'),i/256));
function rings(g){
  if(g.type==='Polygon')return g.coordinates;
  if(g.type==='MultiPolygon')return g.coordinates.flat();
  if(g.type==='GeometryCollection')return g.geometries.flatMap(rings);
  return [];
}

function correlationCanvas(root,tip,field,longitude,latitude,geography,{title,predictor=false,min=-1,max=1,colors=DIVERGE,unit='correlation'}={}){
  const card=el('div','story-map-card fitting-map-card'),canvas=el('canvas');card.append(el('h4',null,title),canvas);canvas.tabIndex=0;canvas.setAttribute('role','img');
  canvas.setAttribute('aria-label',`${title}. Hover or tap a cell; arrow keys inspect adjacent grid cells. ${unit}.`);
  const extent=predictor?[85,155,-20,20]:[94,142,-12,8],W=900,L=72,R=20,T=32,B=72,pw=W-L-R,ph=pw*(extent[3]-extent[2])/(extent[1]-extent[0]),H=Math.ceil(ph+T+B);
  canvas.width=W;canvas.height=H;canvas.style.aspectRatio=`${W}/${H}`;
  const ctx=canvas.getContext('2d'),x=v=>L+(v-extent[0])/(extent[1]-extent[0])*pw,y=v=>T+(extent[3]-v)/(extent[3]-extent[2])*ph;
  ctx.fillStyle='white';ctx.fillRect(0,0,W,H);ctx.save();ctx.beginPath();ctx.rect(L,T,pw,ph);ctx.clip();
  const dx=Math.abs(longitude[1]-longitude[0]),dy=Math.abs(latitude[1]-latitude[0]);
  for(let j=0;j<latitude.length;j++)for(let i=0;i<longitude.length;i++){
    const value=field[j][i];if(value===null)continue;
    ctx.fillStyle=palette(colors,(value-min)/(max-min||1));
    const xx=x(longitude[i]-dx/2),yy=y(latitude[j]+dy/2);
    ctx.fillRect(xx,yy,pw*dx/(extent[1]-extent[0])+.8,ph*dy/(extent[3]-extent[2])+.8);
  }
  function boundary(layer,fill=false){
    for(const f of layer.features)for(const ring of rings(f.geometry)){
      ctx.beginPath();ring.forEach((p,i)=>i?ctx.lineTo(x(p[0]),y(p[1])):ctx.moveTo(x(p[0]),y(p[1])));ctx.closePath();
      if(fill){ctx.fillStyle='#e3e5e4';ctx.fill();}ctx.strokeStyle='#5b6c68';ctx.lineWidth=.75;ctx.stroke();
    }
  }
  if(predictor)boundary(geography.predictor);else{boundary(geography.neighbours,true);boundary(geography.indonesia);boundary(geography.provinces);}
  ctx.restore();ctx.strokeStyle='#8b9f9b';ctx.strokeRect(L,T,pw,ph);ctx.font='26px Arial';ctx.fillStyle=MUTED;ctx.textAlign='center';
  for(let lon=Math.ceil(extent[0]/10)*10;lon<=extent[1];lon+=10)ctx.fillText(String(lon),x(lon),T+ph+32);
  ctx.textAlign='right';for(let lat=Math.ceil(extent[2]/10)*10;lat<=extent[3];lat+=10)ctx.fillText(String(lat),L-9,y(lat)+6);
  ctx.textAlign='center';ctx.fillText('Longitude',L+pw/2,H-10);ctx.save();ctx.translate(21,T+ph/2);ctx.rotate(-Math.PI/2);ctx.fillText('Latitude',0,0);ctx.restore();
  let index=[Math.floor(longitude.length/2),Math.floor(latitude.length/2)];
  function show(i,j,e,pin=false){
    if(i<0||j<0||i>=longitude.length||j>=latitude.length)return;
    index=[i,j];const value=field[j][i];
    tip.show(title,[['Longitude',num(longitude[i],3)],['Latitude',num(latitude[j],3)],[unit,value===null?'Outside evaluated support':num(value,4)]],e,pin);
  }
  function hit(e,pin=false){const b=canvas.getBoundingClientRect(),px=(e.clientX-b.left)*W/b.width,py=(e.clientY-b.top)*H/b.height;if(px<L||px>L+pw||py<T||py>T+ph)return;
    const lon=extent[0]+(px-L)/pw*(extent[1]-extent[0]),lat=extent[3]-(py-T)/ph*(extent[3]-extent[2]);
    show(Math.round((lon-longitude[0])/(longitude[1]-longitude[0])),Math.round((lat-latitude[0])/(latitude[1]-latitude[0])),e,pin);
  }
  canvas.addEventListener('pointermove',e=>hit(e));canvas.addEventListener('click',e=>hit(e,true));canvas.addEventListener('pointerleave',tip.leave);
  canvas.addEventListener('focus',e=>show(...index,e));canvas.addEventListener('keydown',e=>{
    const step={ArrowRight:[1,0],ArrowLeft:[-1,0],ArrowUp:[0,latitude[1]>latitude[0]?1:-1],ArrowDown:[0,latitude[1]>latitude[0]?-1:1]}[e.key];
    if(!step)return;e.preventDefault();show(Math.max(0,Math.min(longitude.length-1,index[0]+step[0])),Math.max(0,Math.min(latitude.length-1,index[1]+step[1])),e,true);
  });
  canvas.exportMap={title};return {card,canvas};
}

async function combineMaps(maps,chartRoot=null){
  const width=1100,column=550,gap=12,rowHeights=[];
  for(let i=0;i<maps.length;i+=2)rowHeights.push(Math.max(...maps.slice(i,i+2).map(c=>c.height*column/c.width))+35);
  const graphic=chartRoot?await svgGraphic(chartRoot):null,chartH=graphic?graphic.height*width/graphic.width:0;
  const canvas=el('canvas');canvas.width=width;canvas.height=Math.ceil(rowHeights.reduce((a,b)=>a+b+gap,0)+chartH+10);
  const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle=INK;ctx.font='17px Arial';
  let yy=0;for(let i=0;i<maps.length;i+=2){for(let j=0;j<2&&i+j<maps.length;j++){const map=maps[i+j];ctx.fillText(map.exportMap.title,j*column+14,yy+20);ctx.drawImage(map,j*column,yy+30,column,map.height*column/map.width);}yy+=rowHeights[i/2]+gap;}
  if(graphic)ctx.drawImage(graphic.image,0,yy,width,chartH);
  return {image:canvas,width:canvas.width,height:canvas.height};
}

export function fittingPatterns(data,geography,season='OND',kind='cca',mode='1'){
  mode=Number(mode);const title=`${season} · ${kind.toUpperCase()} ${mode} · full-training patterns`;
  const root=panel('fitting-patterns',title,'Maps show field–score correlations; the lines show separately standardized training scores.');
  root.dataset.exportKey=`${season}-${kind}-${mode}`;root.dataset.exportNote=data.notes.patterns;
  const maps=el('div','story-map-grid'),tip=tooltip(root),canvases=[],rows=[],series=[];
  for(const [side,name,color]of [['predictor','X predictor','#147d92'],['predictand','Y predictand','#c08325']]){
    const d=data.diagnostics[season][side],a=d[kind].fields[mode-1];
    const {card,canvas}=correlationCanvas(root,tip,a,d.longitude,d.latitude,geography,{title:name,predictor:side==='predictor'});maps.append(card);canvases.push(canvas);
    series.push({name,color,points:d.years.map((year,i)=>({year,value:d[kind].standardizedScore[mode-1][i],entries:[['Standardized score',num(d[kind].standardizedScore[mode-1][i],4)],['Native score',num(d[kind].score[mode-1][i],6)]]}))});
    for(let j=0;j<d.latitude.length;j++)for(let i=0;i<d.longitude.length;i++)if(a[j][i]!==null)rows.push({season,diagnostic:kind.toUpperCase(),mode,side,longitude:d.longitude[i],latitude:d.latitude[j],correlation:a[j][i]});
  }
  root.append(maps);linePlot(root,series,title,{ylabel:'Standardized diagnostic score',height:300});
  root.append(seriesLegend(series.map(s=>({name:s.name,color:s.color}))));
  legend(root,DIVERGE,-1,1,'Field–score correlation · 1991–2020 training · not forecast skill');
  const note=kind==='cca'?`Native canonical correlation for pair ${mode}: ${num(data.diagnostics[season].canonical[mode-1],6)}. This is a training relationship.`:'X and Y EOFs are independently ranked variance modes; sharing a mode number does not make them a canonical pair.';
  root.append(el('p','story-support-note',note),sortableTable(rows,'Training correlation grid'));
  root.exportGraphic=()=>combineMaps(canvases,root);
  const svgButton=root.querySelectorAll('.story-export button')[1];svgButton.textContent='Download score series (SVG)';
  root.exportSvg=()=>{const f=el('div');f.dataset.exportNote=`${season} · ${kind.toUpperCase()} ${mode} · 1991–2020 · standardized score series only; maps are in the PNG export.`;
    f.append(el('h3','story-chart-title',`${season} ${kind.toUpperCase()} ${mode} · training score series`),root.querySelector('svg.story-svg').cloneNode(true),seriesLegend(series.map(s=>({name:s.name,color:s.color}))));return currentViewSvg(f);};
  return root;
}

export function fittingErrors(data,geography,season='JJA',view='absoluteError'){
  const d=data.maps[season],title=`${season} 2023 · ${view==='rainfall'?'forecast rainfall':view==='signedError'?'signed forecast error':'absolute forecast error'}`;
  const root=panel('error-maps',title,'Identical support, units and colour scale for all four methods. Hover, tap or use arrow keys to inspect cells.');
  root.dataset.exportKey=`fitting-${season}-${view}`;root.dataset.exportNote=data.notes.forecast;
  const values=FIT_METHODS.flatMap(m=>d[view][m].flat().filter(v=>v!==null)),max=Math.max(...values.map(Math.abs)),min=view==='signedError'?-max:0,colors=view==='signedError'?DIVERGE:ERROR;
  const maps=el('div','story-map-grid'),tip=tooltip(root),canvases=[],rows=[];
  for(const method of FIT_METHODS){const a=d[view][method],{card,canvas}=correlationCanvas(root,tip,a,d.longitude,d.latitude,geography,{title:method,min,max,colors,unit:'mm'});maps.append(card);canvases.push(canvas);
    for(let j=0;j<d.latitude.length;j++)for(let i=0;i<d.longitude.length;i++)if(a[j][i]!==null)rows.push({season,method,longitude:d.longitude[i],latitude:d.latitude[j],view:{rainfall:'Forecast rainfall',absoluteError:'Absolute error',signedError:'Signed error'}[view],value_mm:a[j][i]});}
  root.append(maps);legend(root,colors,min,max,view==='signedError'?'Forecast minus observed rainfall (mm)':view==='rainfall'?'Forecast seasonal rainfall (mm)':'Absolute forecast minus observed rainfall (mm)');
  root.append(el('p','story-support-note',data.notes.forecast),sortableTable(rows,'2023 forecast grid'));root.exportGraphic=()=>combineMaps(canvases);return root;
}

