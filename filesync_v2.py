#!/usr/bin/env python3
"""
FileBeam Sync v2 - Two-Way PC ↔ Phone Sync
Stunning interactive UI. Run on PC, open on phone browser.
"""

import os, json, mimetypes, secrets, hashlib, time, argparse, re
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime

DEFAULT_PORT = 8081
DEFAULT_ROOT = str(Path.home() / "FileBeamSync")
ACCESS_TOKEN = secrets.token_urlsafe(16)
os.makedirs(DEFAULT_ROOT, exist_ok=True)

def human_size(n):
    for u in ("B","KB","MB","GB","TB"):
        if n < 1024: return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"

def mime(path):
    t, _ = mimetypes.guess_type(path)
    return t or "application/octet-stream"

def scan_dir(root):
    files = {}
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, root).replace("\\","/")
            try:
                stat = os.stat(fp)
                files[rel] = {
                    "rel":rel,"size":stat.st_size,
                    "size_human":human_size(stat.st_size),
                    "mtime":stat.st_mtime,
                    "modified":datetime.fromtimestamp(stat.st_mtime).strftime("%b %d %H:%M"),
                    "mime":mime(fp),
                }
            except: pass
    return files

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FileBeam Sync</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#f6f7fb;
  --card:#ffffff;
  --card2:#f0f2f8;
  --border:#e4e7f0;
  --border2:#d4d8ea;
  --accent:#5b6af0;
  --accent-light:#eef0ff;
  --accent-dark:#4554d4;
  --pink:#e040fb;
  --green:#00c48c;
  --yellow:#ffb020;
  --red:#ff4d4f;
  --text:#111827;
  --muted:#7b849c;
  --muted2:#c0c5d8;
  --shadow-sm:0 1px 3px rgba(30,40,80,.07),0 1px 2px rgba(30,40,80,.05);
  --shadow:0 4px 16px rgba(30,40,80,.08),0 1px 4px rgba(30,40,80,.05);
  --shadow-lg:0 12px 40px rgba(30,40,80,.12);
  --r:14px;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{font-family:'Plus Jakarta Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}

::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:99px}

/* ── Top bar ── */
.topbar{
  background:rgba(255,255,255,.9);
  backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);
  position:sticky;top:0;z-index:100;
  padding:0 20px;height:60px;
  display:flex;align-items:center;justify-content:space-between;gap:12px;
}
.brand{display:flex;align-items:center;gap:11px}
.brand-ico{
  width:38px;height:38px;border-radius:11px;
  background:linear-gradient(135deg,var(--accent),var(--pink));
  display:flex;align-items:center;justify-content:center;font-size:18px;
  box-shadow:0 4px 14px rgba(91,106,240,.35);
}
.brand-name{font-size:1.1rem;font-weight:800;letter-spacing:-.03em;color:var(--text)}
.brand-sub{font-size:.65rem;font-family:'JetBrains Mono',monospace;color:var(--muted);margin-top:-1px}
.status-badge{
  display:flex;align-items:center;gap:6px;
  padding:6px 12px;border-radius:99px;font-size:.75rem;font-weight:600;
  border:1px solid;
}
.status-on{background:#edfff6;border-color:#a7f0cf;color:var(--green)}
.status-off{background:#fff1f1;border-color:#ffc4c4;color:var(--red)}
.live-dot{width:7px;height:7px;border-radius:50%;background:currentColor}
.live-dot.pulse{animation:livePulse 1.8s ease infinite}
@keyframes livePulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}

/* ── Container ── */
.wrap{max-width:860px;margin:0 auto;padding:24px 16px 60px}

/* ── Stats row ── */
.stats-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px}
.stat-card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:16px;
  box-shadow:var(--shadow-sm);
  display:flex;flex-direction:column;gap:4px;
  transition:transform .2s,box-shadow .2s;
}
.stat-card:hover{transform:translateY(-2px);box-shadow:var(--shadow)}
.stat-num{font-size:1.6rem;font-weight:800;font-family:'JetBrains Mono',monospace;line-height:1}
.stat-lbl{font-size:.7rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.stat-num.blue{color:var(--accent)}
.stat-num.green{color:var(--green)}
.stat-num.yellow{color:var(--yellow)}

/* ── Tabs ── */
.tab-bar{
  display:flex;background:var(--card2);border:1px solid var(--border);
  border-radius:12px;padding:4px;gap:3px;margin-bottom:20px;
}
.tab-btn{
  flex:1;padding:9px 6px;border:none;background:transparent;
  border-radius:9px;font-family:'Plus Jakarta Sans',sans-serif;
  font-size:.83rem;font-weight:600;color:var(--muted);
  cursor:pointer;transition:all .2s;
  display:flex;align-items:center;justify-content:center;gap:6px;
}
.tab-btn.active{
  background:var(--card);color:var(--accent);
  box-shadow:var(--shadow-sm);
}
.tab-badge{
  background:var(--accent);color:#fff;
  border-radius:99px;padding:1px 7px;font-size:.65rem;
  min-width:18px;text-align:center;
}

/* ── Card ── */
.card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);box-shadow:var(--shadow-sm);overflow:hidden;
}
.card-head{
  padding:16px 18px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;gap:10px;
}
.card-title{font-size:.88rem;font-weight:700;display:flex;align-items:center;gap:7px}
.card-body{padding:4px}

/* ── File row ── */
.f-row{
  display:flex;align-items:center;gap:10px;
  padding:10px 14px;border-radius:10px;margin:2px;
  transition:background .15s;cursor:default;
}
.f-row:hover{background:var(--card2)}
.f-ico{
  width:36px;height:36px;border-radius:9px;
  display:flex;align-items:center;justify-content:center;
  font-size:17px;flex-shrink:0;
}
.ico-v{background:rgba(224,64,251,.1)} .ico-i{background:rgba(255,176,32,.1)}
.ico-a{background:rgba(0,196,140,.1)}  .ico-d{background:rgba(91,106,240,.1)}
.ico-z{background:rgba(255,77,79,.1)}  .ico-g{background:rgba(123,132,156,.1)}

.f-info{flex:1;min-width:0}
.f-name{font-size:.86rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.f-meta{font-size:.71rem;font-family:'JetBrains Mono',monospace;color:var(--muted);margin-top:2px}
.f-right{display:flex;align-items:center;gap:8px;flex-shrink:0}

/* Status chips */
.chip{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:99px;font-size:.68rem;font-weight:700;border:1px solid}
.chip-green{background:#edfff6;border-color:#a7f0cf;color:var(--green)}
.chip-blue{background:var(--accent-light);border-color:#c4cbff;color:var(--accent)}
.chip-yellow{background:#fffbeb;border-color:#fde68a;color:var(--yellow)}
.chip-muted{background:var(--card2);border-color:var(--border2);color:var(--muted)}

/* Action button */
.act{
  width:30px;height:30px;border-radius:8px;border:1px solid var(--border2);
  background:var(--card2);color:var(--muted);font-size:.78rem;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;transition:all .18s;text-decoration:none;
}
.act:hover{border-color:var(--accent);color:var(--accent);background:var(--accent-light)}

/* ── Buttons ── */
.btn{
  display:inline-flex;align-items:center;gap:7px;
  padding:10px 20px;border-radius:10px;border:none;
  font-family:'Plus Jakarta Sans',sans-serif;font-size:.85rem;font-weight:700;
  cursor:pointer;transition:all .2s;white-space:nowrap;
}
.btn-primary{background:linear-gradient(135deg,var(--accent),var(--accent-dark));color:#fff;box-shadow:0 2px 10px rgba(91,106,240,.3)}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 18px rgba(91,106,240,.45)}
.btn-outline{background:var(--card);border:1.5px solid var(--border2);color:var(--text)}
.btn-outline:hover{border-color:var(--accent);color:var(--accent)}
.btn-green{background:linear-gradient(135deg,#00c48c,#00a872);color:#fff;box-shadow:0 2px 10px rgba(0,196,140,.3)}
.btn-green:hover{transform:translateY(-1px);box-shadow:0 4px 18px rgba(0,196,140,.4)}
.btn-sm{padding:7px 14px;font-size:.78rem;border-radius:8px}
.btn-row{display:flex;gap:8px;padding:14px;border-top:1px solid var(--border);flex-wrap:wrap}

/* ── Upload zone ── */
.upload-zone{
  border:2px dashed var(--border2);border-radius:12px;
  padding:32px 20px;text-align:center;cursor:pointer;
  transition:all .22s;margin:14px;
}
.upload-zone:hover,.upload-zone.drag{
  border-color:var(--accent);
  background:var(--accent-light);
}
.uz-ico{font-size:2.8rem;margin-bottom:10px;display:block}
.uz-title{font-size:.95rem;font-weight:700}
.uz-sub{font-size:.8rem;color:var(--muted);margin-top:4px}
.uz-sub strong{color:var(--accent)}

/* ── Progress ── */
.prog-box{padding:0 14px 14px}
.prog-track{height:6px;background:var(--card2);border-radius:99px;overflow:hidden}
.prog-fill{
  height:100%;border-radius:99px;
  background:linear-gradient(90deg,var(--accent),var(--pink));
  width:0%;transition:width .3s;
}
.prog-info{display:flex;justify-content:space-between;align-items:center;margin-top:6px}
.prog-label{font-family:'JetBrains Mono',monospace;font-size:.72rem;color:var(--muted)}
.prog-pct{font-family:'JetBrains Mono',monospace;font-size:.72rem;font-weight:600;color:var(--accent)}

/* ── Empty ── */
.empty{padding:40px;text-align:center;color:var(--muted)}
.empty-ico{font-size:2.8rem;margin-bottom:8px;opacity:.5}
.empty-txt{font-size:.83rem}

/* ── Toast ── */
.toast-stack{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:999;display:flex;flex-direction:column;gap:6px;align-items:center;pointer-events:none}
.toast{
  background:rgba(17,24,39,.92);color:#fff;
  padding:10px 18px;border-radius:12px;
  font-size:.82rem;font-weight:600;
  backdrop-filter:blur(8px);
  transform:translateY(20px);opacity:0;
  transition:all .3s cubic-bezier(.34,1.56,.64,1);
  white-space:nowrap;
}
.toast.show{transform:none;opacity:1}
.toast.success{background:rgba(0,196,140,.9)}
.toast.error{background:rgba(255,77,79,.9)}

/* ── Animations ── */
@keyframes slideIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.f-row{animation:slideIn .22s ease both}
.f-row:nth-child(1){animation-delay:.04s} .f-row:nth-child(2){animation-delay:.08s}
.f-row:nth-child(3){animation-delay:.12s} .f-row:nth-child(4){animation-delay:.16s}
.f-row:nth-child(n+5){animation-delay:.2s}

/* ── Responsive ── */
@media(max-width:520px){
  .stats-row{grid-template-columns:repeat(3,1fr)}
  .stat-num{font-size:1.2rem}
  .tab-btn span:not(.tab-badge){display:none}
}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <div class="brand-ico">🔄</div>
    <div>
      <div class="brand-name">FileBeam Sync</div>
      <div class="brand-sub">pc ↔ phone · two-way</div>
    </div>
  </div>
  <div class="status-badge status-on" id="statusBadge">
    <div class="live-dot pulse" id="liveDot"></div>
    <span id="statusText">Connecting…</span>
  </div>
</div>

<div class="wrap">

  <!-- Stats -->
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-num blue" id="sTotal">—</div>
      <div class="stat-lbl">PC Files</div>
    </div>
    <div class="stat-card">
      <div class="stat-num green" id="sSize">—</div>
      <div class="stat-lbl">Total Size</div>
    </div>
    <div class="stat-card">
      <div class="stat-num yellow" id="sPending">—</div>
      <div class="stat-lbl">Pending</div>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tab-bar">
    <button class="tab-btn active" id="tab-sync-btn" onclick="showTab('sync')">🔄 <span>Sync</span> <span class="tab-badge" id="pendingBadge">0</span></button>
    <button class="tab-btn" id="tab-pc-btn" onclick="showTab('pc')">💻 <span>PC Files</span></button>
    <button class="tab-btn" id="tab-upload-btn" onclick="showTab('upload')">⬆ <span>Upload</span></button>
  </div>

  <!-- SYNC TAB -->
  <div id="tab-sync">
    <div class="card">
      <div class="card-head">
        <div class="card-title">📋 <span>Sync Status</span></div>
        <button class="btn btn-outline btn-sm" onclick="loadAll()">↺ Refresh</button>
      </div>
      <div class="card-body" id="syncBody"><div class="empty"><div class="empty-ico">⏳</div><div class="empty-txt">Scanning…</div></div></div>
      <div class="btn-row">
        <button class="btn btn-green" onclick="doSync()">🔄 Mark All Synced</button>
        <button class="btn btn-outline" onclick="showTab('upload')">⬆ Upload from Phone</button>
      </div>
    </div>
  </div>

  <!-- PC FILES TAB -->
  <div id="tab-pc" style="display:none">
    <div class="card">
      <div class="card-head">
        <div class="card-title">💻 <span>Files on PC</span></div>
        <button class="btn btn-outline btn-sm" onclick="loadPCFiles()">↺</button>
      </div>
      <div class="card-body" id="pcBody"><div class="empty"><div class="empty-ico">⏳</div></div></div>
    </div>
  </div>

  <!-- UPLOAD TAB -->
  <div id="tab-upload" style="display:none">
    <div class="card" style="margin-bottom:14px">
      <div class="card-head">
        <div class="card-title">📤 <span>Phone → PC</span></div>
      </div>
      <div class="upload-zone" id="uploadZone"
           ondragover="uzOver(event)" ondragleave="uzLeave()"
           ondrop="uzDrop(event)" onclick="document.getElementById('fileIn').click()">
        <span class="uz-ico">📱</span>
        <div class="uz-title">Send files to your PC</div>
        <div class="uz-sub">Tap to pick files · or drag & drop<br/><strong>Photos, videos, documents — anything</strong></div>
      </div>
      <input type="file" id="fileIn" multiple style="display:none" onchange="uploadFiles(this.files)"/>
      <div class="prog-box" id="progBox" style="display:none">
        <div class="prog-track"><div class="prog-fill" id="progFill"></div></div>
        <div class="prog-info">
          <span class="prog-label" id="progLabel">Uploading…</span>
          <span class="prog-pct" id="progPct">0%</span>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-head">
        <div class="card-title">📥 <span>PC → Phone</span></div>
      </div>
      <div style="padding:16px;font-size:.83rem;color:var(--muted);line-height:1.6">
        Go to the <strong>PC Files</strong> tab → tap the ⬇ button on any file to save it directly to your phone.
      </div>
    </div>
  </div>

</div>

<div class="toast-stack" id="toastStack"></div>

<script>
const TOKEN = "{{TOKEN}}";
const A = p => `/api${p}?token=${TOKEN}`;
let pcFiles = {};
let activeTab = "sync";

// ── Init ──────────────────────────────────────────────────────────────────
async function init(){
  await ping();
  await loadAll();
  setInterval(ping, 8000);
}

async function ping(){
  try{
    const r = await fetch(A("/ping"), {signal:AbortSignal.timeout(3000)});
    const ok = r.ok;
    document.getElementById("statusBadge").className = "status-badge " + (ok?"status-on":"status-off");
    document.getElementById("liveDot").className = "live-dot" + (ok?" pulse":"");
    document.getElementById("statusText").textContent = ok ? "Connected" : "Offline";
  } catch {
    document.getElementById("statusBadge").className = "status-badge status-off";
    document.getElementById("statusText").textContent = "Offline";
  }
}

async function loadAll(){
  try{
    const r = await fetch(A("/files"));
    const d = await r.json();
    pcFiles = d.files || {};
    const total = Object.keys(pcFiles).length;
    const size = Object.values(pcFiles).reduce((a,f)=>a+f.size,0);
    document.getElementById("sTotal").textContent = total;
    document.getElementById("sSize").textContent = humanSize(size);
    const synced = getSynced();
    const pending = total - Object.keys(pcFiles).filter(k=>synced.includes(k)).length;
    document.getElementById("sPending").textContent = pending;
    document.getElementById("pendingBadge").textContent = pending;
    if(activeTab==="sync") renderSync();
    if(activeTab==="pc") renderPC();
  } catch(e){ toast("Connection failed","error"); }
}

// ── Tabs ──────────────────────────────────────────────────────────────────
function showTab(id){
  ["sync","pc","upload"].forEach(t=>{
    document.getElementById("tab-"+t).style.display = t===id?"block":"none";
    document.getElementById("tab-"+t+"-btn").classList.toggle("active",t===id);
  });
  activeTab = id;
  if(id==="sync") renderSync();
  if(id==="pc") renderPC();
}

// ── Sync tab ──────────────────────────────────────────────────────────────
function getSynced(){ return JSON.parse(sessionStorage.getItem("synced")||"[]"); }
function setSynced(s){ sessionStorage.setItem("synced",JSON.stringify(s)); }
function getUploaded(){ return JSON.parse(sessionStorage.getItem("uploaded")||"[]"); }

function renderSync(){
  const el = document.getElementById("syncBody");
  const synced = getSynced();
  const uploaded = getUploaded();
  const rows = [];
  Object.values(pcFiles).forEach(f=>{
    rows.push({...f, status: synced.includes(f.rel)?"synced":"pc_only"});
  });
  uploaded.forEach(name=>{
    if(!pcFiles[name]) rows.push({rel:name,size_human:"—",modified:"just now",mime:"",status:"phone_only"});
  });
  if(!rows.length){ el.innerHTML=`<div class="empty"><div class="empty-ico">🌿</div><div class="empty-txt">No files yet. Upload some to get started!</div></div>`; return; }
  const chips = {synced:["chip-green","✓ Synced"],pc_only:["chip-blue","💻 PC Only"],phone_only:["chip-yellow","📱 Phone"]};
  el.innerHTML = rows.map(f=>{
    const [cc,cl]=chips[f.status]||["chip-muted","—"];
    const [ico,icls]=icoFor(f.mime);
    return `<div class="f-row">
      <div class="f-ico ${icls}">${ico}</div>
      <div class="f-info">
        <div class="f-name">${f.rel}</div>
        <div class="f-meta">${f.size_human} · ${f.modified}</div>
      </div>
      <div class="f-right">
        <span class="chip ${cc}">${cl}</span>
        ${f.status!=="phone_only"?`<a class="act" href="${A('/download?path='+encodeURIComponent(f.rel))}" download title="Download">⬇</a>`:""}
      </div>
    </div>`;
  }).join("");
}

function doSync(){
  const synced = getSynced();
  Object.keys(pcFiles).forEach(k=>{ if(!synced.includes(k)) synced.push(k); });
  setSynced(synced);
  toast("All files marked as synced ✓","success");
  loadAll();
}

// ── PC Files tab ──────────────────────────────────────────────────────────
function renderPC(){
  const el = document.getElementById("pcBody");
  const files = Object.values(pcFiles);
  if(!files.length){ el.innerHTML=`<div class="empty"><div class="empty-ico">📭</div><div class="empty-txt">Sync folder is empty</div></div>`; return; }
  el.innerHTML = files.map(f=>{
    const [ico,icls]=icoFor(f.mime);
    return `<div class="f-row">
      <div class="f-ico ${icls}">${ico}</div>
      <div class="f-info">
        <div class="f-name">${f.rel}</div>
        <div class="f-meta">${f.size_human} · ${f.modified}</div>
      </div>
      <div class="f-right">
        <a class="act" href="${A('/download?path='+encodeURIComponent(f.rel))}" download title="Save to phone">⬇</a>
      </div>
    </div>`;
  }).join("");
}

function loadPCFiles(){ loadAll(); }

// ── Upload ────────────────────────────────────────────────────────────────
function uzOver(e){e.preventDefault();document.getElementById("uploadZone").classList.add("drag")}
function uzLeave(){document.getElementById("uploadZone").classList.remove("drag")}
function uzDrop(e){e.preventDefault();uzLeave();uploadFiles(e.dataTransfer.files)}

async function uploadFiles(files){
  if(!files.length) return;
  const pb=document.getElementById("progBox"), pf=document.getElementById("progFill");
  const pl=document.getElementById("progLabel"), pp=document.getElementById("progPct");
  pb.style.display="block";
  const uploaded = getUploaded();
  for(let i=0;i<files.length;i++){
    const file=files[i];
    pl.textContent=`${file.name}`;
    const form=new FormData();
    form.append("file",file); form.append("path","/");
    await new Promise(res=>{
      const xhr=new XMLHttpRequest();
      xhr.upload.onprogress=ev=>{
        const pct=Math.round((i+ev.loaded/ev.total)/files.length*100);
        pf.style.width=pct+"%"; pp.textContent=pct+"%";
      };
      xhr.onload=res;
      xhr.open("POST",A("/upload")); xhr.send(form);
    });
    if(!uploaded.includes(file.name)) uploaded.push(file.name);
  }
  sessionStorage.setItem("uploaded",JSON.stringify(uploaded));
  pf.style.width="100%"; pp.textContent="100%";
  pl.textContent=`Done! ${files.length} file(s) sent ✓`;
  toast(`${files.length} file(s) uploaded to PC!`,"success");
  setTimeout(()=>{ pb.style.display="none"; pf.style.width="0%"; pp.textContent="0%"; },3000);
  loadAll();
}

// ── Helpers ───────────────────────────────────────────────────────────────
function icoFor(m=""){
  if(m.startsWith("video/")) return ["🎬","ico-v"];
  if(m.startsWith("image/")) return ["🖼","ico-i"];
  if(m.startsWith("audio/")) return ["🎵","ico-a"];
  if(m.includes("pdf")||m.startsWith("text/")) return ["📄","ico-d"];
  if(m.includes("zip")||m.includes("rar")) return ["🗜","ico-z"];
  return ["📎","ico-g"];
}
function humanSize(n){
  for(const u of["B","KB","MB","GB"]){if(n<1024)return n.toFixed(1)+" "+u;n/=1024}
  return n.toFixed(1)+" TB";
}
function toast(msg,type="info"){
  const stack=document.getElementById("toastStack");
  const el=document.createElement("div");
  el.className=`toast ${type}`; el.textContent=msg;
  stack.appendChild(el);
  requestAnimationFrame(()=>el.classList.add("show"));
  setTimeout(()=>{ el.classList.remove("show"); setTimeout(()=>el.remove(),400); },3000);
}

init();
</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    root = DEFAULT_ROOT
    token = ACCESS_TOKEN

    def log_message(self, fmt, *args): pass

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",len(body))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(body)

    def check_token(self, qs):
        return qs.get("token",[""])[0] == self.token

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path in ("/",""):
            html = HTML.replace("{{TOKEN}}", self.token)
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",len(body))
            self.end_headers()
            self.wfile.write(body); return
        if not self.check_token(qs):
            self.send_json({"error":"Unauthorized"},401); return
        if parsed.path == "/api/ping":
            self.send_json({"ok":True,"time":time.time()}); return
        if parsed.path == "/api/files":
            files = scan_dir(self.root)
            total_size = sum(f["size"] for f in files.values())
            self.send_json({"files":files,"total":len(files),"total_size":total_size,"total_size_human":human_size(total_size)}); return
        if parsed.path == "/api/download":
            rel = unquote(qs.get("path",[""])[0])
            abs_path = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
            if not abs_path.startswith(self.root) or not os.path.isfile(abs_path):
                self.send_json({"error":"Not found"},404); return
            size = os.path.getsize(abs_path)
            mt = mime(abs_path)
            fname = os.path.basename(abs_path)
            self.send_response(200)
            self.send_header("Content-Type",mt)
            self.send_header("Content-Length",size)
            self.send_header("Content-Disposition",f'attachment; filename="{fname}"')
            self.end_headers()
            try:
                with open(abs_path,"rb") as f:
                    while chunk := f.read(65536): self.wfile.write(chunk)
            except: pass
            return
        self.send_json({"error":"Not found"},404)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if not self.check_token(qs): self.send_json({"error":"Unauthorized"},401); return
        if parsed.path == "/api/upload":
            ct = self.headers.get("Content-Type","")
            length = int(self.headers.get("Content-Length",0))
            body = self.rfile.read(length)
            boundary = ct.split("boundary=")[-1].encode()
            parts = body.split(b"--" + boundary)
            upload_path = self.root
            file_data = file_name = None
            for part in parts:
                if b"Content-Disposition" not in part: continue
                header, _, content = part.partition(b"\r\n\r\n")
                content = content.rstrip(b"\r\n")
                hstr = header.decode(errors="replace")
                if 'name="path"' in hstr:
                    rel = content.decode(errors="replace").strip()
                    ap = os.path.normpath(os.path.join(self.root,rel.lstrip("/")))
                    if ap.startswith(self.root): upload_path=ap
                elif 'name="file"' in hstr:
                    fn=re.search(r'filename="([^"]+)"',hstr)
                    if fn: file_name=fn.group(1); file_data=content
            if file_data is not None and file_name:
                os.makedirs(upload_path,exist_ok=True)
                with open(os.path.join(upload_path,file_name),"wb") as f: f.write(file_data)
                self.send_json({"ok":True,"name":file_name})
            else: self.send_json({"error":"No file"},400)
            return
        self.send_json({"error":"Not found"},404)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=DEFAULT_PORT)
    parser.add_argument("--root",type=str,default=DEFAULT_ROOT)
    args = parser.parse_args()
    Handler.root = os.path.abspath(args.root)
    os.makedirs(Handler.root,exist_ok=True)
    Handler.token = ACCESS_TOKEN
    print(f"\n🔄 FileBeam Sync v2 at http://localhost:{args.port}")
    print(f"📁 Sync folder: {Handler.root}")
    print(f"🔒 Token: {ACCESS_TOKEN}\n")
    try: HTTPServer(("0.0.0.0",args.port),Handler).serve_forever()
    except KeyboardInterrupt: print("\nStopped.")

if __name__=="__main__": main()
