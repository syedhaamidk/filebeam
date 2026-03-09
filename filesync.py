#!/usr/bin/env python3
"""
FileBeam Sync - Two-Way File Sync between PC and Phone
Run on your PC, open in phone browser on same WiFi.
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

def file_hash(path, block=65536):
    h = hashlib.md5()
    with open(path,"rb") as f:
        while chunk := f.read(block): h.update(chunk)
    return h.hexdigest()

def scan_dir(root):
    files = {}
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, root).replace("\\","/")
            try:
                stat = os.stat(fp)
                files[rel] = {
                    "rel": rel,
                    "size": stat.st_size,
                    "size_human": human_size(stat.st_size),
                    "mtime": stat.st_mtime,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y %H:%M"),
                    "mime": mime(fp),
                }
            except: pass
    return files

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FileBeam Sync</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root {
  --bg:#f0f2f5; --card:#ffffff; --border:#e2e5eb;
  --accent:#2563eb; --accent2:#7c3aed;
  --green:#16a34a; --red:#dc2626; --yellow:#d97706;
  --text:#111827; --muted:#6b7280; --light:#f9fafb;
  --shadow:0 1px 3px rgba(0,0,0,.08),0 4px 16px rgba(0,0,0,.05);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}

/* top bar */
.topbar{
  background:var(--card);border-bottom:1px solid var(--border);
  padding:14px 20px;display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:50;gap:12px;flex-wrap:wrap;
}
.brand{display:flex;align-items:center;gap:10px}
.brand-icon{
  width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  display:flex;align-items:center;justify-content:center;font-size:17px;color:#fff;
}
.brand-name{font-size:1.15rem;font-weight:700;letter-spacing:-.02em}
.brand-tag{font-size:.68rem;color:var(--muted);font-family:'DM Mono',monospace}
.conn-dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 0 3px rgba(22,163,74,.2)}
.conn-dot.off{background:var(--red);box-shadow:0 0 0 3px rgba(220,38,38,.2)}

/* main layout */
.container{max-width:900px;margin:0 auto;padding:24px 16px}
.section-title{font-size:.72rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}

/* tabs */
.tabs{display:flex;gap:4px;background:var(--border);border-radius:12px;padding:4px;margin-bottom:20px}
.tab{flex:1;padding:9px;border:none;background:transparent;border-radius:9px;
  font-family:'DM Sans',sans-serif;font-size:.85rem;font-weight:500;color:var(--muted);
  cursor:pointer;transition:all .18s;text-align:center}
.tab.active{background:var(--card);color:var(--accent);font-weight:700;box-shadow:var(--shadow)}

/* cards */
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;margin-bottom:14px;box-shadow:var(--shadow)}

/* stats bar */
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center;box-shadow:var(--shadow)}
.stat-val{font-size:1.4rem;font-weight:700;font-family:'DM Mono',monospace}
.stat-lbl{font-size:.7rem;color:var(--muted);margin-top:2px}

/* file list */
.file-row{
  display:flex;align-items:center;gap:10px;padding:10px 12px;
  border-radius:10px;border:1px solid transparent;transition:all .15s;
}
.file-row:hover{background:var(--light);border-color:var(--border)}
.file-ico{width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.ico-vid{background:rgba(124,58,237,.12)} .ico-img{background:rgba(37,99,235,.12)}
.ico-aud{background:rgba(22,163,74,.12)}  .ico-doc{background:rgba(217,119,6,.12)}
.ico-zip{background:rgba(220,38,38,.12)}  .ico-gen{background:rgba(107,114,128,.12)}
.file-info{flex:1;min-width:0}
.file-name{font-size:.88rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.file-sub{font-size:.72rem;color:var(--muted);font-family:'DM Mono',monospace;margin-top:1px}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:.68rem;font-weight:600}
.badge-new{background:rgba(22,163,74,.12);color:var(--green)}
.badge-mod{background:rgba(37,99,235,.12);color:var(--accent)}
.badge-del{background:rgba(220,38,38,.12);color:var(--red)}
.badge-sync{background:rgba(107,114,128,.12);color:var(--muted)}

/* buttons */
.btn{border:none;border-radius:10px;padding:10px 18px;font-family:'DM Sans',sans-serif;
  font-size:.85rem;font-weight:600;cursor:pointer;transition:all .18s;display:inline-flex;align-items:center;gap:7px}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:#1d4ed8}
.btn-success{background:var(--green);color:#fff}
.btn-success:hover{background:#15803d}
.btn-ghost{background:var(--light);color:var(--text);border:1px solid var(--border)}
.btn-ghost:hover{border-color:var(--accent);color:var(--accent)}
.btn-sm{padding:6px 12px;font-size:.78rem;border-radius:8px}
.btn-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}

/* drop zone */
.dropzone{
  border:2px dashed var(--border);border-radius:12px;padding:28px;
  text-align:center;transition:all .2s;cursor:pointer;
}
.dropzone:hover,.dropzone.over{border-color:var(--accent);background:rgba(37,99,235,.04)}
.dropzone p{color:var(--muted);font-size:.83rem;margin-top:6px}

/* progress */
.prog-wrap{margin-top:10px;display:none}
.prog-bar{height:5px;background:var(--border);border-radius:99px;overflow:hidden}
.prog-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:99px;width:0%;transition:width .3s}
.prog-label{font-size:.75rem;color:var(--muted);margin-top:5px;font-family:'DM Mono',monospace}

/* toast */
#toast{
  position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(80px);
  background:#111827;color:#fff;padding:10px 20px;border-radius:12px;
  font-size:.85rem;font-weight:500;z-index:999;transition:transform .3s;
  white-space:nowrap;pointer-events:none;
}
#toast.show{transform:translateX(-50%) translateY(0)}

/* empty state */
.empty{text-align:center;padding:32px;color:var(--muted);font-size:.85rem}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <div class="brand-icon">🔄</div>
    <div>
      <div class="brand-name">FileBeam Sync</div>
      <div class="brand-tag">two-way · pc ↔ phone</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:8px">
    <div class="conn-dot" id="connDot"></div>
    <span style="font-size:.78rem;color:var(--muted)" id="connLabel">Connecting…</span>
  </div>
</div>

<div class="container">

  <div class="stats">
    <div class="stat"><div class="stat-val" id="statTotal">—</div><div class="stat-lbl">Total Files</div></div>
    <div class="stat"><div class="stat-val" id="statSize">—</div><div class="stat-lbl">Total Size</div></div>
    <div class="stat"><div class="stat-val" id="statPending">—</div><div class="stat-lbl">To Sync</div></div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="showTab('sync')">🔄 Sync</button>
    <button class="tab" onclick="showTab('pc')">💻 PC Files</button>
    <button class="tab" onclick="showTab('upload')">⬆️ Upload</button>
  </div>

  <!-- SYNC TAB -->
  <div id="tab-sync">
    <div class="card">
      <div class="section-title">Sync Status</div>
      <div id="syncList"><div class="empty">Scanning…</div></div>
      <div class="btn-row">
        <button class="btn btn-success" onclick="doSync()">🔄 Sync All</button>
        <button class="btn btn-ghost" onclick="loadSync()">↺ Refresh</button>
      </div>
    </div>
  </div>

  <!-- PC FILES TAB -->
  <div id="tab-pc" style="display:none">
    <div class="card">
      <div class="section-title">Files on PC</div>
      <div id="pcList"><div class="empty">Loading…</div></div>
    </div>
  </div>

  <!-- UPLOAD TAB -->
  <div id="tab-upload" style="display:none">
    <div class="card">
      <div class="section-title">Send from Phone → PC</div>
      <div class="dropzone" id="dropzone"
           ondragover="onDragOver(event)" ondragleave="onDragLeave()"
           ondrop="onDrop(event)" onclick="document.getElementById('fileIn').click()">
        <div style="font-size:2.2rem">📤</div>
        <p>Tap to pick files from your phone<br/>or drag & drop</p>
      </div>
      <input type="file" id="fileIn" multiple style="display:none" onchange="uploadFiles(this.files)"/>
      <div class="prog-wrap" id="progWrap">
        <div class="prog-bar"><div class="prog-fill" id="progFill"></div></div>
        <div class="prog-label" id="progLabel"></div>
      </div>
    </div>
    <div class="card">
      <div class="section-title">Download from PC → Phone</div>
      <p style="font-size:.83rem;color:var(--muted);margin-bottom:12px">Switch to the PC Files tab and tap any file to download it to your phone.</p>
    </div>
  </div>

</div>

<div id="toast"></div>

<script>
const TOKEN = "{{TOKEN}}";
const A = p => `/api${p}?token=${TOKEN}`;
let pcFiles = {}, phoneFiles = {}, activeTab = "sync";

// ── Tabs ──────────────────────────────────────────────────────────────────
function showTab(id) {
  ["sync","pc","upload"].forEach(t => {
    document.getElementById("tab-"+t).style.display = t===id?"block":"none";
  });
  document.querySelectorAll(".tab").forEach((el,i) => {
    el.classList.toggle("active", ["sync","pc","upload"][i]===id);
  });
  activeTab = id;
  if (id==="pc") loadPCFiles();
  if (id==="sync") loadSync();
}

// ── Connection ────────────────────────────────────────────────────────────
async function checkConn() {
  try {
    const r = await fetch(A("/ping"), {signal: AbortSignal.timeout(3000)});
    const ok = r.ok;
    document.getElementById("connDot").className = "conn-dot" + (ok?"":" off");
    document.getElementById("connLabel").textContent = ok ? "Connected" : "Disconnected";
    return ok;
  } catch {
    document.getElementById("connDot").className = "conn-dot off";
    document.getElementById("connLabel").textContent = "Disconnected";
    return false;
  }
}

// ── Stats ─────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const r = await fetch(A("/files"));
    const d = await r.json();
    pcFiles = d.files || {};
    const total = Object.keys(pcFiles).length;
    const size = Object.values(pcFiles).reduce((a,f)=>a+f.size,0);
    document.getElementById("statTotal").textContent = total;
    document.getElementById("statSize").textContent = humanSize(size);
  } catch {}
}

// ── PC Files tab ──────────────────────────────────────────────────────────
async function loadPCFiles() {
  const el = document.getElementById("pcList");
  try {
    const r = await fetch(A("/files"));
    const d = await r.json();
    pcFiles = d.files || {};
    const items = Object.values(pcFiles);
    if (!items.length) { el.innerHTML='<div class="empty">No files on PC yet</div>'; return; }
    el.innerHTML = items.map(f => `
      <div class="file-row">
        <div class="file-ico ${icoClass(f.mime)}">${icoEmoji(f.mime)}</div>
        <div class="file-info">
          <div class="file-name">${f.rel}</div>
          <div class="file-sub">${f.size_human} · ${f.modified}</div>
        </div>
        <a class="btn btn-ghost btn-sm" href="${A('/download?path='+encodeURIComponent(f.rel))}" download>⬇</a>
      </div>`).join("");
  } catch { el.innerHTML='<div class="empty">Failed to load</div>'; }
}

// ── Sync tab ──────────────────────────────────────────────────────────────
async function loadSync() {
  await loadStats();
  const el = document.getElementById("syncList");
  // Simulate phone-side file awareness via localStorage keys (files user uploaded this session)
  const uploaded = JSON.parse(sessionStorage.getItem("uploaded")||"[]");
  const synced = JSON.parse(sessionStorage.getItem("synced")||"[]");

  const pcItems = Object.values(pcFiles);
  const rows = [];

  pcItems.forEach(f => {
    const isSynced = synced.includes(f.rel);
    rows.push({...f, status: isSynced?"synced":"pc_only"});
  });
  uploaded.forEach(name => {
    if (!pcFiles[name]) rows.push({rel:name, size_human:"—", modified:"just now", mime:"", status:"phone_only"});
  });

  document.getElementById("statPending").textContent = rows.filter(r=>r.status!=="synced").length;

  if (!rows.length) { el.innerHTML='<div class="empty">No files found. Upload some files to get started!</div>'; return; }

  el.innerHTML = rows.map(f => {
    const badgeMap = {synced:['badge-sync','✓ Synced'], pc_only:['badge-mod','💻 PC Only'], phone_only:['badge-new','📱 Phone Only']};
    const [bc, bl] = badgeMap[f.status]||['badge-sync','—'];
    return `
      <div class="file-row">
        <div class="file-ico ${icoClass(f.mime)}">${icoEmoji(f.mime)}</div>
        <div class="file-info">
          <div class="file-name">${f.rel}</div>
          <div class="file-sub">${f.size_human} · ${f.modified}</div>
        </div>
        <span class="badge ${bc}">${bl}</span>
      </div>`;
  }).join("");
}

async function doSync() {
  const synced = JSON.parse(sessionStorage.getItem("synced")||"[]");
  Object.keys(pcFiles).forEach(k => { if (!synced.includes(k)) synced.push(k); });
  sessionStorage.setItem("synced", JSON.stringify(synced));
  toast("✅ All PC files marked as synced!");
  loadSync();
}

// ── Upload ────────────────────────────────────────────────────────────────
function onDragOver(e){e.preventDefault();document.getElementById("dropzone").classList.add("over")}
function onDragLeave(){document.getElementById("dropzone").classList.remove("over")}
function onDrop(e){e.preventDefault();onDragLeave();uploadFiles(e.dataTransfer.files)}

async function uploadFiles(files) {
  if (!files.length) return;
  const pw = document.getElementById("progWrap");
  const pf = document.getElementById("progFill");
  const pl = document.getElementById("progLabel");
  pw.style.display = "block";
  const uploaded = JSON.parse(sessionStorage.getItem("uploaded")||"[]");

  for (let i=0; i<files.length; i++) {
    const file = files[i];
    pl.textContent = `Uploading ${file.name} (${i+1}/${files.length})…`;
    const form = new FormData();
    form.append("file", file);
    form.append("path", "/");
    await new Promise(resolve => {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = e => {
        pf.style.width = Math.round((i + e.loaded/e.total)/files.length*100)+"%";
      };
      xhr.onload = resolve;
      xhr.open("POST", A("/upload"));
      xhr.send(form);
    });
    if (!uploaded.includes(file.name)) uploaded.push(file.name);
  }
  sessionStorage.setItem("uploaded", JSON.stringify(uploaded));
  pf.style.width = "100%";
  pl.textContent = `✅ ${files.length} file(s) sent to PC!`;
  setTimeout(()=>{ pw.style.display="none"; pf.style.width="0%"; }, 3000);
  toast(`✅ ${files.length} file(s) uploaded to PC!`);
  loadStats();
}

// ── Helpers ────────────────────────────────────────────────────────────────
function humanSize(n){
  for(const u of["B","KB","MB","GB"]){if(n<1024)return n.toFixed(1)+" "+u;n/=1024}
  return n.toFixed(1)+" TB";
}
function icoClass(m=""){
  if(m.startsWith("video/"))return "ico-vid";
  if(m.startsWith("image/"))return "ico-img";
  if(m.startsWith("audio/"))return "ico-aud";
  if(m.includes("zip")||m.includes("rar"))return "ico-zip";
  if(m.startsWith("text/")||m.includes("pdf")||m.includes("doc"))return "ico-doc";
  return "ico-gen";
}
function icoEmoji(m=""){
  if(m.startsWith("video/"))return "🎬";
  if(m.startsWith("image/"))return "🖼";
  if(m.startsWith("audio/"))return "🎵";
  if(m.includes("pdf"))return "📕";
  if(m.includes("zip")||m.includes("rar"))return "🗜";
  if(m.startsWith("text/"))return "📄";
  return "📎";
}
function toast(msg){
  const t=document.getElementById("toast");
  t.textContent=msg; t.classList.add("show");
  setTimeout(()=>t.classList.remove("show"),3000);
}

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
  await checkConn();
  await loadStats();
  await loadSync();
  setInterval(checkConn, 10000);
}
init();
</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    root = DEFAULT_ROOT
    token = ACCESS_TOKEN

    def log_message(self, fmt, *args): pass

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", len(body))
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
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
            return

        if not self.check_token(qs):
            self.send_json({"error":"Unauthorized"},401); return

        if parsed.path == "/api/ping":
            self.send_json({"ok":True,"time":time.time()}); return

        if parsed.path == "/api/files":
            files = scan_dir(self.root)
            total_size = sum(f["size"] for f in files.values())
            self.send_json({"files":files,"total":len(files),"total_size":total_size,"total_size_human":human_size(total_size)})
            return

        if parsed.path == "/api/download":
            rel = unquote(qs.get("path",[""])[0])
            abs_path = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
            if not abs_path.startswith(self.root) or not os.path.isfile(abs_path):
                self.send_json({"error":"Not found"},404); return
            size = os.path.getsize(abs_path)
            mt = mime(abs_path)
            fname = os.path.basename(abs_path)
            self.send_response(200)
            self.send_header("Content-Type", mt)
            self.send_header("Content-Length", size)
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
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
                    if abs_p.startswith(self.root): upload_path = abs_p
                elif 'name="file"' in header_str:
                    fn_match = re.search(r'filename="([^"]+)"', header_str)
                    if fn_match:
                        file_name = fn_match.group(1)
                        file_data = content
            if file_data is not None and file_name:
                os.makedirs(upload_path, exist_ok=True)
                dest = os.path.join(upload_path, file_name)
                with open(dest,"wb") as f: f.write(file_data)
                self.send_json({"ok":True,"name":file_name})
            else:
                self.send_json({"error":"No file"},400)
            return

        self.send_json({"error":"Not found"},404)

def main():
    parser = argparse.ArgumentParser(description="FileBeam Sync")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--root", type=str, default=DEFAULT_ROOT)
    args = parser.parse_args()

    Handler.root = os.path.abspath(args.root)
    os.makedirs(Handler.root, exist_ok=True)
    Handler.token = ACCESS_TOKEN

    print("\n" + "="*54)
    print("  🔄  FileBeam Sync  —  PC ↔ Phone Two-Way Sync")
    print("="*54)
    print(f"  📁  Sync Folder : {Handler.root}")
    print(f"  🌐  Local URL   : http://localhost:{args.port}")
    print(f"\n  📱  On your phone (same WiFi):")
    print(f"      1. Run: ipconfig  →  find IPv4 Address")
    print(f"      2. Open: http://<YOUR_IP>:{args.port}")
    print(f"\n  🔒  Token: {ACCESS_TOKEN}")
    print("="*54)
    print("  Press Ctrl+C to stop\n")

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Sync server stopped.")

if __name__ == "__main__":
    main()
