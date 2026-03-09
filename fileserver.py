#!/usr/bin/env python3
"""
FileBeam - Personal File Server
Run this on your PC to access files from anywhere via browser.
"""

import os
import json
import mimetypes
import threading
import secrets
import hashlib
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
import argparse

# ── Config ──────────────────────────────────────────────────────────────────
DEFAULT_PORT = 8080
DEFAULT_ROOT  = str(Path.home())   # Change to any folder you want to share
ACCESS_TOKEN  = secrets.token_urlsafe(16)  # Auto-generated secure token

# ── Helpers ──────────────────────────────────────────────────────────────────
def human_size(n):
    for unit in ("B","KB","MB","GB","TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def mime(path):
    t, _ = mimetypes.guess_type(path)
    return t or "application/octet-stream"

def is_video(path):
    return mime(path).startswith("video/")

def is_audio(path):
    return mime(path).startswith("audio/")

def is_image(path):
    return mime(path).startswith("image/")

def is_text(path):
    return mime(path).startswith("text/") or path.endswith((".md",".json",".py",".js",".ts",".html",".css",".yaml",".yml",".toml",".sh",".bat"))

# ── HTML Template ─────────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FileBeam</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400&display=swap" rel="stylesheet"/>
<style>
:root {
  --bg: #0a0a0f;
  --surface: #12121a;
  --border: #1e1e2e;
  --accent: #7c6aff;
  --accent2: #ff6ab0;
  --text: #e8e8f0;
  --muted: #6b6b80;
  --green: #4ade80;
  --yellow: #fbbf24;
  --red: #f87171;
  --blue: #60a5fa;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Syne', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  overflow-x: hidden;
}
body::before {
  content: '';
  position: fixed; inset: 0;
  background: radial-gradient(ellipse 80% 50% at 20% -10%, rgba(124,106,255,.15) 0%, transparent 60%),
              radial-gradient(ellipse 60% 40% at 80% 110%, rgba(255,106,176,.10) 0%, transparent 60%);
  pointer-events: none; z-index: 0;
}
.wrap { position: relative; z-index: 1; max-width: 960px; margin: 0 auto; padding: 0 16px; }

/* Header */
header {
  border-bottom: 1px solid var(--border);
  padding: 18px 0;
  backdrop-filter: blur(10px);
  position: sticky; top: 0; z-index: 100;
  background: rgba(10,10,15,.85);
}
.header-inner { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.logo { display: flex; align-items: center; gap: 10px; }
.logo-icon {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.logo-text { font-size: 1.3rem; font-weight: 800; letter-spacing: -.02em; }
.logo-sub { font-size: .7rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; }

/* Breadcrumb */
.breadcrumb {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  font-family: 'JetBrains Mono', monospace; font-size: .78rem; color: var(--muted);
  padding: 14px 0 4px;
}
.breadcrumb a { color: var(--accent); text-decoration: none; transition: color .2s; }
.breadcrumb a:hover { color: var(--accent2); }
.breadcrumb span { color: var(--muted); }

/* Search & Upload bar */
.toolbar {
  display: flex; gap: 10px; padding: 14px 0;
  flex-wrap: wrap;
}
.search-box {
  flex: 1; min-width: 180px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 10px 14px;
  color: var(--text); font-family: 'Syne', sans-serif; font-size: .9rem;
  outline: none; transition: border-color .2s;
}
.search-box:focus { border-color: var(--accent); }
.search-box::placeholder { color: var(--muted); }
.btn {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 10px 18px;
  color: var(--text); font-family: 'Syne', sans-serif; font-size: .85rem; font-weight: 600;
  cursor: pointer; transition: all .2s; white-space: nowrap;
  display: flex; align-items: center; gap: 7px;
}
.btn:hover { border-color: var(--accent); color: var(--accent); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: #6b5aee; border-color: #6b5aee; color: #fff; }

/* File grid */
.file-list { display: flex; flex-direction: column; gap: 2px; padding-bottom: 40px; }
.file-item {
  display: flex; align-items: center; gap: 12px;
  padding: 11px 14px; border-radius: 10px;
  border: 1px solid transparent;
  transition: all .18s; cursor: pointer;
  text-decoration: none; color: var(--text);
  position: relative;
}
.file-item:hover {
  background: var(--surface);
  border-color: var(--border);
}
.file-item.dir:hover { border-color: var(--accent); }
.file-icon {
  width: 38px; height: 38px; border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.icon-dir  { background: rgba(124,106,255,.15); }
.icon-vid  { background: rgba(255,106,176,.15); }
.icon-aud  { background: rgba(74,222,128,.15); }
.icon-img  { background: rgba(96,165,250,.15); }
.icon-txt  { background: rgba(251,191,36,.15); }
.icon-file { background: rgba(107,107,128,.15); }

.file-name { flex: 1; font-size: .92rem; font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-meta { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.file-size { font-family: 'JetBrains Mono', monospace; font-size: .75rem; color: var(--muted); }
.file-date { font-family: 'JetBrains Mono', monospace; font-size: .72rem; color: var(--muted); }
.file-actions { display: flex; gap: 6px; opacity: 0; transition: opacity .18s; }
.file-item:hover .file-actions { opacity: 1; }
.action-btn {
  background: rgba(124,106,255,.15); border: none;
  border-radius: 6px; padding: 5px 10px;
  color: var(--accent); font-size: .75rem; font-weight: 600;
  cursor: pointer; transition: background .18s;
  font-family: 'Syne', sans-serif;
}
.action-btn:hover { background: rgba(124,106,255,.3); }

/* Media viewer */
.viewer-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.92);
  z-index: 1000; display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(6px); padding: 20px;
  opacity: 0; pointer-events: none; transition: opacity .25s;
}
.viewer-overlay.open { opacity: 1; pointer-events: all; }
.viewer-box {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; max-width: 900px; width: 100%;
  max-height: 90vh; overflow: hidden;
  display: flex; flex-direction: column;
}
.viewer-header {
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.viewer-title { font-size: .95rem; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.viewer-close {
  width: 30px; height: 30px; border-radius: 8px;
  background: rgba(248,113,113,.15); border: none;
  color: var(--red); font-size: 1.1rem; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .18s;
}
.viewer-close:hover { background: rgba(248,113,113,.3); }
.viewer-body { flex: 1; overflow: auto; display: flex; align-items: center; justify-content: center; min-height: 0; }
.viewer-body video, .viewer-body audio { width: 100%; outline: none; }
.viewer-body img { max-width: 100%; max-height: 70vh; object-fit: contain; }
.viewer-body pre {
  padding: 20px; font-family: 'JetBrains Mono', monospace;
  font-size: .8rem; line-height: 1.6; white-space: pre-wrap;
  word-break: break-all; color: var(--text); width: 100%;
}

/* Upload modal */
.upload-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.85);
  z-index: 1000; display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(6px);
  opacity: 0; pointer-events: none; transition: opacity .25s;
}
.upload-overlay.open { opacity: 1; pointer-events: all; }
.upload-box {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; padding: 28px; width: 360px;
  display: flex; flex-direction: column; gap: 16px;
}
.drop-zone {
  border: 2px dashed var(--border); border-radius: 12px;
  padding: 32px 20px; text-align: center; transition: all .2s;
  cursor: pointer;
}
.drop-zone.dragover { border-color: var(--accent); background: rgba(124,106,255,.08); }
.drop-zone p { color: var(--muted); font-size: .85rem; margin-top: 8px; }
.progress-bar { height: 4px; background: var(--border); border-radius: 99px; overflow: hidden; display: none; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); border-radius: 99px; width: 0%; transition: width .3s; }
.status-msg { font-size: .82rem; color: var(--muted); text-align: center; min-height: 18px; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 99px; }

/* Responsive */
@media (max-width: 600px) {
  .file-date { display: none; }
  .file-actions { opacity: 1; }
}
</style>
</head>
<body>
<header>
  <div class="wrap header-inner">
    <div class="logo">
      <div class="logo-icon">⚡</div>
      <div>
        <div class="logo-text">FileBeam</div>
        <div class="logo-sub">personal file server</div>
      </div>
    </div>
    <button class="btn btn-primary" onclick="openUpload()">⬆ Upload</button>
  </div>
</header>

<div class="wrap">
  <div class="breadcrumb" id="breadcrumb"></div>
  <div class="toolbar">
    <input class="search-box" placeholder="🔍  Search files…" id="searchInput" oninput="filterFiles()"/>
  </div>
  <div class="file-list" id="fileList"></div>
</div>

<!-- Media Viewer -->
<div class="viewer-overlay" id="viewerOverlay" onclick="closeViewer(event)">
  <div class="viewer-box">
    <div class="viewer-header">
      <span class="viewer-title" id="viewerTitle"></span>
      <button class="viewer-close" onclick="closeViewer()">✕</button>
    </div>
    <div class="viewer-body" id="viewerBody"></div>
  </div>
</div>

<!-- Upload Modal -->
<div class="upload-overlay" id="uploadOverlay" onclick="closeUpload(event)">
  <div class="upload-box" onclick="event.stopPropagation()">
    <div style="font-size:1.1rem;font-weight:700;">Upload Files</div>
    <div class="drop-zone" id="dropZone"
         ondragover="onDragOver(event)" ondragleave="onDragLeave()"
         ondrop="onDrop(event)" onclick="document.getElementById('fileInput').click()">
      <div style="font-size:2rem;">📂</div>
      <p>Drag & drop files here<br/>or <strong>click to browse</strong></p>
    </div>
    <input type="file" id="fileInput" multiple style="display:none" onchange="uploadFiles(this.files)"/>
    <div class="progress-bar" id="progressBar"><div class="progress-fill" id="progressFill"></div></div>
    <div class="status-msg" id="statusMsg"></div>
    <button class="btn" style="width:100%;justify-content:center;" onclick="closeUpload()">Close</button>
  </div>
</div>

<script>
const TOKEN = "{{TOKEN}}";
const API = (path) => `/api${path}?token=${TOKEN}`;
let currentPath = "/";
let allFiles = [];

function init() {
  const hash = decodeURIComponent(location.hash.slice(1)) || "/";
  navigate(hash, false);
}

async function navigate(path, pushState=true) {
  currentPath = path;
  if (pushState) history.pushState({}, "", "#" + encodeURIComponent(path));
  renderBreadcrumb(path);
  await loadDir(path);
}

function renderBreadcrumb(path) {
  const parts = path.split("/").filter(Boolean);
  let html = `<a href="#" onclick="navigate('/');return false;">🏠 Home</a>`;
  let acc = "";
  parts.forEach((p, i) => {
    acc += "/" + p;
    const snap = acc;
    html += `<span>/</span>`;
    if (i < parts.length - 1)
      html += `<a href="#" onclick="navigate('${snap}');return false;">${p}</a>`;
    else
      html += `<span style="color:var(--text)">${p}</span>`;
  });
  document.getElementById("breadcrumb").innerHTML = html;
}

async function loadDir(path) {
  const res = await fetch(API(`/list?path=${encodeURIComponent(path)}`));
  const data = await res.json();
  if (data.error) { alert(data.error); return; }
  allFiles = data.items;
  renderFiles(allFiles);
}

function filterFiles() {
  const q = document.getElementById("searchInput").value.toLowerCase();
  renderFiles(allFiles.filter(f => f.name.toLowerCase().includes(q)));
}

const icons = {
  dir: ["📁","icon-dir"], video: ["🎬","icon-vid"],
  audio: ["🎵","icon-aud"], image: ["🖼","icon-img"],
  text: ["📄","icon-txt"], file: ["📎","icon-file"]
};
function fileIcon(f) {
  if (f.is_dir) return icons.dir;
  const t = f.mime || "";
  if (t.startsWith("video/")) return icons.video;
  if (t.startsWith("audio/")) return icons.audio;
  if (t.startsWith("image/")) return icons.image;
  if (t.startsWith("text/") || f.name.match(/\.(md|json|py|js|ts|html|css|yaml|yml|sh|bat)$/)) return icons.text;
  return icons.file;
}

function renderFiles(files) {
  const el = document.getElementById("fileList");
  if (!files.length) { el.innerHTML = `<div style="text-align:center;padding:40px;color:var(--muted)">No files found</div>`; return; }
  el.innerHTML = files.map(f => {
    const [ico, cls] = fileIcon(f);
    const fp = currentPath.replace(/\/$/, "") + "/" + f.name;
    if (f.is_dir) return `
      <a class="file-item dir" href="#" onclick="navigate('${fp}');return false;">
        <div class="file-icon ${cls}">${ico}</div>
        <div class="file-name">${f.name}</div>
        <div class="file-meta">
          <span class="file-date">${f.modified}</span>
        </div>
      </a>`;
    const canPreview = f.mime && (f.mime.startsWith("video/")||f.mime.startsWith("audio/")||f.mime.startsWith("image/")||f.mime.startsWith("text/")||f.name.match(/\.(md|json|py|js|ts|html|css|yaml|yml|sh)$/));
    return `
      <div class="file-item" onclick="handleFileClick('${fp}','${f.name}','${f.mime||''}')">
        <div class="file-icon ${cls}">${ico}</div>
        <div class="file-name">${f.name}</div>
        <div class="file-meta">
          <span class="file-size">${f.size_human}</span>
          <span class="file-date">${f.modified}</span>
          <div class="file-actions" onclick="event.stopPropagation()">
            ${canPreview ? `<button class="action-btn" onclick="openViewer('${fp}','${f.name}','${f.mime||''}')">👁 View</button>` : ""}
            <a class="action-btn" href="${API('/download?path='+encodeURIComponent(fp))}" download="${f.name}">⬇ Save</a>
          </div>
        </div>
      </div>`;
  }).join("");
}

function handleFileClick(fp, name, mimetype) {
  const previewable = mimetype && (mimetype.startsWith("video/")||mimetype.startsWith("audio/")||mimetype.startsWith("image/")||mimetype.startsWith("text/"));
  const isTextExt = name.match(/\.(md|json|py|js|ts|html|css|yaml|yml|sh|bat)$/);
  if (previewable || isTextExt) openViewer(fp, name, mimetype);
  else window.location.href = API('/download?path='+encodeURIComponent(fp));
}

async function openViewer(fp, name, mimetype) {
  const overlay = document.getElementById("viewerOverlay");
  const body = document.getElementById("viewerBody");
  document.getElementById("viewerTitle").textContent = name;
  const url = API('/download?path='+encodeURIComponent(fp));
  if (mimetype.startsWith("video/"))
    body.innerHTML = `<video controls autoplay src="${url}"></video>`;
  else if (mimetype.startsWith("audio/"))
    body.innerHTML = `<audio controls autoplay src="${url}" style="width:100%;padding:20px"></audio>`;
  else if (mimetype.startsWith("image/"))
    body.innerHTML = `<img src="${url}" alt="${name}"/>`;
  else {
    body.innerHTML = `<pre>Loading…</pre>`;
    const res = await fetch(url);
    const text = await res.text();
    body.innerHTML = `<pre>${escHtml(text)}</pre>`;
  }
  overlay.classList.add("open");
}

function closeViewer(e) {
  if (e && e.target !== document.getElementById("viewerOverlay")) return;
  document.getElementById("viewerOverlay").classList.remove("open");
  document.getElementById("viewerBody").innerHTML = "";
}

function openUpload() { document.getElementById("uploadOverlay").classList.add("open"); }
function closeUpload(e) {
  if (e && e.target !== document.getElementById("uploadOverlay")) return;
  document.getElementById("uploadOverlay").classList.remove("open");
}

function onDragOver(e) { e.preventDefault(); document.getElementById("dropZone").classList.add("dragover"); }
function onDragLeave() { document.getElementById("dropZone").classList.remove("dragover"); }
function onDrop(e) { e.preventDefault(); onDragLeave(); uploadFiles(e.dataTransfer.files); }

async function uploadFiles(files) {
  if (!files.length) return;
  const bar = document.getElementById("progressBar");
  const fill = document.getElementById("progressFill");
  const msg = document.getElementById("statusMsg");
  bar.style.display = "block";
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    msg.textContent = `Uploading ${file.name}…`;
    const form = new FormData();
    form.append("file", file);
    form.append("path", currentPath);
    await new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => {
        fill.style.width = Math.round((i + e.loaded/e.total) / files.length * 100) + "%";
      };
      xhr.onload = () => resolve();
      xhr.open("POST", API("/upload"));
      xhr.send(form);
    });
  }
  fill.style.width = "100%";
  msg.textContent = `✅ ${files.length} file(s) uploaded!`;
  setTimeout(() => { bar.style.display="none"; fill.style.width="0%"; msg.textContent=""; }, 2000);
  loadDir(currentPath);
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

window.addEventListener("popstate", () => {
  const hash = decodeURIComponent(location.hash.slice(1)) || "/";
  navigate(hash, false);
});

init();
</script>
</body>
</html>
"""

# ── Request Handler ─────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    root = DEFAULT_ROOT
    token = ACCESS_TOKEN

    def log_message(self, fmt, *args):
        pass  # silence default logging

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def check_token(self, qs):
        return qs.get("token", [""])[0] == self.token

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # Serve main UI
        if parsed.path in ("/", ""):
            html = HTML_TEMPLATE.replace("{{TOKEN}}", self.token)
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
            return

        if not self.check_token(qs):
            self.send_json({"error": "Unauthorized"}, 401); return

        # List directory
        if parsed.path == "/api/list":
            rel = unquote(qs.get("path", ["/"])[0])
            abs_path = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
            if not abs_path.startswith(self.root):
                self.send_json({"error": "Access denied"}); return
            if not os.path.isdir(abs_path):
                self.send_json({"error": "Not a directory"}); return
            items = []
            try:
                for name in sorted(os.listdir(abs_path), key=lambda x: (not os.path.isdir(os.path.join(abs_path,x)), x.lower())):
                    fp = os.path.join(abs_path, name)
                    try:
                        stat = os.stat(fp)
                        is_dir = os.path.isdir(fp)
                        items.append({
                            "name": name,
                            "is_dir": is_dir,
                            "size": stat.st_size if not is_dir else 0,
                            "size_human": human_size(stat.st_size) if not is_dir else "—",
                            "modified": __import__("datetime").datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y"),
                            "mime": mime(fp) if not is_dir else "",
                        })
                    except: pass
            except PermissionError:
                self.send_json({"error": "Permission denied"}); return
            self.send_json({"items": items})
            return

        # Download / stream file
        if parsed.path == "/api/download":
            rel = unquote(qs.get("path", [""])[0])
            abs_path = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
            if not abs_path.startswith(self.root) or not os.path.isfile(abs_path):
                self.send_json({"error": "Not found"}, 404); return
            size = os.path.getsize(abs_path)
            mt = mime(abs_path)
            self.send_response(200)
            self.send_header("Content-Type", mt)
            self.send_header("Content-Length", size)
            self.send_header("Accept-Ranges", "bytes")
            fname = os.path.basename(abs_path)
            self.send_header("Content-Disposition", f'inline; filename="{fname}"')
            self.end_headers()
            try:
                with open(abs_path, "rb") as f:
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
            except: pass
            return

        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if not self.check_token(qs):
            self.send_json({"error": "Unauthorized"}, 401); return

        if parsed.path == "/api/upload":
            ct = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            # Parse multipart
            boundary = ct.split("boundary=")[-1].encode()
            parts = body.split(b"--" + boundary)
            upload_path = DEFAULT_ROOT
            file_data = None
            file_name = None
            for part in parts:
                if b"Content-Disposition" not in part: continue
                header, _, content = part.partition(b"\r\n\r\n")
                content = content.rstrip(b"\r\n")
                header_str = header.decode(errors="replace")
                if 'name="path"' in header_str:
                    rel = content.decode(errors="replace").strip()
                    abs_p = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
                    if abs_p.startswith(self.root):
                        upload_path = abs_p
                elif 'name="file"' in header_str:
                    fn_match = __import__("re").search(r'filename="([^"]+)"', header_str)
                    if fn_match:
                        file_name = fn_match.group(1)
                        file_data = content
            if file_data is not None and file_name:
                dest = os.path.join(upload_path, file_name)
                os.makedirs(upload_path, exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(file_data)
                self.send_json({"ok": True, "name": file_name})
            else:
                self.send_json({"error": "No file"}, 400)
            return

        self.send_json({"error": "Not found"}, 404)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="FileBeam - Personal File Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--root", type=str, default=DEFAULT_ROOT, help="Root folder to share")
    args = parser.parse_args()

    Handler.root = os.path.abspath(args.root)
    Handler.token = ACCESS_TOKEN

    print("\n" + "="*52)
    print("  ⚡  FileBeam  —  Personal File Server")
    print("="*52)
    print(f"  📁  Sharing  : {Handler.root}")
    print(f"  🌐  Local    : http://localhost:{args.port}")
    print(f"\n  🔑  Access URL (share this with yourself):")
    print(f"      http://YOUR_IP:{args.port}/?#/")
    print(f"\n  🔒  Token    : {ACCESS_TOKEN}")
    print(f"\n  To find your IP, run: ipconfig (Windows)")
    print(f"                    or: ifconfig (Mac/Linux)")
    print(f"\n  For internet access, set up port forwarding")
    print(f"  on port {args.port} in your router settings.")
    print("="*52)
    print("  Press Ctrl+C to stop\n")

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")

if __name__ == "__main__":
    main()
