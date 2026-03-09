#!/usr/bin/env python3
"""
FileBeam v2 - Personal File Server
Stunning, interactive UI. Run on PC, access from anywhere.
"""

import os, json, mimetypes, secrets, hashlib, argparse, re
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime

DEFAULT_PORT = 8080
DEFAULT_ROOT = str(Path.home())
ACCESS_TOKEN = secrets.token_urlsafe(16)

def human_size(n):
    for u in ("B","KB","MB","GB","TB"):
        if n < 1024: return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"

def mime(path):
    t, _ = mimetypes.guess_type(path)
    return t or "application/octet-stream"

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FileBeam</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Fira+Code:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#07080f;
  --surface:#0e1018;
  --surface2:#141620;
  --border:#1e2130;
  --border2:#262a3a;
  --accent:#4f8ef7;
  --accent-glow:rgba(79,142,247,0.35);
  --pink:#e06bff;
  --pink-glow:rgba(224,107,255,0.3);
  --green:#3dd68c;
  --yellow:#f5c542;
  --red:#ff5f5f;
  --text:#eef0f8;
  --muted:#5a5f7a;
  --muted2:#3a3f55;
  --r:14px;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html{scroll-behavior:smooth}
body{
  font-family:'Outfit',sans-serif;
  background:var(--bg);
  color:var(--text);
  min-height:100vh;
  overflow-x:hidden;
}

/* ── Ambient background ── */
body::before{
  content:'';
  position:fixed;inset:0;
  background:
    radial-gradient(ellipse 70% 50% at 15% 0%,rgba(79,142,247,.08) 0%,transparent 65%),
    radial-gradient(ellipse 50% 40% at 85% 100%,rgba(224,107,255,.07) 0%,transparent 60%),
    radial-gradient(ellipse 40% 30% at 50% 50%,rgba(61,214,140,.04) 0%,transparent 70%);
  pointer-events:none;z-index:0;
}

/* ── Scrollbar ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:99px}

/* ── Header ── */
header{
  position:sticky;top:0;z-index:100;
  background:rgba(7,8,15,.85);
  backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);
  padding:0 20px;
  height:62px;
  display:flex;align-items:center;justify-content:space-between;gap:12px;
}
.logo{display:flex;align-items:center;gap:11px;text-decoration:none;color:inherit}
.logo-mark{
  position:relative;
  width:36px;height:36px;
  border-radius:10px;
  background:linear-gradient(135deg,var(--accent),var(--pink));
  display:flex;align-items:center;justify-content:center;
  font-size:17px;
  box-shadow:0 0 20px var(--accent-glow);
  transition:box-shadow .3s;
}
.logo-mark:hover{box-shadow:0 0 30px var(--accent-glow),0 0 50px var(--pink-glow)}
.logo-text{font-size:1.2rem;font-weight:800;letter-spacing:-.03em;
  background:linear-gradient(90deg,var(--text) 60%,var(--accent));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo-ver{font-size:.62rem;font-family:'Fira Code',monospace;color:var(--muted);margin-top:-2px}
.header-right{display:flex;align-items:center;gap:8px}

/* ── Pill badge ── */
.pill{
  display:inline-flex;align-items:center;gap:5px;
  padding:5px 11px;border-radius:99px;font-size:.72rem;font-weight:600;
  border:1px solid;white-space:nowrap;
}
.pill-blue{background:rgba(79,142,247,.1);border-color:rgba(79,142,247,.25);color:var(--accent)}
.pill-green{background:rgba(61,214,140,.1);border-color:rgba(61,214,140,.25);color:var(--green)}
.pill-red{background:rgba(255,95,95,.1);border-color:rgba(255,95,95,.25);color:var(--red)}
.dot{width:6px;height:6px;border-radius:50%;background:currentColor;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* ── Buttons ── */
.btn{
  display:inline-flex;align-items:center;gap:7px;
  padding:9px 18px;border-radius:10px;border:none;
  font-family:'Outfit',sans-serif;font-size:.85rem;font-weight:600;
  cursor:pointer;transition:all .2s;white-space:nowrap;
}
.btn-glow{
  background:linear-gradient(135deg,var(--accent),#3d6fd4);
  color:#fff;
  box-shadow:0 2px 12px rgba(79,142,247,.35);
}
.btn-glow:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(79,142,247,.5)}
.btn-glow:active{transform:translateY(0)}
.btn-ghost{
  background:var(--surface2);border:1px solid var(--border2);color:var(--text);
}
.btn-ghost:hover{border-color:var(--accent);color:var(--accent)}
.btn-sm{padding:6px 12px;font-size:.75rem;border-radius:8px}
.btn-icon{width:34px;height:34px;padding:0;justify-content:center;border-radius:9px}

/* ── Main layout ── */
.wrap{position:relative;z-index:1;max-width:980px;margin:0 auto;padding:0 16px}

/* ── Breadcrumb ── */
.breadcrumb-bar{
  padding:14px 0 0;
  display:flex;align-items:center;gap:6px;flex-wrap:wrap;
  font-family:'Fira Code',monospace;font-size:.75rem;
}
.bc-seg{
  display:flex;align-items:center;gap:6px;
  color:var(--muted);cursor:pointer;transition:color .18s;
  padding:3px 8px;border-radius:6px;
}
.bc-seg:hover{color:var(--accent);background:rgba(79,142,247,.08)}
.bc-sep{color:var(--muted2);font-size:.9em}
.bc-cur{color:var(--text);font-weight:500}

/* ── Toolbar ── */
.toolbar{
  display:flex;gap:10px;padding:14px 0 10px;flex-wrap:wrap;align-items:center;
}
.search-wrap{
  flex:1;min-width:200px;position:relative;
}
.search-icon{
  position:absolute;left:13px;top:50%;transform:translateY(-50%);
  color:var(--muted);font-size:.9rem;pointer-events:none;
}
.search-input{
  width:100%;
  background:var(--surface2);
  border:1px solid var(--border2);
  border-radius:11px;
  padding:10px 14px 10px 38px;
  color:var(--text);
  font-family:'Outfit',sans-serif;font-size:.88rem;
  outline:none;transition:all .2s;
}
.search-input:focus{border-color:var(--accent);background:var(--surface);box-shadow:0 0 0 3px rgba(79,142,247,.12)}
.search-input::placeholder{color:var(--muted)}
.view-toggle{display:flex;gap:3px;background:var(--surface2);border:1px solid var(--border2);border-radius:10px;padding:3px}
.view-btn{
  width:32px;height:32px;display:flex;align-items:center;justify-content:center;
  border-radius:7px;border:none;background:transparent;color:var(--muted);
  cursor:pointer;transition:all .18s;font-size:.9rem;
}
.view-btn.active{background:var(--border2);color:var(--text)}

/* ── Sort bar ── */
.sort-bar{
  display:flex;gap:4px;padding-bottom:8px;border-bottom:1px solid var(--border);
  font-size:.72rem;font-weight:600;color:var(--muted);letter-spacing:.04em;
  text-transform:uppercase;
}
.sort-btn{
  background:none;border:none;color:var(--muted);font-family:'Outfit',sans-serif;
  font-size:.72rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;
  cursor:pointer;padding:4px 8px;border-radius:6px;transition:all .18s;
  display:flex;align-items:center;gap:4px;
}
.sort-btn:hover{color:var(--text);background:var(--surface2)}
.sort-btn.active{color:var(--accent)}
.sort-name{flex:1}
.sort-size{width:90px;text-align:right}
.sort-date{width:130px;text-align:right}
.sort-actions{width:100px}

/* ── File grid / list ── */
.file-list{display:flex;flex-direction:column;gap:2px;padding:6px 0 60px}
.file-grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
  gap:10px;padding:6px 0 60px;
}

/* List item */
.file-row{
  display:flex;align-items:center;gap:12px;
  padding:10px 12px;border-radius:11px;
  border:1px solid transparent;
  text-decoration:none;color:var(--text);
  transition:all .18s;cursor:pointer;
  position:relative;overflow:hidden;
}
.file-row::before{
  content:'';position:absolute;inset:0;
  background:linear-gradient(90deg,rgba(79,142,247,.05),transparent);
  opacity:0;transition:opacity .2s;border-radius:11px;
}
.file-row:hover{background:var(--surface2);border-color:var(--border2)}
.file-row:hover::before{opacity:1}
.file-row.dir:hover{border-color:rgba(79,142,247,.3)}
.file-row.selected{background:rgba(79,142,247,.08);border-color:rgba(79,142,247,.3)}

/* Grid item */
.file-card{
  background:var(--surface2);
  border:1px solid var(--border2);
  border-radius:13px;
  padding:16px 12px;
  display:flex;flex-direction:column;align-items:center;gap:10px;
  cursor:pointer;transition:all .2s;
  text-align:center;text-decoration:none;color:var(--text);
  position:relative;overflow:hidden;
}
.file-card:hover{
  border-color:rgba(79,142,247,.4);
  transform:translateY(-2px);
  box-shadow:0 8px 24px rgba(0,0,0,.3);
}
.file-card .card-ico{font-size:2.2rem;line-height:1}
.file-card .card-name{font-size:.78rem;font-weight:600;width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-card .card-size{font-size:.68rem;font-family:'Fira Code',monospace;color:var(--muted)}
.file-card .card-actions{
  position:absolute;inset:0;background:rgba(7,8,15,.85);
  display:flex;align-items:center;justify-content:center;gap:8px;
  opacity:0;transition:opacity .2s;border-radius:13px;
}
.file-card:hover .card-actions{opacity:1}

/* File icon blob */
.f-ico{
  width:40px;height:40px;border-radius:10px;
  display:flex;align-items:center;justify-content:center;
  font-size:19px;flex-shrink:0;
  transition:transform .2s;
}
.file-row:hover .f-ico{transform:scale(1.08)}
.ico-dir{background:linear-gradient(135deg,rgba(79,142,247,.2),rgba(79,142,247,.05));border:1px solid rgba(79,142,247,.2)}
.ico-vid{background:linear-gradient(135deg,rgba(224,107,255,.2),rgba(224,107,255,.05));border:1px solid rgba(224,107,255,.2)}
.ico-aud{background:linear-gradient(135deg,rgba(61,214,140,.2),rgba(61,214,140,.05));border:1px solid rgba(61,214,140,.2)}
.ico-img{background:linear-gradient(135deg,rgba(245,197,66,.2),rgba(245,197,66,.05));border:1px solid rgba(245,197,66,.2)}
.ico-txt{background:linear-gradient(135deg,rgba(96,200,255,.2),rgba(96,200,255,.05));border:1px solid rgba(96,200,255,.2)}
.ico-zip{background:linear-gradient(135deg,rgba(255,150,80,.2),rgba(255,150,80,.05));border:1px solid rgba(255,150,80,.2)}
.ico-gen{background:linear-gradient(135deg,rgba(90,95,122,.2),rgba(90,95,122,.05));border:1px solid rgba(90,95,122,.2)}

.f-name{flex:1;font-size:.9rem;font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.f-size{width:90px;text-align:right;font-family:'Fira Code',monospace;font-size:.74rem;color:var(--muted);flex-shrink:0}
.f-date{width:130px;text-align:right;font-family:'Fira Code',monospace;font-size:.72rem;color:var(--muted);flex-shrink:0}
.f-actions{
  width:100px;display:flex;justify-content:flex-end;gap:5px;
  opacity:0;transition:opacity .18s;flex-shrink:0;
}
.file-row:hover .f-actions{opacity:1}
.act-btn{
  width:28px;height:28px;border-radius:7px;border:1px solid var(--border2);
  background:var(--surface);color:var(--muted);
  display:flex;align-items:center;justify-content:center;font-size:.8rem;
  cursor:pointer;transition:all .18s;text-decoration:none;
}
.act-btn:hover{border-color:var(--accent);color:var(--accent);background:rgba(79,142,247,.1)}

/* ── Empty state ── */
.empty{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:60px 20px;gap:12px;color:var(--muted);
}
.empty-ico{font-size:3rem;opacity:.4}
.empty-txt{font-size:.88rem}

/* ── Upload zone ── */
.drop-overlay{
  position:fixed;inset:0;z-index:200;
  background:rgba(7,8,15,.9);
  backdrop-filter:blur(8px);
  display:flex;align-items:center;justify-content:center;
  opacity:0;pointer-events:none;transition:opacity .25s;
}
.drop-overlay.active{opacity:1;pointer-events:all}
.drop-inner{
  border:2px dashed var(--accent);
  border-radius:20px;padding:60px 80px;
  text-align:center;
  animation:dropPulse 1.5s ease infinite;
}
@keyframes dropPulse{0%,100%{box-shadow:0 0 0 0 var(--accent-glow)}50%{box-shadow:0 0 40px 10px var(--accent-glow)}}
.drop-inner h2{font-size:1.6rem;font-weight:800;margin-bottom:8px}
.drop-inner p{color:var(--muted);font-size:.88rem}

/* ── Upload modal ── */
.modal-bg{
  position:fixed;inset:0;z-index:300;
  background:rgba(0,0,0,.75);backdrop-filter:blur(10px);
  display:flex;align-items:center;justify-content:center;padding:20px;
  opacity:0;pointer-events:none;transition:opacity .25s;
}
.modal-bg.open{opacity:1;pointer-events:all}
.modal{
  background:var(--surface);
  border:1px solid var(--border2);
  border-radius:18px;
  width:100%;max-width:420px;
  overflow:hidden;
  transform:translateY(20px) scale(.97);
  transition:transform .3s;
}
.modal-bg.open .modal{transform:none}
.modal-head{
  padding:18px 20px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
}
.modal-title{font-size:1rem;font-weight:700}
.modal-close{
  width:28px;height:28px;border-radius:8px;border:none;
  background:rgba(255,95,95,.12);color:var(--red);
  cursor:pointer;font-size:1rem;display:flex;align-items:center;justify-content:center;
  transition:background .18s;
}
.modal-close:hover{background:rgba(255,95,95,.25)}
.modal-body{padding:20px;display:flex;flex-direction:column;gap:14px}
.upload-zone{
  border:2px dashed var(--border2);border-radius:13px;
  padding:30px 20px;text-align:center;cursor:pointer;
  transition:all .2s;
}
.upload-zone:hover,.upload-zone.drag{border-color:var(--accent);background:rgba(79,142,247,.05)}
.upload-zone-ico{font-size:2.4rem;margin-bottom:8px}
.upload-zone p{font-size:.83rem;color:var(--muted);margin-top:4px}
.upload-zone strong{color:var(--accent)}

/* Progress */
.prog-wrap{display:none;flex-direction:column;gap:6px}
.prog-track{height:5px;background:var(--border2);border-radius:99px;overflow:hidden}
.prog-fill{
  height:100%;border-radius:99px;
  background:linear-gradient(90deg,var(--accent),var(--pink));
  width:0%;transition:width .3s;
  box-shadow:0 0 10px rgba(79,142,247,.5);
}
.prog-label{font-family:'Fira Code',monospace;font-size:.73rem;color:var(--muted);text-align:center}

/* ── Media viewer ── */
.viewer-bg{
  position:fixed;inset:0;z-index:400;
  background:rgba(0,0,0,.92);backdrop-filter:blur(12px);
  display:flex;align-items:center;justify-content:center;padding:20px;
  opacity:0;pointer-events:none;transition:opacity .25s;
}
.viewer-bg.open{opacity:1;pointer-events:all}
.viewer{
  background:var(--surface);border:1px solid var(--border2);
  border-radius:18px;width:100%;max-width:920px;
  max-height:90vh;display:flex;flex-direction:column;overflow:hidden;
  transform:scale(.95);transition:transform .3s;
}
.viewer-bg.open .viewer{transform:none}
.viewer-head{
  padding:14px 18px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:12px;
}
.viewer-name{flex:1;font-size:.9rem;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.viewer-body{flex:1;overflow:auto;display:flex;align-items:center;justify-content:center;min-height:0;background:var(--bg)}
.viewer-body video,.viewer-body audio{width:100%;outline:none}
.viewer-body img{max-width:100%;max-height:75vh;object-fit:contain;display:block}
.viewer-body pre{
  width:100%;padding:24px;
  font-family:'Fira Code',monospace;font-size:.8rem;line-height:1.7;
  color:var(--text);white-space:pre-wrap;word-break:break-all;
}

/* ── Toast ── */
.toast-stack{
  position:fixed;bottom:24px;right:24px;z-index:999;
  display:flex;flex-direction:column;gap:8px;align-items:flex-end;
}
.toast{
  display:flex;align-items:center;gap:10px;
  padding:11px 16px;border-radius:12px;
  font-size:.83rem;font-weight:600;
  border:1px solid;
  transform:translateX(120%);transition:transform .3s cubic-bezier(.34,1.56,.64,1);
  max-width:320px;
  backdrop-filter:blur(10px);
}
.toast.show{transform:none}
.toast.info{background:rgba(79,142,247,.15);border-color:rgba(79,142,247,.3);color:var(--accent)}
.toast.success{background:rgba(61,214,140,.15);border-color:rgba(61,214,140,.3);color:var(--green)}
.toast.error{background:rgba(255,95,95,.15);border-color:rgba(255,95,95,.3);color:var(--red)}

/* ── Context menu ── */
.ctx-menu{
  position:fixed;z-index:500;
  background:var(--surface2);border:1px solid var(--border2);
  border-radius:12px;padding:5px;min-width:160px;
  box-shadow:0 8px 32px rgba(0,0,0,.4);
  opacity:0;pointer-events:none;transform:scale(.95) translateY(-4px);
  transition:all .18s;
}
.ctx-menu.show{opacity:1;pointer-events:all;transform:none}
.ctx-item{
  display:flex;align-items:center;gap:9px;
  padding:9px 12px;border-radius:8px;font-size:.83rem;font-weight:500;
  cursor:pointer;transition:background .15s;color:var(--text);
}
.ctx-item:hover{background:var(--border2)}
.ctx-item.danger{color:var(--red)}
.ctx-item.danger:hover{background:rgba(255,95,95,.1)}
.ctx-sep{height:1px;background:var(--border);margin:4px 0}

/* ── Responsive ── */
@media(max-width:640px){
  .f-date,.sort-date{display:none}
  .f-size,.sort-size{display:none}
  .f-actions{opacity:1}
  .file-grid{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}
}
@media(max-width:400px){
  .file-grid{grid-template-columns:repeat(2,1fr)}
}

/* ── Animations ── */
@keyframes fadeSlideIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.file-row,.file-card{animation:fadeSlideIn .25s ease both}

/* stagger */
.file-row:nth-child(1),.file-card:nth-child(1){animation-delay:.03s}
.file-row:nth-child(2),.file-card:nth-child(2){animation-delay:.06s}
.file-row:nth-child(3),.file-card:nth-child(3){animation-delay:.09s}
.file-row:nth-child(4),.file-card:nth-child(4){animation-delay:.12s}
.file-row:nth-child(5),.file-card:nth-child(5){animation-delay:.15s}
.file-row:nth-child(6),.file-card:nth-child(6){animation-delay:.18s}
.file-row:nth-child(n+7),.file-card:nth-child(n+7){animation-delay:.2s}
</style>
</head>
<body>

<!-- Header -->
<header>
  <a class="logo" href="#" onclick="navigate('/');return false">
    <div class="logo-mark">⚡</div>
    <div>
      <div class="logo-text">FileBeam</div>
      <div class="logo-ver">v2.0 · personal server</div>
    </div>
  </a>
  <div class="header-right">
    <span class="pill pill-green" id="connPill"><span class="dot"></span>Online</span>
    <button class="btn btn-glow btn-sm" onclick="openUpload()">⬆ Upload</button>
  </div>
</header>

<div class="wrap">
  <!-- Breadcrumb -->
  <div class="breadcrumb-bar" id="breadcrumb"></div>

  <!-- Toolbar -->
  <div class="toolbar">
    <div class="search-wrap">
      <span class="search-icon">🔍</span>
      <input class="search-input" id="searchInput" placeholder="Search files and folders…" oninput="filterFiles()" autocomplete="off"/>
    </div>
    <div class="view-toggle">
      <button class="view-btn active" id="listBtn" onclick="setView('list')" title="List view">☰</button>
      <button class="view-btn" id="gridBtn" onclick="setView('grid')" title="Grid view">⊞</button>
    </div>
    <button class="btn btn-ghost btn-sm" onclick="loadDir(currentPath)">↺</button>
  </div>

  <!-- Sort bar (list view only) -->
  <div class="sort-bar" id="sortBar">
    <button class="sort-btn sort-name active" onclick="sortBy('name')" id="sort-name">Name <span id="sort-name-ico">↑</span></button>
    <button class="sort-btn sort-size" onclick="sortBy('size')" id="sort-size">Size</button>
    <button class="sort-btn sort-date" onclick="sortBy('date')" id="sort-date">Modified</button>
    <div class="sort-actions"></div>
  </div>

  <!-- File list -->
  <div id="fileContainer" class="file-list"></div>
</div>

<!-- Drop overlay -->
<div class="drop-overlay" id="dropOverlay">
  <div class="drop-inner">
    <div style="font-size:3rem;margin-bottom:12px">📂</div>
    <h2>Drop to Upload</h2>
    <p>Release to upload files to current folder</p>
  </div>
</div>

<!-- Upload modal -->
<div class="modal-bg" id="uploadModal" onclick="closeUpload(event)">
  <div class="modal">
    <div class="modal-head">
      <span class="modal-title">Upload Files</span>
      <button class="modal-close" onclick="closeUpload()">✕</button>
    </div>
    <div class="modal-body">
      <div class="upload-zone" id="uploadZone"
           ondragover="uzDragOver(event)" ondragleave="uzDragLeave()"
           ondrop="uzDrop(event)" onclick="document.getElementById('fileInput').click()">
        <div class="upload-zone-ico">📤</div>
        <div style="font-size:.9rem;font-weight:700">Drag files here</div>
        <p>or <strong>tap to browse</strong> your device</p>
      </div>
      <input type="file" id="fileInput" multiple style="display:none" onchange="uploadFiles(this.files)"/>
      <div class="prog-wrap" id="progWrap" style="display:flex">
        <div class="prog-track"><div class="prog-fill" id="progFill"></div></div>
        <div class="prog-label" id="progLabel">Ready</div>
      </div>
    </div>
  </div>
</div>

<!-- Media viewer -->
<div class="viewer-bg" id="viewerBg" onclick="closeViewer(event)">
  <div class="viewer">
    <div class="viewer-head">
      <span class="viewer-name" id="viewerName"></span>
      <a id="viewerDl" class="btn btn-ghost btn-sm" download>⬇ Save</a>
      <button class="modal-close" onclick="closeViewer()">✕</button>
    </div>
    <div class="viewer-body" id="viewerBody"></div>
  </div>
</div>

<!-- Context menu -->
<div class="ctx-menu" id="ctxMenu">
  <div class="ctx-item" id="ctxOpen">📂 Open</div>
  <div class="ctx-item" id="ctxView">👁 Preview</div>
  <div class="ctx-sep"></div>
  <div class="ctx-item" id="ctxDownload">⬇ Download</div>
</div>

<!-- Toast stack -->
<div class="toast-stack" id="toastStack"></div>

<script>
const TOKEN = "{{TOKEN}}";
const A = p => `/api${p}?token=${TOKEN}`;
let currentPath = "/";
let allFiles = [];
let viewMode = "list";
let sortKey = "name";
let sortAsc = true;
let ctxFile = null;

// ── Init ──────────────────────────────────────────────────────────────────
function init(){
  const hash = decodeURIComponent(location.hash.slice(1)) || "/";
  navigate(hash, false);
  setupDragDrop();
  document.addEventListener("click", () => hideCtx());
  document.addEventListener("keydown", e => { if(e.key==="Escape"){closeViewer();closeUpload();} });
}

// ── Navigation ────────────────────────────────────────────────────────────
async function navigate(path, push=true){
  currentPath = path;
  if(push) history.pushState({},"",'#'+encodeURIComponent(path));
  renderBreadcrumb(path);
  await loadDir(path);
}
window.addEventListener("popstate", ()=>{
  const hash = decodeURIComponent(location.hash.slice(1)) || "/";
  navigate(hash, false);
});

function renderBreadcrumb(path){
  const parts = path.split("/").filter(Boolean);
  let html = `<span class="bc-seg" onclick="navigate('/')">🏠 Home</span>`;
  let acc = "";
  parts.forEach((p,i)=>{
    acc += "/" + p;
    html += `<span class="bc-sep">/</span>`;
    const snap = acc;
    if(i < parts.length-1)
      html += `<span class="bc-seg" onclick="navigate('${snap}')">${p}</span>`;
    else
      html += `<span class="bc-seg bc-cur">${p}</span>`;
  });
  document.getElementById("breadcrumb").innerHTML = html;
}

// ── Load directory ────────────────────────────────────────────────────────
async function loadDir(path){
  const container = document.getElementById("fileContainer");
  container.innerHTML = `<div class="empty"><div class="empty-ico">⏳</div><div class="empty-txt">Loading…</div></div>`;
  try{
    const r = await fetch(A(`/list?path=${encodeURIComponent(path)}`));
    const d = await r.json();
    if(d.error){ toast(d.error,"error"); return; }
    allFiles = d.items;
    renderFiles(allFiles);
  } catch(e){ toast("Failed to load directory","error"); }
}

function filterFiles(){
  const q = document.getElementById("searchInput").value.toLowerCase();
  renderFiles(allFiles.filter(f=>f.name.toLowerCase().includes(q)));
}

// ── Sort ──────────────────────────────────────────────────────────────────
function sortBy(key){
  if(sortKey===key) sortAsc=!sortAsc;
  else { sortKey=key; sortAsc=true; }
  document.querySelectorAll(".sort-btn").forEach(b=>b.classList.remove("active"));
  document.getElementById("sort-"+key).classList.add("active");
  document.getElementById("sort-"+key+"-ico") && (document.getElementById("sort-"+key+"-ico").textContent = sortAsc?"↑":"↓");
  renderFiles(allFiles);
}

function sorted(files){
  return [...files].sort((a,b)=>{
    if(a.is_dir !== b.is_dir) return a.is_dir?-1:1;
    let va,vb;
    if(sortKey==="name"){ va=a.name.toLowerCase(); vb=b.name.toLowerCase(); }
    else if(sortKey==="size"){ va=a.size||0; vb=b.size||0; }
    else { va=a.mtime||0; vb=b.mtime||0; }
    return sortAsc ? (va<vb?-1:va>vb?1:0) : (va>vb?-1:va<vb?1:0);
  });
}

// ── View mode ─────────────────────────────────────────────────────────────
function setView(mode){
  viewMode = mode;
  document.getElementById("listBtn").classList.toggle("active", mode==="list");
  document.getElementById("gridBtn").classList.toggle("active", mode==="grid");
  document.getElementById("sortBar").style.display = mode==="list"?"flex":"none";
  renderFiles(allFiles);
}

// ── Render ────────────────────────────────────────────────────────────────
function renderFiles(files){
  const sorted_files = sorted(files);
  const container = document.getElementById("fileContainer");
  container.className = viewMode==="grid" ? "file-grid" : "file-list";
  if(!sorted_files.length){
    container.innerHTML = `<div class="empty"><div class="empty-ico">🌌</div><div class="empty-txt">Nothing here</div></div>`;
    return;
  }
  if(viewMode==="list") container.innerHTML = sorted_files.map(listRow).join("");
  else container.innerHTML = sorted_files.map(gridCard).join("");
}

const icoMap = m=>{
  if(!m) return ["📁","ico-dir"];
  if(m.startsWith("video/")) return ["🎬","ico-vid"];
  if(m.startsWith("audio/")) return ["🎵","ico-aud"];
  if(m.startsWith("image/")) return ["🖼","ico-img"];
  if(m.includes("pdf")) return ["📕","ico-txt"];
  if(m.startsWith("text/") || m.includes("json")) return ["📄","ico-txt"];
  if(m.includes("zip")||m.includes("rar")||m.includes("tar")) return ["🗜","ico-zip"];
  return ["📎","ico-gen"];
};

function listRow(f){
  const fp = (currentPath.replace(/\/$/,"") + "/" + f.name);
  const [ico,cls] = f.is_dir ? ["📁","ico-dir"] : icoMap(f.mime);
  const canPreview = !f.is_dir && f.mime && (f.mime.startsWith("video/")||f.mime.startsWith("audio/")||f.mime.startsWith("image/")||f.mime.startsWith("text/"));
  return `<div class="file-row ${f.is_dir?'dir':''}"
    onclick="handleClick('${esc(fp)}','${esc(f.name)}','${f.mime||''}',${f.is_dir})"
    oncontextmenu="showCtx(event,'${esc(fp)}','${esc(f.name)}','${f.mime||''}',${f.is_dir})">
    <div class="f-ico ${cls}">${ico}</div>
    <div class="f-name">${esc(f.name)}</div>
    <div class="f-size">${f.is_dir?'—':f.size_human}</div>
    <div class="f-date">${f.modified}</div>
    <div class="f-actions" onclick="event.stopPropagation()">
      ${canPreview?`<button class="act-btn" title="Preview" onclick="openViewer('${esc(fp)}','${esc(f.name)}','${f.mime||''}')">👁</button>`:''}
      ${!f.is_dir?`<a class="act-btn" title="Download" href="${A('/download?path='+encodeURIComponent(fp))}" download="${esc(f.name)}">⬇</a>`:''}
    </div>
  </div>`;
}

function gridCard(f){
  const fp = (currentPath.replace(/\/$/,"") + "/" + f.name);
  const [ico] = f.is_dir ? ["📁"] : icoMap(f.mime);
  const canPreview = !f.is_dir && f.mime && (f.mime.startsWith("video/")||f.mime.startsWith("audio/")||f.mime.startsWith("image/")||f.mime.startsWith("text/"));
  return `<div class="file-card"
    onclick="handleClick('${esc(fp)}','${esc(f.name)}','${f.mime||''}',${f.is_dir})"
    oncontextmenu="showCtx(event,'${esc(fp)}','${esc(f.name)}','${f.mime||''}',${f.is_dir})">
    <div class="card-ico">${ico}</div>
    <div class="card-name" title="${esc(f.name)}">${esc(f.name)}</div>
    <div class="card-size">${f.is_dir?'folder':f.size_human}</div>
    <div class="card-actions" onclick="event.stopPropagation()">
      ${canPreview?`<button class="act-btn btn-ghost" onclick="openViewer('${esc(fp)}','${esc(f.name)}','${f.mime||''}')">👁</button>`:''}
      ${!f.is_dir?`<a class="act-btn btn-ghost" href="${A('/download?path='+encodeURIComponent(fp))}" download="${esc(f.name)}">⬇</a>`:''}
    </div>
  </div>`;
}

function handleClick(fp, name, mime, isDir){
  if(isDir){ navigate(fp); return; }
  const previewable = mime && (mime.startsWith("video/")||mime.startsWith("audio/")||mime.startsWith("image/")||mime.startsWith("text/"));
  if(previewable) openViewer(fp, name, mime);
  else window.location.href = A('/download?path='+encodeURIComponent(fp));
}

// ── Context menu ──────────────────────────────────────────────────────────
function showCtx(e, fp, name, mime, isDir){
  e.preventDefault(); e.stopPropagation();
  ctxFile = {fp,name,mime,isDir};
  const m = document.getElementById("ctxMenu");
  document.getElementById("ctxOpen").style.display = isDir?"flex":"none";
  document.getElementById("ctxView").style.display = (!isDir && mime && (mime.startsWith("video/")||mime.startsWith("audio/")||mime.startsWith("image/")||mime.startsWith("text/"))) ? "flex":"none";
  document.getElementById("ctxDownload").style.display = isDir?"none":"flex";
  document.getElementById("ctxOpen").onclick = ()=>{ if(isDir) navigate(fp); hideCtx(); };
  document.getElementById("ctxView").onclick = ()=>{ openViewer(fp,name,mime); hideCtx(); };
  document.getElementById("ctxDownload").onclick = ()=>{ window.location.href=A('/download?path='+encodeURIComponent(fp)); hideCtx(); };
  const x = Math.min(e.clientX, window.innerWidth-170);
  const y = Math.min(e.clientY, window.innerHeight-140);
  m.style.left=x+"px"; m.style.top=y+"px";
  m.classList.add("show");
}
function hideCtx(){ document.getElementById("ctxMenu").classList.remove("show"); }

// ── Viewer ────────────────────────────────────────────────────────────────
async function openViewer(fp, name, mime){
  const url = A('/download?path='+encodeURIComponent(fp));
  document.getElementById("viewerName").textContent = name;
  document.getElementById("viewerDl").href = url;
  document.getElementById("viewerDl").download = name;
  const body = document.getElementById("viewerBody");
  if(mime.startsWith("video/")) body.innerHTML=`<video controls autoplay src="${url}"></video>`;
  else if(mime.startsWith("audio/")) body.innerHTML=`<audio controls autoplay src="${url}" style="width:100%;padding:24px"></audio>`;
  else if(mime.startsWith("image/")) body.innerHTML=`<img src="${url}" alt="${esc(name)}"/>`;
  else { body.innerHTML=`<pre>Loading…</pre>`; const r=await fetch(url); body.innerHTML=`<pre>${escHtml(await r.text())}</pre>`; }
  document.getElementById("viewerBg").classList.add("open");
}
function closeViewer(e){
  if(e && e.target!==document.getElementById("viewerBg")) return;
  document.getElementById("viewerBg").classList.remove("open");
  document.getElementById("viewerBody").innerHTML="";
}

// ── Upload ────────────────────────────────────────────────────────────────
function openUpload(){ document.getElementById("uploadModal").classList.add("open"); }
function closeUpload(e){
  if(e && e.target!==document.getElementById("uploadModal")) return;
  document.getElementById("uploadModal").classList.remove("open");
}
function uzDragOver(e){e.preventDefault();document.getElementById("uploadZone").classList.add("drag")}
function uzDragLeave(){document.getElementById("uploadZone").classList.remove("drag")}
function uzDrop(e){e.preventDefault();uzDragLeave();uploadFiles(e.dataTransfer.files)}

async function uploadFiles(files){
  if(!files.length) return;
  const pw=document.getElementById("progWrap"), pf=document.getElementById("progFill"), pl=document.getElementById("progLabel");
  pw.style.display="flex";
  for(let i=0;i<files.length;i++){
    const file=files[i];
    pl.textContent=`Uploading ${file.name} (${i+1}/${files.length})…`;
    const form=new FormData();
    form.append("file",file); form.append("path",currentPath);
    await new Promise(res=>{
      const xhr=new XMLHttpRequest();
      xhr.upload.onprogress=ev=>{ pf.style.width=Math.round((i+ev.loaded/ev.total)/files.length*100)+"%"; };
      xhr.onload=res;
      xhr.open("POST",A("/upload")); xhr.send(form);
    });
  }
  pf.style.width="100%";
  pl.textContent=`✅ ${files.length} file(s) uploaded!`;
  toast(`${files.length} file(s) uploaded successfully`,"success");
  setTimeout(()=>{ pw.style.display="none"; pf.style.width="0%"; pl.textContent="Ready"; },2500);
  loadDir(currentPath);
}

// ── Global drag-drop ──────────────────────────────────────────────────────
function setupDragDrop(){
  let dragCount=0;
  document.addEventListener("dragenter",e=>{
    if(e.dataTransfer.types.includes("Files")){ dragCount++; document.getElementById("dropOverlay").classList.add("active"); }
  });
  document.addEventListener("dragleave",()=>{ dragCount--; if(dragCount<=0){dragCount=0;document.getElementById("dropOverlay").classList.remove("active");} });
  document.addEventListener("dragover",e=>e.preventDefault());
  document.addEventListener("drop",e=>{
    e.preventDefault(); dragCount=0;
    document.getElementById("dropOverlay").classList.remove("active");
    if(e.dataTransfer.files.length){ openUpload(); uploadFiles(e.dataTransfer.files); }
  });
}

// ── Toast ─────────────────────────────────────────────────────────────────
function toast(msg, type="info"){
  const stack=document.getElementById("toastStack");
  const el=document.createElement("div");
  el.className=`toast ${type}`;
  el.textContent=msg;
  stack.appendChild(el);
  requestAnimationFrame(()=>{ el.classList.add("show"); });
  setTimeout(()=>{ el.classList.remove("show"); setTimeout(()=>el.remove(),400); },3000);
}

// ── Helpers ───────────────────────────────────────────────────────────────
function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function escHtml(s){ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

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
            self.wfile.write(body)
            return
        if not self.check_token(qs):
            self.send_json({"error":"Unauthorized"},401); return
        if parsed.path == "/api/list":
            rel = unquote(qs.get("path",["/"])[0])
            abs_path = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
            if not abs_path.startswith(self.root):
                self.send_json({"error":"Access denied"}); return
            if not os.path.isdir(abs_path):
                self.send_json({"error":"Not a directory"}); return
            items = []
            try:
                for name in sorted(os.listdir(abs_path), key=lambda x:(not os.path.isdir(os.path.join(abs_path,x)),x.lower())):
                    fp = os.path.join(abs_path, name)
                    try:
                        stat = os.stat(fp)
                        is_dir = os.path.isdir(fp)
                        items.append({
                            "name":name,"is_dir":is_dir,
                            "size":stat.st_size if not is_dir else 0,
                            "size_human":human_size(stat.st_size) if not is_dir else "—",
                            "mtime":stat.st_mtime,
                            "modified":datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y"),
                            "mime":mime(fp) if not is_dir else "",
                        })
                    except: pass
            except PermissionError:
                self.send_json({"error":"Permission denied"}); return
            self.send_json({"items":items}); return
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
            self.send_header("Accept-Ranges","bytes")
            self.send_header("Content-Disposition",f'inline; filename="{fname}"')
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
        if not self.check_token(qs):
            self.send_json({"error":"Unauthorized"},401); return
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
                header_str = header.decode(errors="replace")
                if 'name="path"' in header_str:
                    rel = content.decode(errors="replace").strip()
                    ap = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
                    if ap.startswith(self.root): upload_path = ap
                elif 'name="file"' in header_str:
                    fn = re.search(r'filename="([^"]+)"', header_str)
                    if fn: file_name=fn.group(1); file_data=content
            if file_data is not None and file_name:
                os.makedirs(upload_path, exist_ok=True)
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
    Handler.token = ACCESS_TOKEN
    print(f"\n⚡ FileBeam v2 running at http://localhost:{args.port}")
    print(f"📁 Sharing: {Handler.root}")
    print(f"🔒 Token: {ACCESS_TOKEN}\n")
    try: HTTPServer(("0.0.0.0",args.port),Handler).serve_forever()
    except KeyboardInterrupt: print("\nStopped.")

if __name__=="__main__": main()
