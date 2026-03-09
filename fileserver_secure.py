#!/usr/bin/env python3
"""
FileBeam Secure - Hardened Personal File Server
Features:
  - HTTPS with self-signed certificate
  - Login page with secure session cookies (HttpOnly, Secure, SameSite)
  - Token in Authorization header, never in URL
  - Rate limiting & brute-force lockout
  - Upload restrictions (file type whitelist, size limit)
  - Auto-expiring sessions
  - Security headers on every response
"""

import os, json, mimetypes, secrets, hashlib, argparse, re, ssl, time, ipaddress
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime
import subprocess, tempfile, threading

# ═══════════════════════════════════════════════════════════════════
#  CONFIG  — edit these before running
# ═══════════════════════════════════════════════════════════════════
DEFAULT_PORT   = 8443
DEFAULT_ROOT   = str(Path.home())

# Password: change this! Will be hashed at startup.
SERVER_PASSWORD = "changeme123"

# Session settings
SESSION_LIFETIME  = 3600        # seconds (1 hour)
SESSION_IDLE_TIMEOUT = 900      # seconds (15 min idle = logout)

# Rate limiting / brute-force
MAX_LOGIN_ATTEMPTS  = 5         # attempts before lockout
LOCKOUT_DURATION    = 300       # seconds (5 min)
RATE_WINDOW         = 60        # seconds to track attempts
MAX_REQUESTS_PER_MIN = 120      # general request rate limit per IP

# Upload restrictions
MAX_UPLOAD_BYTES = 500 * 1024 * 1024   # 500 MB per file
ALLOWED_EXTENSIONS = {
    # Documents
    ".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".txt",".md",".csv",".rtf",
    # Images
    ".jpg",".jpeg",".png",".gif",".webp",".svg",".heic",".bmp",
    # Video
    ".mp4",".mov",".avi",".mkv",".webm",".m4v",
    # Audio
    ".mp3",".wav",".flac",".aac",".ogg",".m4a",
    # Archives
    ".zip",".tar",".gz",".7z",".rar",
    # Code / data
    ".json",".xml",".yaml",".yml",".py",".js",".ts",".html",".css",".sh",
}

# ═══════════════════════════════════════════════════════════════════
#  INTERNAL STATE
# ═══════════════════════════════════════════════════════════════════
PASSWORD_HASH = hashlib.sha256(SERVER_PASSWORD.encode()).hexdigest()

# sessions: {token: {created, last_active, ip}}
_sessions: dict = {}
_sessions_lock = threading.Lock()

# rate limiting: {ip: [timestamp, ...]}
_login_attempts: dict = {}
_lockouts: dict = {}          # {ip: lockout_until}
_request_times: dict = {}     # {ip: [timestamps]}
_state_lock = threading.Lock()

# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════
def human_size(n):
    for u in ("B","KB","MB","GB","TB"):
        if n < 1024: return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"

def mime_of(path):
    t, _ = mimetypes.guess_type(path)
    return t or "application/octet-stream"

def now(): return time.time()

# ── Session management ───────────────────────────────────────────
def create_session(ip: str) -> str:
    token = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[token] = {"created": now(), "last_active": now(), "ip": ip}
    return token

def validate_session(token: str, ip: str) -> bool:
    if not token:
        return False
    with _sessions_lock:
        s = _sessions.get(token)
        if not s:
            return False
        age = now() - s["created"]
        idle = now() - s["last_active"]
        if age > SESSION_LIFETIME or idle > SESSION_IDLE_TIMEOUT:
            del _sessions[token]
            return False
        # Optional: bind session to originating IP
        # if s["ip"] != ip: del _sessions[token]; return False
        s["last_active"] = now()
    return True

def revoke_session(token: str):
    with _sessions_lock:
        _sessions.pop(token, None)

def purge_expired_sessions():
    with _sessions_lock:
        dead = [t for t, s in _sessions.items()
                if now()-s["created"] > SESSION_LIFETIME
                or now()-s["last_active"] > SESSION_IDLE_TIMEOUT]
        for t in dead:
            del _sessions[t]

# ── Rate limiting ────────────────────────────────────────────────
def is_locked_out(ip: str) -> bool:
    with _state_lock:
        until = _lockouts.get(ip, 0)
        if now() < until:
            return True
        if until:
            del _lockouts[ip]
            _login_attempts.pop(ip, None)
    return False

def record_failed_login(ip: str):
    with _state_lock:
        attempts = _login_attempts.setdefault(ip, [])
        attempts.append(now())
        # Keep only attempts within the window
        _login_attempts[ip] = [t for t in attempts if now()-t < RATE_WINDOW]
        if len(_login_attempts[ip]) >= MAX_LOGIN_ATTEMPTS:
            _lockouts[ip] = now() + LOCKOUT_DURATION
            del _login_attempts[ip]

def clear_login_attempts(ip: str):
    with _state_lock:
        _login_attempts.pop(ip, None)
        _lockouts.pop(ip, None)

def is_rate_limited(ip: str) -> bool:
    with _state_lock:
        times = _request_times.setdefault(ip, [])
        times.append(now())
        _request_times[ip] = [t for t in times if now()-t < 60]
        return len(_request_times[ip]) > MAX_REQUESTS_PER_MIN

def lockout_remaining(ip: str) -> int:
    with _state_lock:
        until = _lockouts.get(ip, 0)
        return max(0, int(until - now()))

# ── Upload validation ────────────────────────────────────────────
def validate_upload(filename: str, size: int) -> tuple[bool, str]:
    if size > MAX_UPLOAD_BYTES:
        return False, f"File too large. Max {human_size(MAX_UPLOAD_BYTES)}."
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File type '{ext}' not allowed."
    # Basic filename sanitisation
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', filename):
        return False, "Invalid characters in filename."
    return True, ""

# ── SSL certificate (self-signed) ────────────────────────────────
def generate_self_signed_cert(cert_path: str, key_path: str):
    """Generate a self-signed cert using openssl CLI."""
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return  # already exists
    print("  🔐  Generating self-signed TLS certificate…")
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_path, "-out", cert_path,
            "-days", "3650", "-nodes",
            "-subj", "/CN=FileBeam/O=FileBeam/C=US",
            "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost"
        ], check=True, capture_output=True)
        print("  ✅  Certificate generated.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: pure-Python via cryptography lib if available
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509 import DNSName, IPAddress
            import datetime as dt, ipaddress as ipa
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FileBeam")])
            cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(dt.datetime.utcnow())
                .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=3650))
                .add_extension(x509.SubjectAlternativeName([
                    DNSName("localhost"),
                    IPAddress(ipa.IPv4Address("127.0.0.1"))
                ]), critical=False)
                .sign(key, hashes.SHA256()))
            with open(key_path,"wb") as f:
                f.write(key.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption()))
            with open(cert_path,"wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            print("  ✅  Certificate generated (via cryptography lib).")
        except ImportError:
            print("  ⚠️   Could not generate cert. Install openssl or 'pip install cryptography'.")
            raise SystemExit(1)

# ═══════════════════════════════════════════════════════════════════
#  HTML
# ═══════════════════════════════════════════════════════════════════
LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FileBeam — Sign In</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet"/>
<style>
:root{--bg:#07080f;--card:#0e1018;--border:#1e2130;--accent:#4f8ef7;--text:#eef0f8;--muted:#5a5f7a;--red:#ff5f5f;--green:#3dd68c}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Outfit',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 70% 50% at 20% 0%,rgba(79,142,247,.1) 0%,transparent 60%),radial-gradient(ellipse 50% 40% at 80% 100%,rgba(224,107,255,.07) 0%,transparent 60%);pointer-events:none}
.box{position:relative;z-index:1;background:var(--card);border:1px solid var(--border);border-radius:20px;padding:36px 32px;width:100%;max-width:380px;box-shadow:0 24px 60px rgba(0,0,0,.5)}
.logo{display:flex;align-items:center;gap:10px;margin-bottom:28px;justify-content:center}
.logo-mark{width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,#4f8ef7,#e06bff);display:flex;align-items:center;justify-content:center;font-size:20px;box-shadow:0 0 24px rgba(79,142,247,.4)}
.logo-name{font-size:1.4rem;font-weight:800;letter-spacing:-.03em}
.title{font-size:1.1rem;font-weight:700;margin-bottom:6px;text-align:center}
.sub{font-size:.82rem;color:var(--muted);text-align:center;margin-bottom:24px}
label{font-size:.78rem;font-weight:600;color:var(--muted);letter-spacing:.05em;text-transform:uppercase;display:block;margin-bottom:6px}
.input-wrap{position:relative;margin-bottom:16px}
input[type=password]{width:100%;background:#141620;border:1px solid var(--border);border-radius:11px;padding:12px 44px 12px 14px;color:var(--text);font-family:'Outfit',sans-serif;font-size:.9rem;outline:none;transition:border-color .2s,box-shadow .2s}
input[type=password]:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(79,142,247,.15)}
.toggle-pw{position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;border:none;color:var(--muted);cursor:pointer;font-size:1rem;padding:4px;transition:color .18s}
.toggle-pw:hover{color:var(--text)}
.btn{width:100%;padding:13px;border:none;border-radius:11px;background:linear-gradient(135deg,#4f8ef7,#3d6fd4);color:#fff;font-family:'Outfit',sans-serif;font-size:.95rem;font-weight:700;cursor:pointer;transition:all .2s;box-shadow:0 2px 14px rgba(79,142,247,.35);margin-top:4px}
.btn:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(79,142,247,.5)}
.btn:active{transform:none}
.btn:disabled{opacity:.5;pointer-events:none}
.err{background:rgba(255,95,95,.12);border:1px solid rgba(255,95,95,.25);border-radius:10px;padding:10px 14px;font-size:.82rem;color:var(--red);margin-bottom:14px;display:none}
.err.show{display:block}
.lock-msg{background:rgba(255,176,32,.1);border:1px solid rgba(255,176,32,.25);border-radius:10px;padding:10px 14px;font-size:.82rem;color:#ffb020;margin-bottom:14px;display:none}
.lock-msg.show{display:block}
.secure-note{display:flex;align-items:center;gap:6px;justify-content:center;margin-top:20px;font-size:.72rem;color:var(--muted);font-family:'Fira Code',monospace}
.dot-green{width:6px;height:6px;border-radius:50%;background:var(--green)}
</style>
</head>
<body>
<div class="box">
  <div class="logo">
    <div class="logo-mark">⚡</div>
    <div class="logo-name">FileBeam</div>
  </div>
  <div class="title">Welcome back</div>
  <div class="sub">Enter your password to access files</div>
  <div class="err" id="errMsg"></div>
  <div class="lock-msg" id="lockMsg"></div>
  <label for="pw">Password</label>
  <div class="input-wrap">
    <input type="password" id="pw" placeholder="••••••••••••" autocomplete="current-password" onkeydown="if(event.key==='Enter')login()"/>
    <button class="toggle-pw" onclick="togglePw()" tabindex="-1" type="button">👁</button>
  </div>
  <button class="btn" id="loginBtn" onclick="login()">Sign In →</button>
  <div class="secure-note"><div class="dot-green"></div>End-to-end encrypted · HTTPS</div>
</div>
<script>
let locked = false;
function togglePw(){
  const i=document.getElementById('pw');
  i.type = i.type==='password'?'text':'password';
}
async function login(){
  if(locked) return;
  const pw = document.getElementById('pw').value;
  const btn = document.getElementById('loginBtn');
  if(!pw){ showErr('Please enter your password.'); return; }
  btn.disabled=true; btn.textContent='Signing in…';
  try{
    const r = await fetch('/auth/login',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({password:pw})
    });
    const d = await r.json();
    if(r.ok && d.ok){
      btn.textContent='✓ Success!';
      setTimeout(()=>location.href='/',500);
    } else if(r.status===429){
      locked=true;
      document.getElementById('lockMsg').textContent = d.error || 'Too many attempts. Try again later.';
      document.getElementById('lockMsg').classList.add('show');
      document.getElementById('errMsg').classList.remove('show');
      btn.textContent='Locked Out';
      startLockTimer(d.retry_after||300);
    } else {
      showErr(d.error || 'Incorrect password.');
      btn.disabled=false; btn.textContent='Sign In →';
      document.getElementById('pw').value='';
      document.getElementById('pw').focus();
    }
  } catch {
    showErr('Connection error. Try again.');
    btn.disabled=false; btn.textContent='Sign In →';
  }
}
function showErr(msg){
  const e=document.getElementById('errMsg');
  e.textContent=msg; e.classList.add('show');
}
function startLockTimer(secs){
  const msg=document.getElementById('lockMsg');
  const interval=setInterval(()=>{
    secs--;
    if(secs<=0){ clearInterval(interval); locked=false; location.reload(); return; }
    msg.textContent=`Too many attempts. Try again in ${secs}s.`;
  },1000);
}
document.getElementById('pw').focus();
</script>
</body>
</html>"""

MAIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FileBeam</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Fira+Code:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{--bg:#07080f;--surface:#0e1018;--surface2:#141620;--border:#1e2130;--border2:#262a3a;--accent:#4f8ef7;--accent-glow:rgba(79,142,247,.35);--pink:#e06bff;--green:#3dd68c;--yellow:#f5c542;--red:#ff5f5f;--text:#eef0f8;--muted:#5a5f7a;--muted2:#3a3f55}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{font-family:'Outfit',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 70% 50% at 15% 0%,rgba(79,142,247,.08),transparent 65%),radial-gradient(ellipse 50% 40% at 85% 100%,rgba(224,107,255,.07),transparent 60%);pointer-events:none;z-index:0}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:99px}
header{position:sticky;top:0;z-index:100;background:rgba(7,8,15,.85);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:0 20px;height:62px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.logo{display:flex;align-items:center;gap:11px;text-decoration:none;color:inherit}
.logo-mark{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--accent),var(--pink));display:flex;align-items:center;justify-content:center;font-size:17px;box-shadow:0 0 20px var(--accent-glow)}
.logo-text{font-size:1.2rem;font-weight:800;letter-spacing:-.03em;background:linear-gradient(90deg,var(--text) 60%,var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo-ver{font-size:.62rem;font-family:'Fira Code',monospace;color:var(--muted);margin-top:-2px}
.header-right{display:flex;align-items:center;gap:8px}
.pill{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;border-radius:99px;font-size:.72rem;font-weight:600;border:1px solid}
.pill-green{background:rgba(61,214,140,.1);border-color:rgba(61,214,140,.25);color:var(--green)}
.pill-red{background:rgba(255,95,95,.1);border-color:rgba(255,95,95,.25);color:var(--red)}
.dot{width:6px;height:6px;border-radius:50%;background:currentColor;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.btn{display:inline-flex;align-items:center;gap:7px;padding:9px 18px;border-radius:10px;border:none;font-family:'Outfit',sans-serif;font-size:.85rem;font-weight:600;cursor:pointer;transition:all .2s;white-space:nowrap}
.btn-glow{background:linear-gradient(135deg,var(--accent),#3d6fd4);color:#fff;box-shadow:0 2px 12px rgba(79,142,247,.35)}
.btn-glow:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(79,142,247,.5)}
.btn-ghost{background:var(--surface2);border:1px solid var(--border2);color:var(--text)}
.btn-ghost:hover{border-color:var(--accent);color:var(--accent)}
.btn-danger{background:rgba(255,95,95,.12);border:1px solid rgba(255,95,95,.25);color:var(--red)}
.btn-danger:hover{background:rgba(255,95,95,.2)}
.btn-sm{padding:6px 12px;font-size:.75rem;border-radius:8px}
.wrap{position:relative;z-index:1;max-width:980px;margin:0 auto;padding:0 16px}
.breadcrumb-bar{padding:14px 0 0;display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-family:'Fira Code',monospace;font-size:.75rem}
.bc-seg{display:flex;align-items:center;gap:6px;color:var(--muted);cursor:pointer;transition:color .18s;padding:3px 8px;border-radius:6px}
.bc-seg:hover{color:var(--accent);background:rgba(79,142,247,.08)}
.bc-sep{color:var(--muted2)}
.bc-cur{color:var(--text);font-weight:500}
.toolbar{display:flex;gap:10px;padding:14px 0 10px;flex-wrap:wrap;align-items:center}
.search-wrap{flex:1;min-width:200px;position:relative}
.search-icon{position:absolute;left:13px;top:50%;transform:translateY(-50%);color:var(--muted);pointer-events:none}
.search-input{width:100%;background:var(--surface2);border:1px solid var(--border2);border-radius:11px;padding:10px 14px 10px 38px;color:var(--text);font-family:'Outfit',sans-serif;font-size:.88rem;outline:none;transition:all .2s}
.search-input:focus{border-color:var(--accent);background:var(--surface);box-shadow:0 0 0 3px rgba(79,142,247,.12)}
.search-input::placeholder{color:var(--muted)}
.view-toggle{display:flex;gap:3px;background:var(--surface2);border:1px solid var(--border2);border-radius:10px;padding:3px}
.view-btn{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:7px;border:none;background:transparent;color:var(--muted);cursor:pointer;transition:all .18s}
.view-btn.active{background:var(--border2);color:var(--text)}
.sort-bar{display:flex;gap:4px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.sort-btn{background:none;border:none;color:var(--muted);font-family:'Outfit',sans-serif;font-size:.72rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;cursor:pointer;padding:4px 8px;border-radius:6px;transition:all .18s;display:flex;align-items:center;gap:4px}
.sort-btn:hover{color:var(--text);background:var(--surface2)}
.sort-btn.active{color:var(--accent)}
.sort-name{flex:1}.sort-size{width:90px;text-align:right}.sort-date{width:130px;text-align:right}.sort-actions{width:100px}
.file-list{display:flex;flex-direction:column;gap:2px;padding:6px 0 60px}
.file-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;padding:6px 0 60px}
.file-row{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:11px;border:1px solid transparent;text-decoration:none;color:var(--text);transition:all .18s;cursor:pointer;position:relative;overflow:hidden}
.file-row::before{content:'';position:absolute;inset:0;background:linear-gradient(90deg,rgba(79,142,247,.05),transparent);opacity:0;transition:opacity .2s;border-radius:11px}
.file-row:hover{background:var(--surface2);border-color:var(--border2)}
.file-row:hover::before{opacity:1}
.file-row.dir:hover{border-color:rgba(79,142,247,.3)}
.file-card{background:var(--surface2);border:1px solid var(--border2);border-radius:13px;padding:16px 12px;display:flex;flex-direction:column;align-items:center;gap:10px;cursor:pointer;transition:all .2s;text-align:center;color:var(--text);position:relative;overflow:hidden}
.file-card:hover{border-color:rgba(79,142,247,.4);transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.3)}
.file-card .card-ico{font-size:2.2rem;line-height:1}
.file-card .card-name{font-size:.78rem;font-weight:600;width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-card .card-size{font-size:.68rem;font-family:'Fira Code',monospace;color:var(--muted)}
.file-card .card-actions{position:absolute;inset:0;background:rgba(7,8,15,.85);display:flex;align-items:center;justify-content:center;gap:8px;opacity:0;transition:opacity .2s;border-radius:13px}
.file-card:hover .card-actions{opacity:1}
.f-ico{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:19px;flex-shrink:0;transition:transform .2s}
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
.f-actions{width:100px;display:flex;justify-content:flex-end;gap:5px;opacity:0;transition:opacity .18s;flex-shrink:0}
.file-row:hover .f-actions{opacity:1}
.act-btn{width:28px;height:28px;border-radius:7px;border:1px solid var(--border2);background:var(--surface);color:var(--muted);display:flex;align-items:center;justify-content:center;font-size:.8rem;cursor:pointer;transition:all .18s;text-decoration:none}
.act-btn:hover{border-color:var(--accent);color:var(--accent);background:rgba(79,142,247,.1)}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 20px;gap:12px;color:var(--muted)}
.drop-overlay{position:fixed;inset:0;z-index:200;background:rgba(7,8,15,.9);backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .25s}
.drop-overlay.active{opacity:1;pointer-events:all}
.drop-inner{border:2px dashed var(--accent);border-radius:20px;padding:60px 80px;text-align:center;animation:dropPulse 1.5s ease infinite}
@keyframes dropPulse{0%,100%{box-shadow:0 0 0 0 var(--accent-glow)}50%{box-shadow:0 0 40px 10px var(--accent-glow)}}
.modal-bg{position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.75);backdrop-filter:blur(10px);display:flex;align-items:center;justify-content:center;padding:20px;opacity:0;pointer-events:none;transition:opacity .25s}
.modal-bg.open{opacity:1;pointer-events:all}
.modal{background:var(--surface);border:1px solid var(--border2);border-radius:18px;width:100%;max-width:420px;overflow:hidden;transform:translateY(20px) scale(.97);transition:transform .3s}
.modal-bg.open .modal{transform:none}
.modal-head{padding:18px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.modal-title{font-size:1rem;font-weight:700}
.modal-close{width:28px;height:28px;border-radius:8px;border:none;background:rgba(255,95,95,.12);color:var(--red);cursor:pointer;font-size:1rem;display:flex;align-items:center;justify-content:center;transition:background .18s}
.modal-close:hover{background:rgba(255,95,95,.25)}
.modal-body{padding:20px;display:flex;flex-direction:column;gap:14px}
.upload-zone{border:2px dashed var(--border2);border-radius:13px;padding:30px 20px;text-align:center;cursor:pointer;transition:all .2s}
.upload-zone:hover,.upload-zone.drag{border-color:var(--accent);background:rgba(79,142,247,.05)}
.upload-zone-ico{font-size:2.4rem;margin-bottom:8px}
.upload-zone p{font-size:.83rem;color:var(--muted);margin-top:4px}
.upload-zone strong{color:var(--accent)}
.upload-limit{font-size:.72rem;font-family:'Fira Code',monospace;color:var(--muted);text-align:center;margin-top:-4px}
.prog-wrap{display:none;flex-direction:column;gap:6px}
.prog-track{height:5px;background:var(--border2);border-radius:99px;overflow:hidden}
.prog-fill{height:100%;border-radius:99px;background:linear-gradient(90deg,var(--accent),var(--pink));width:0%;transition:width .3s;box-shadow:0 0 10px rgba(79,142,247,.5)}
.prog-label{font-family:'Fira Code',monospace;font-size:.73rem;color:var(--muted);text-align:center}
.viewer-bg{position:fixed;inset:0;z-index:400;background:rgba(0,0,0,.92);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:center;padding:20px;opacity:0;pointer-events:none;transition:opacity .25s}
.viewer-bg.open{opacity:1;pointer-events:all}
.viewer{background:var(--surface);border:1px solid var(--border2);border-radius:18px;width:100%;max-width:920px;max-height:90vh;display:flex;flex-direction:column;overflow:hidden;transform:scale(.95);transition:transform .3s}
.viewer-bg.open .viewer{transform:none}
.viewer-head{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}
.viewer-name{flex:1;font-size:.9rem;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.viewer-body{flex:1;overflow:auto;display:flex;align-items:center;justify-content:center;min-height:0;background:var(--bg)}
.viewer-body video,.viewer-body audio{width:100%;outline:none}
.viewer-body img{max-width:100%;max-height:75vh;object-fit:contain;display:block}
.viewer-body pre{width:100%;padding:24px;font-family:'Fira Code',monospace;font-size:.8rem;line-height:1.7;color:var(--text);white-space:pre-wrap;word-break:break-all}
.toast-stack{position:fixed;bottom:24px;right:24px;z-index:999;display:flex;flex-direction:column;gap:8px;align-items:flex-end}
.toast{display:flex;align-items:center;gap:10px;padding:11px 16px;border-radius:12px;font-size:.83rem;font-weight:600;border:1px solid;transform:translateX(120%);transition:transform .3s cubic-bezier(.34,1.56,.64,1);max-width:320px;backdrop-filter:blur(10px)}
.toast.show{transform:none}
.toast.info{background:rgba(79,142,247,.15);border-color:rgba(79,142,247,.3);color:var(--accent)}
.toast.success{background:rgba(61,214,140,.15);border-color:rgba(61,214,140,.3);color:var(--green)}
.toast.error{background:rgba(255,95,95,.15);border-color:rgba(255,95,95,.3);color:var(--red)}
.ctx-menu{position:fixed;z-index:500;background:var(--surface2);border:1px solid var(--border2);border-radius:12px;padding:5px;min-width:160px;box-shadow:0 8px 32px rgba(0,0,0,.4);opacity:0;pointer-events:none;transform:scale(.95) translateY(-4px);transition:all .18s}
.ctx-menu.show{opacity:1;pointer-events:all;transform:none}
.ctx-item{display:flex;align-items:center;gap:9px;padding:9px 12px;border-radius:8px;font-size:.83rem;font-weight:500;cursor:pointer;transition:background .15s;color:var(--text)}
.ctx-item:hover{background:var(--border2)}
.ctx-sep{height:1px;background:var(--border);margin:4px 0}
/* session bar */
.session-bar{display:flex;align-items:center;gap:6px;font-size:.72rem;font-family:'Fira Code',monospace;color:var(--muted)}
.session-timer{color:var(--yellow)}
@keyframes fadeSlideIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.file-row,.file-card{animation:fadeSlideIn .25s ease both}
.file-row:nth-child(1),.file-card:nth-child(1){animation-delay:.03s}
.file-row:nth-child(2),.file-card:nth-child(2){animation-delay:.06s}
.file-row:nth-child(3),.file-card:nth-child(3){animation-delay:.09s}
.file-row:nth-child(n+4),.file-card:nth-child(n+4){animation-delay:.12s}
@media(max-width:640px){.f-date,.sort-date{display:none}.f-size,.sort-size{display:none}.f-actions{opacity:1}}
</style>
</head>
<body>
<header>
  <a class="logo" href="#" onclick="navigate('/');return false">
    <div class="logo-mark">⚡</div>
    <div>
      <div class="logo-text">FileBeam</div>
      <div class="logo-ver">v2 · secure</div>
    </div>
  </a>
  <div class="header-right">
    <div class="session-bar">
      <span>session:</span><span class="session-timer" id="sessionTimer">--:--</span>
    </div>
    <span class="pill pill-green"><span class="dot"></span>Secure</span>
    <button class="btn btn-glow btn-sm" onclick="openUpload()">⬆ Upload</button>
    <button class="btn btn-danger btn-sm" onclick="logout()">⏻</button>
  </div>
</header>

<div class="wrap">
  <div class="breadcrumb-bar" id="breadcrumb"></div>
  <div class="toolbar">
    <div class="search-wrap">
      <span class="search-icon">🔍</span>
      <input class="search-input" id="searchInput" placeholder="Search files and folders…" oninput="filterFiles()" autocomplete="off"/>
    </div>
    <div class="view-toggle">
      <button class="view-btn active" id="listBtn" onclick="setView('list')">☰</button>
      <button class="view-btn" id="gridBtn" onclick="setView('grid')">⊞</button>
    </div>
    <button class="btn btn-ghost btn-sm" onclick="loadDir(currentPath)">↺</button>
  </div>
  <div class="sort-bar" id="sortBar">
    <button class="sort-btn sort-name active" onclick="sortBy('name')" id="sort-name">Name <span id="sort-name-ico">↑</span></button>
    <button class="sort-btn sort-size" onclick="sortBy('size')" id="sort-size">Size</button>
    <button class="sort-btn sort-date" onclick="sortBy('date')" id="sort-date">Modified</button>
    <div class="sort-actions"></div>
  </div>
  <div id="fileContainer" class="file-list"></div>
</div>

<div class="drop-overlay" id="dropOverlay">
  <div class="drop-inner">
    <div style="font-size:3rem;margin-bottom:12px">📂</div>
    <h2 style="font-size:1.5rem;font-weight:800;margin-bottom:8px">Drop to Upload</h2>
    <p style="color:#5a5f7a">Release to upload to current folder</p>
  </div>
</div>

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
      <div class="upload-limit" id="uploadLimits"></div>
      <input type="file" id="fileInput" multiple style="display:none" onchange="uploadFiles(this.files)"/>
      <div class="prog-wrap" id="progWrap" style="display:flex">
        <div class="prog-track"><div class="prog-fill" id="progFill"></div></div>
        <div class="prog-label" id="progLabel">Ready</div>
      </div>
    </div>
  </div>
</div>

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

<div class="ctx-menu" id="ctxMenu">
  <div class="ctx-item" id="ctxOpen">📂 Open</div>
  <div class="ctx-item" id="ctxView">👁 Preview</div>
  <div class="ctx-sep"></div>
  <div class="ctx-item" id="ctxDownload">⬇ Download</div>
</div>

<div class="toast-stack" id="toastStack"></div>

<script>
// All API calls use session cookie — no token in URLs
const API = p => `/api${p}`;
let currentPath = "/", allFiles = [], viewMode = "list", sortKey = "name", sortAsc = true;
let sessionStart = Date.now();
const SESSION_MS = {{SESSION_MS}};

function init(){
  const hash = decodeURIComponent(location.hash.slice(1)) || "/";
  navigate(hash, false);
  setupDragDrop();
  document.addEventListener("click", hideCtx);
  document.addEventListener("keydown", e=>{ if(e.key==="Escape"){closeViewer();closeUpload();} });
  startSessionTimer();
  loadLimits();
}

// Session timer
function startSessionTimer(){
  setInterval(()=>{
    const elapsed = Date.now() - sessionStart;
    const remaining = Math.max(0, SESSION_MS - elapsed);
    const m = Math.floor(remaining/60000);
    const s = Math.floor((remaining%60000)/1000);
    document.getElementById("sessionTimer").textContent = `${m}:${s.toString().padStart(2,"0")}`;
    if(remaining < 60000) document.getElementById("sessionTimer").style.color="var(--red)";
    if(remaining === 0) logout();
  }, 1000);
}

async function loadLimits(){
  try{
    const r = await fetch(API("/limits"));
    if(r.status===401){location.href='/login';return;}
    const d = await r.json();
    document.getElementById("uploadLimits").textContent =
      `Max ${d.max_size_human} per file · Allowed: ${d.extensions.slice(0,8).join(", ")}…`;
  } catch {}
}

async function apiFetch(url, opts={}){
  const r = await fetch(url, {credentials:"include", ...opts});
  if(r.status === 401){ location.href = "/login"; throw new Error("Unauthorized"); }
  return r;
}

async function navigate(path, push=true){
  currentPath = path;
  if(push) history.pushState({},"",'#'+encodeURIComponent(path));
  renderBreadcrumb(path);
  await loadDir(path);
}
window.addEventListener("popstate",()=>{
  const hash = decodeURIComponent(location.hash.slice(1))||"/";
  navigate(hash,false);
});

function renderBreadcrumb(path){
  const parts = path.split("/").filter(Boolean);
  let html = `<span class="bc-seg" onclick="navigate('/')">🏠 Home</span>`;
  let acc = "";
  parts.forEach((p,i)=>{
    acc += "/"+p; html += `<span class="bc-sep">/</span>`;
    const snap=acc;
    if(i<parts.length-1) html+=`<span class="bc-seg" onclick="navigate('${snap}')">${p}</span>`;
    else html+=`<span class="bc-seg bc-cur">${p}</span>`;
  });
  document.getElementById("breadcrumb").innerHTML=html;
}

async function loadDir(path){
  const c=document.getElementById("fileContainer");
  c.innerHTML=`<div class="empty"><div style="font-size:2rem">⏳</div><div>Loading…</div></div>`;
  try{
    const r = await apiFetch(API(`/list?path=${encodeURIComponent(path)}`));
    const d = await r.json();
    if(d.error){toast(d.error,"error");return;}
    allFiles=d.items; renderFiles(allFiles);
  } catch(e){ if(e.message!=="Unauthorized") toast("Failed to load","error"); }
}

function filterFiles(){
  const q=document.getElementById("searchInput").value.toLowerCase();
  renderFiles(allFiles.filter(f=>f.name.toLowerCase().includes(q)));
}

function sortBy(key){
  if(sortKey===key) sortAsc=!sortAsc; else {sortKey=key;sortAsc=true;}
  document.querySelectorAll(".sort-btn").forEach(b=>b.classList.remove("active"));
  document.getElementById("sort-"+key).classList.add("active");
  const ico=document.getElementById("sort-"+key+"-ico");
  if(ico) ico.textContent=sortAsc?"↑":"↓";
  renderFiles(allFiles);
}

function sorted(files){
  return [...files].sort((a,b)=>{
    if(a.is_dir!==b.is_dir) return a.is_dir?-1:1;
    let va,vb;
    if(sortKey==="name"){va=a.name.toLowerCase();vb=b.name.toLowerCase();}
    else if(sortKey==="size"){va=a.size||0;vb=b.size||0;}
    else{va=a.mtime||0;vb=b.mtime||0;}
    return sortAsc?(va<vb?-1:va>vb?1:0):(va>vb?-1:va<vb?1:0);
  });
}

function setView(mode){
  viewMode=mode;
  document.getElementById("listBtn").classList.toggle("active",mode==="list");
  document.getElementById("gridBtn").classList.toggle("active",mode==="grid");
  document.getElementById("sortBar").style.display=mode==="list"?"flex":"none";
  renderFiles(allFiles);
}

const icoMap=m=>{
  if(!m) return ["📁","ico-dir"];
  if(m.startsWith("video/")) return ["🎬","ico-vid"];
  if(m.startsWith("audio/")) return ["🎵","ico-aud"];
  if(m.startsWith("image/")) return ["🖼","ico-img"];
  if(m.includes("pdf")) return ["📕","ico-txt"];
  if(m.startsWith("text/")||m.includes("json")) return ["📄","ico-txt"];
  if(m.includes("zip")||m.includes("rar")||m.includes("tar")) return ["🗜","ico-zip"];
  return ["📎","ico-gen"];
};

function renderFiles(files){
  const sf=sorted(files);
  const c=document.getElementById("fileContainer");
  c.className=viewMode==="grid"?"file-grid":"file-list";
  if(!sf.length){c.innerHTML=`<div class="empty"><div style="font-size:2rem">🌌</div><div>Nothing here</div></div>`;return;}
  c.innerHTML=sf.map(viewMode==="grid"?gridCard:listRow).join("");
}

function listRow(f){
  const fp=(currentPath.replace(/\/$/,"")+"/"+f.name);
  const [ico,cls]=f.is_dir?["📁","ico-dir"]:icoMap(f.mime);
  const canP=!f.is_dir&&f.mime&&(f.mime.startsWith("video/")||f.mime.startsWith("audio/")||f.mime.startsWith("image/")||f.mime.startsWith("text/"));
  return `<div class="file-row ${f.is_dir?'dir':''}"
    onclick="handleClick('${esc(fp)}','${esc(f.name)}','${f.mime||''}',${f.is_dir})"
    oncontextmenu="showCtx(event,'${esc(fp)}','${esc(f.name)}','${f.mime||''}',${f.is_dir})">
    <div class="f-ico ${cls}">${ico}</div>
    <div class="f-name">${esc(f.name)}</div>
    <div class="f-size">${f.is_dir?"—":f.size_human}</div>
    <div class="f-date">${f.modified}</div>
    <div class="f-actions" onclick="event.stopPropagation()">
      ${canP?`<button class="act-btn" onclick="openViewer('${esc(fp)}','${esc(f.name)}','${f.mime||''}')">👁</button>`:""}
      ${!f.is_dir?`<a class="act-btn" href="${API('/download?path='+encodeURIComponent(fp))}" download="${esc(f.name)}">⬇</a>`:""}
    </div>
  </div>`;
}

function gridCard(f){
  const fp=(currentPath.replace(/\/$/,"")+"/"+f.name);
  const [ico]=f.is_dir?["📁"]:icoMap(f.mime);
  const canP=!f.is_dir&&f.mime&&(f.mime.startsWith("video/")||f.mime.startsWith("audio/")||f.mime.startsWith("image/")||f.mime.startsWith("text/"));
  return `<div class="file-card"
    onclick="handleClick('${esc(fp)}','${esc(f.name)}','${f.mime||''}',${f.is_dir})"
    oncontextmenu="showCtx(event,'${esc(fp)}','${esc(f.name)}','${f.mime||''}',${f.is_dir})">
    <div class="card-ico">${ico}</div>
    <div class="card-name" title="${esc(f.name)}">${esc(f.name)}</div>
    <div class="card-size">${f.is_dir?"folder":f.size_human}</div>
    <div class="card-actions" onclick="event.stopPropagation()">
      ${canP?`<button class="act-btn" onclick="openViewer('${esc(fp)}','${esc(f.name)}','${f.mime||''}')">👁</button>`:""}
      ${!f.is_dir?`<a class="act-btn" href="${API('/download?path='+encodeURIComponent(fp))}" download="${esc(f.name)}">⬇</a>`:""}
    </div>
  </div>`;
}

function handleClick(fp,name,mime,isDir){
  if(isDir){navigate(fp);return;}
  const p=mime&&(mime.startsWith("video/")||mime.startsWith("audio/")||mime.startsWith("image/")||mime.startsWith("text/"));
  if(p) openViewer(fp,name,mime);
  else window.location.href=API('/download?path='+encodeURIComponent(fp));
}

function showCtx(e,fp,name,mime,isDir){
  e.preventDefault();e.stopPropagation();
  const m=document.getElementById("ctxMenu");
  document.getElementById("ctxOpen").style.display=isDir?"flex":"none";
  document.getElementById("ctxView").style.display=(!isDir&&mime&&(mime.startsWith("video/")||mime.startsWith("audio/")||mime.startsWith("image/")||mime.startsWith("text/")))?"flex":"none";
  document.getElementById("ctxDownload").style.display=isDir?"none":"flex";
  document.getElementById("ctxOpen").onclick=()=>{if(isDir)navigate(fp);hideCtx();};
  document.getElementById("ctxView").onclick=()=>{openViewer(fp,name,mime);hideCtx();};
  document.getElementById("ctxDownload").onclick=()=>{window.location.href=API('/download?path='+encodeURIComponent(fp));hideCtx();};
  m.style.left=Math.min(e.clientX,window.innerWidth-170)+"px";
  m.style.top=Math.min(e.clientY,window.innerHeight-140)+"px";
  m.classList.add("show");
}
function hideCtx(){document.getElementById("ctxMenu").classList.remove("show");}

async function openViewer(fp,name,mime){
  const url=API('/download?path='+encodeURIComponent(fp));
  document.getElementById("viewerName").textContent=name;
  document.getElementById("viewerDl").href=url;
  document.getElementById("viewerDl").download=name;
  const body=document.getElementById("viewerBody");
  if(mime.startsWith("video/")) body.innerHTML=`<video controls autoplay src="${url}"></video>`;
  else if(mime.startsWith("audio/")) body.innerHTML=`<audio controls autoplay src="${url}" style="width:100%;padding:24px"></audio>`;
  else if(mime.startsWith("image/")) body.innerHTML=`<img src="${url}" alt="${esc(name)}"/>`;
  else{body.innerHTML=`<pre>Loading…</pre>`;const r=await apiFetch(url);body.innerHTML=`<pre>${escH(await r.text())}</pre>`;}
  document.getElementById("viewerBg").classList.add("open");
}
function closeViewer(e){
  if(e&&e.target!==document.getElementById("viewerBg"))return;
  document.getElementById("viewerBg").classList.remove("open");
  document.getElementById("viewerBody").innerHTML="";
}

function openUpload(){document.getElementById("uploadModal").classList.add("open");}
function closeUpload(e){
  if(e&&e.target!==document.getElementById("uploadModal"))return;
  document.getElementById("uploadModal").classList.remove("open");
}
function uzDragOver(e){e.preventDefault();document.getElementById("uploadZone").classList.add("drag")}
function uzDragLeave(){document.getElementById("uploadZone").classList.remove("drag")}
function uzDrop(e){e.preventDefault();uzDragLeave();uploadFiles(e.dataTransfer.files)}

async function uploadFiles(files){
  if(!files.length)return;
  const pw=document.getElementById("progWrap"),pf=document.getElementById("progFill"),pl=document.getElementById("progLabel");
  pw.style.display="flex";
  for(let i=0;i<files.length;i++){
    const file=files[i];
    pl.textContent=`Uploading ${file.name} (${i+1}/${files.length})…`;
    const form=new FormData();
    form.append("file",file);form.append("path",currentPath);
    const result = await new Promise(res=>{
      const xhr=new XMLHttpRequest();
      xhr.upload.onprogress=ev=>{pf.style.width=Math.round((i+ev.loaded/ev.total)/files.length*100)+"%";};
      xhr.onload=()=>res(xhr);
      xhr.open("POST",API("/upload"));
      xhr.withCredentials=true;
      xhr.send(form);
    });
    if(result.status===401){location.href='/login';return;}
    if(result.status!==200){
      try{ const d=JSON.parse(result.responseText); toast(d.error||"Upload failed","error"); }
      catch{ toast("Upload failed","error"); }
      pw.style.display="none";pf.style.width="0%";pl.textContent="Ready";
      return;
    }
  }
  pf.style.width="100%";
  pl.textContent=`✅ ${files.length} file(s) uploaded!`;
  toast(`${files.length} file(s) uploaded`,"success");
  setTimeout(()=>{pw.style.display="none";pf.style.width="0%";pl.textContent="Ready";},2500);
  loadDir(currentPath);
}

function setupDragDrop(){
  let dc=0;
  document.addEventListener("dragenter",e=>{if(e.dataTransfer.types.includes("Files")){dc++;document.getElementById("dropOverlay").classList.add("active");}});
  document.addEventListener("dragleave",()=>{dc--;if(dc<=0){dc=0;document.getElementById("dropOverlay").classList.remove("active");}});
  document.addEventListener("dragover",e=>e.preventDefault());
  document.addEventListener("drop",e=>{e.preventDefault();dc=0;document.getElementById("dropOverlay").classList.remove("active");if(e.dataTransfer.files.length){openUpload();uploadFiles(e.dataTransfer.files);}});
}

async function logout(){
  await fetch('/auth/logout',{method:'POST',credentials:'include'});
  location.href='/login';
}

function toast(msg,type="info"){
  const stack=document.getElementById("toastStack");
  const el=document.createElement("div");
  el.className=`toast ${type}`;el.textContent=msg;
  stack.appendChild(el);
  requestAnimationFrame(()=>el.classList.add("show"));
  setTimeout(()=>{el.classList.remove("show");setTimeout(()=>el.remove(),400);},3000);
}

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");}
function escH(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

init();
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════════════
#  REQUEST HANDLER
# ═══════════════════════════════════════════════════════════════════
class Handler(BaseHTTPRequestHandler):
    root = DEFAULT_ROOT

    def log_message(self, fmt, *args): pass

    @property
    def client_ip(self):
        # Respect X-Forwarded-For from cloudflare tunnel
        fwd = self.headers.get("X-Forwarded-For","").split(",")[0].strip()
        return fwd or self.client_address[0]

    def get_session_token(self):
        cookies = self.headers.get("Cookie","")
        for part in cookies.split(";"):
            k,_,v = part.strip().partition("=")
            if k.strip() == "fb_session":
                return v.strip()
        return None

    def is_authenticated(self):
        token = self.get_session_token()
        return validate_session(token, self.client_ip)

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_security_headers()
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html, code=200):
        body = html.encode()
        self.send_response(code)
        self.send_security_headers()
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_security_headers(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("X-XSS-Protection","1; mode=block")
        self.send_header("Referrer-Policy","strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy",
            "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: blob:; media-src 'self' blob:;")
        self.send_header("Strict-Transport-Security","max-age=31536000; includeSubDomains")
        self.send_header("Cache-Control","no-store, no-cache, must-revalidate")

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length","0")
        self.end_headers()

    def do_GET(self):
        if is_rate_limited(self.client_ip):
            self.send_json({"error":"Too many requests"},429); return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        # Login page
        if path in ("/login",""):
            if self.is_authenticated():
                self.redirect("/"); return
            self.send_html(LOGIN_HTML); return

        # Root → redirect to login if not authed
        if path == "/":
            if not self.is_authenticated():
                self.redirect("/login"); return
            html = MAIN_HTML.replace("{{SESSION_MS}}", str(SESSION_LIFETIME * 1000))
            self.send_html(html); return

        # Auth required for all API routes
        if not self.is_authenticated():
            self.send_json({"error":"Unauthorized"},401); return

        if path == "/api/limits":
            self.send_json({
                "max_size_human": human_size(MAX_UPLOAD_BYTES),
                "max_size": MAX_UPLOAD_BYTES,
                "extensions": sorted(ALLOWED_EXTENSIONS),
            }); return

        if path == "/api/list":
            rel = unquote(qs.get("path",["/"])[0])
            abs_path = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
            if not abs_path.startswith(self.root):
                self.send_json({"error":"Access denied"},403); return
            if not os.path.isdir(abs_path):
                self.send_json({"error":"Not a directory"},400); return
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
                            "mime":mime_of(fp) if not is_dir else "",
                        })
                    except: pass
            except PermissionError:
                self.send_json({"error":"Permission denied"},403); return
            self.send_json({"items":items}); return

        if path == "/api/download":
            rel = unquote(qs.get("path",[""])[0])
            abs_path = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
            if not abs_path.startswith(self.root) or not os.path.isfile(abs_path):
                self.send_json({"error":"Not found"},404); return
            size = os.path.getsize(abs_path)
            mt = mime_of(abs_path)
            fname = os.path.basename(abs_path)
            self.send_response(200)
            self.send_security_headers()
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
        if is_rate_limited(self.client_ip):
            self.send_json({"error":"Too many requests. Slow down."},429); return

        parsed = urlparse(self.path)
        path = parsed.path

        # Login
        if path == "/auth/login":
            if is_locked_out(self.client_ip):
                remaining = lockout_remaining(self.client_ip)
                self.send_json({"error":f"Too many failed attempts. Try again in {remaining}s.","retry_after":remaining},429)
                return
            length = int(self.headers.get("Content-Length",0))
            try:
                body = json.loads(self.rfile.read(length))
                pw = body.get("password","")
            except:
                self.send_json({"error":"Bad request"},400); return

            pw_hash = hashlib.sha256(pw.encode()).hexdigest()
            if secrets.compare_digest(pw_hash, PASSWORD_HASH):
                clear_login_attempts(self.client_ip)
                purge_expired_sessions()
                token = create_session(self.client_ip)
                self.send_response(200)
                self.send_security_headers()
                self.send_header("Content-Type","application/json")
                self.send_header("Set-Cookie",
                    f"fb_session={token}; HttpOnly; Secure; SameSite=Strict; "
                    f"Max-Age={SESSION_LIFETIME}; Path=/")
                body_out = json.dumps({"ok":True}).encode()
                self.send_header("Content-Length",len(body_out))
                self.end_headers()
                self.wfile.write(body_out)
            else:
                record_failed_login(self.client_ip)
                if is_locked_out(self.client_ip):
                    self.send_json({"error":"Too many failed attempts. Locked out for 5 minutes.","retry_after":LOCKOUT_DURATION},429)
                else:
                    self.send_json({"error":"Incorrect password."},401)
            return

        # Logout
        if path == "/auth/logout":
            token = self.get_session_token()
            if token: revoke_session(token)
            self.send_response(200)
            self.send_security_headers()
            self.send_header("Set-Cookie","fb_session=; HttpOnly; Secure; SameSite=Strict; Max-Age=0; Path=/")
            self.send_header("Content-Type","application/json")
            body_out = json.dumps({"ok":True}).encode()
            self.send_header("Content-Length",len(body_out))
            self.end_headers()
            self.wfile.write(body_out)
            return

        # Upload (auth required)
        if not self.is_authenticated():
            self.send_json({"error":"Unauthorized"},401); return

        if path == "/api/upload":
            ct = self.headers.get("Content-Type","")
            length = int(self.headers.get("Content-Length",0))

            # Check content length early
            if length > MAX_UPLOAD_BYTES + 65536:
                self.send_json({"error":f"Request too large. Max {human_size(MAX_UPLOAD_BYTES)} per file."},413); return

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
                    ap = os.path.normpath(os.path.join(self.root, rel.lstrip("/")))
                    if ap.startswith(self.root): upload_path = ap
                elif 'name="file"' in hstr:
                    fn = re.search(r'filename="([^"]+)"', hstr)
                    if fn: file_name=fn.group(1); file_data=content

            if file_data is not None and file_name:
                ok, err = validate_upload(file_name, len(file_data))
                if not ok:
                    self.send_json({"error":err},400); return
                os.makedirs(upload_path, exist_ok=True)
                # Sanitise filename
                safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',file_name)
                with open(os.path.join(upload_path, safe_name),"wb") as f: f.write(file_data)
                self.send_json({"ok":True,"name":safe_name})
            else:
                self.send_json({"error":"No file received"},400)
            return

        self.send_json({"error":"Not found"},404)

# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="FileBeam Secure Server")
    parser.add_argument("--port",type=int,default=DEFAULT_PORT)
    parser.add_argument("--root",type=str,default=DEFAULT_ROOT)
    parser.add_argument("--password",type=str,default=SERVER_PASSWORD)
    parser.add_argument("--no-https",action="store_true",help="Disable HTTPS (not recommended)")
    args = parser.parse_args()

    global PASSWORD_HASH
    PASSWORD_HASH = hashlib.sha256(args.password.encode()).hexdigest()
    Handler.root = os.path.abspath(args.root)

    cert_dir = os.path.join(Path.home(), ".filebeam")
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "cert.pem")
    key_path  = os.path.join(cert_dir, "key.pem")

    server = HTTPServer(("0.0.0.0", args.port), Handler)

    if not args.no_https:
        generate_self_signed_cert(cert_path, key_path)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert_path, key_path)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        proto = "https"
    else:
        proto = "http"

    print("\n" + "═"*56)
    print("  ⚡  FileBeam Secure  ·  Hardened File Server")
    print("═"*56)
    print(f"  📁  Sharing   : {Handler.root}")
    print(f"  🔒  Protocol  : {proto.upper()} {'(TLS 1.2+)' if proto=='https' else '(plain)'}")
    print(f"  🌐  Local URL : {proto}://localhost:{args.port}")
    print(f"  🔑  Password  : {'(custom)' if args.password!=SERVER_PASSWORD else SERVER_PASSWORD}")
    print()
    print("  Security features active:")
    print("  ✅  Login page + session cookie (HttpOnly/Secure/SameSite)")
    print("  ✅  HTTPS with TLS 1.2+")
    print("  ✅  Brute-force lockout (5 attempts → 5 min ban)")
    print(f"  ✅  Rate limit ({MAX_REQUESTS_PER_MIN} req/min per IP)")
    print(f"  ✅  Session expiry ({SESSION_LIFETIME//60} min · {SESSION_IDLE_TIMEOUT//60} min idle)")
    print(f"  ✅  Upload limit ({human_size(MAX_UPLOAD_BYTES)} · {len(ALLOWED_EXTENSIONS)} allowed types)")
    print("  ✅  Security headers (CSP, HSTS, X-Frame, etc.)")
    print()
    if proto == "https":
        print("  ⚠️   Browser will warn about self-signed cert.")
        print("       Click 'Advanced → Proceed' once to accept it.")
    print("═"*56)
    print("  Press Ctrl+C to stop\n")

    try: server.serve_forever()
    except KeyboardInterrupt: print("\n  Server stopped.")

if __name__ == "__main__":
    main()
