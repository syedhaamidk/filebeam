<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Outfit&weight=800&size=42&pause=1000&color=4F8EF7&center=true&vCenter=true&width=500&height=70&lines=⚡+FileBeam" alt="FileBeam"/>

<p align="center">
  <b>Your personal file server. Access, sync & stream files between your PC and phone — from anywhere.</b>
</p>

<br/>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-4F8EF7?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/HTTPS-TLS%201.2+-3DD68C?style=for-the-badge&logo=letsencrypt&logoColor=white"/>
  <img src="https://img.shields.io/badge/No%20Dependencies-Zero%20Install-E06BFF?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/License-MIT-F5C542?style=for-the-badge"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Works%20On-Windows%20%7C%20macOS%20%7C%20Linux-4F8EF7?style=flat-square"/>
  <img src="https://img.shields.io/badge/Access%20From-Any%20Browser%20%7C%20Any%20Device-3DD68C?style=flat-square"/>
  <img src="https://img.shields.io/badge/Tunnel-Cloudflare%20%7C%20ngrok-E06BFF?style=flat-square"/>
</p>

<br/>

```
  PC Files ──────────────── Cloudflare Tunnel ──────────────── 📱 Phone
  Browse · Download · Upload · Stream · Sync · Secure
```

</div>

---

## ✨ What is FileBeam?

**FileBeam** is a self-hosted file server you run on your own PC. No cloud subscriptions, no third-party storage, no monthly fees. Your files stay on your machine — you just get a beautiful browser interface to access them from anywhere.

> Think of it as your own private Google Drive, but everything lives on *your* PC.

---

## 🗂 Project Structure

```
filebeam/
├── 🔒 fileserver_secure.py     # Hardened production server (recommended)
├── ⚡ fileserver_v2.py          # File browser — access PC files from phone
├── 🔄 filesync_v2.py           # Two-way sync — phone ↔ PC
├── 🪟 setup_cloudflare.bat     # One-click setup for Windows
└── 🐧 setup_cloudflare.sh      # One-click setup for macOS / Linux
```

---

## 🚀 Quick Start

### 1 — Run the server

```bash
# Secure server (recommended)
python fileserver_secure.py --password "YourPassword" --root "C:\Users\You\Files"

# Or the basic file browser
python fileserver_v2.py --root "C:\Users\You\Files"

# Or the two-way sync server
python filesync_v2.py --root "C:\Users\You\SyncFolder"
```

### 2 — Access on your phone (same WiFi)

```bash
# Find your PC's IP address
ipconfig          # Windows
ifconfig          # macOS / Linux

# Then open on your phone:
https://192.168.x.x:8443
```

### 3 — Access from anywhere (Cloudflare Tunnel)

```bash
# Windows — double-click:
setup_cloudflare.bat

# macOS / Linux:
bash setup_cloudflare.sh
```

> A public URL like `https://xxxx.trycloudflare.com` will appear. Open it on any device, anywhere in the world.

---

## 🛡️ Security Features

> `fileserver_secure.py` includes a full security hardening suite — no extra libraries needed.

<table>
<tr>
<td>

**🔐 HTTPS / TLS 1.2+**
Self-signed certificate auto-generated on first run. All traffic encrypted end-to-end.

</td>
<td>

**🔑 Login Page**
Password-protected with SHA-256 hashing and timing-safe comparison. Session cookie is `HttpOnly`, `Secure`, `SameSite=Strict`.

</td>
</tr>
<tr>
<td>

**🚫 Brute-Force Lockout**
5 failed login attempts triggers a 5-minute IP ban. Live countdown shown on the login page.

</td>
<td>

**⏱️ Auto-Expiring Sessions**
Sessions expire after 1 hour absolute, or 15 minutes of idle time. Countdown visible in the header.

</td>
</tr>
<tr>
<td>

**📦 Upload Restrictions**
500 MB max per file. Only whitelisted file types accepted (60+ extensions). Filenames are sanitised.

</td>
<td>

**🛡️ Security Headers**
Every response includes CSP, HSTS, X-Frame-Options, X-Content-Type-Options, and Referrer-Policy.

</td>
</tr>
</table>

---

## 🎛️ Configuration

All settings live at the top of each Python file — no config files, no `.env` needed.

```python
# ── fileserver_secure.py ──────────────────────────────────
SERVER_PASSWORD      = "changeme123"    # ← change this!
SESSION_LIFETIME     = 3600             # 1 hour
SESSION_IDLE_TIMEOUT = 900              # 15 min idle logout
MAX_LOGIN_ATTEMPTS   = 5               # before IP lockout
LOCKOUT_DURATION     = 300             # 5 minute ban
MAX_REQUESTS_PER_MIN = 120             # rate limit per IP
MAX_UPLOAD_BYTES     = 500 * 1024**2   # 500 MB per file
```

Or pass options via CLI:

```bash
python fileserver_secure.py \
  --port 8443 \
  --root "/path/to/share" \
  --password "SuperSecret42!" \
  --no-https          # only if behind a trusted reverse proxy
```

---

## 📱 Features by App

### `fileserver_v2.py` — File Browser

| Feature | Details |
|---|---|
| 📂 Browse | Navigate any folder on your PC |
| ⬇️ Download | Save any file to your phone |
| ⬆️ Upload | Send files from phone to PC |
| 🎬 Stream | Watch videos / listen to music in-browser |
| 🖼️ Preview | Images, text files, PDFs inline |
| ☰ / ⊞ Views | Toggle between list and grid layout |
| 🔍 Search | Real-time file filtering |
| 🖱️ Right-click | Context menu on every file |

### `filesync_v2.py` — Two-Way Sync

| Feature | Details |
|---|---|
| 📊 Live Stats | File count, total size, pending sync counter |
| 🔴🟢 Connection | Live pulsing dot — shows if PC is reachable |
| 📤 Phone → PC | Upload any file from phone to PC sync folder |
| 📥 PC → Phone | Download any PC file to phone in one tap |
| 🎨 Status Chips | Color-coded: Synced / PC Only / Phone Only |

---

## 🌍 Deployment Options

### Option A — Cloudflare Tunnel *(recommended, free forever)*

```
Your Phone  ──→  trycloudflare.com  ──→  Your PC
```

- ✅ Free, no account needed for basic use
- ✅ Files stay on your PC
- ✅ No port forwarding or router config
- ⚠️ URL changes each restart (fixed with a free Cloudflare account)

### Option B — Local WiFi Only

```
Your Phone  ──→  192.168.x.x:8443  ──→  Your PC
```

- ✅ Zero external exposure
- ✅ Fastest speed
- ❌ Only works at home

### Option C — Port Forwarding

```
Your Phone  ──→  your-public-ip:8443  ──→  Your PC
```

- ✅ Permanent URL
- ⚠️ Requires router configuration
- ⚠️ Exposes port to internet — use `fileserver_secure.py`

---

## 📋 Requirements

- **Python 3.8+** — that's it. All modules used (`ssl`, `http.server`, `hashlib`, etc.) are part of the standard library.
- **openssl** — for certificate generation (pre-installed on macOS/Linux; included with Git on Windows)

```bash
python --version    # must be 3.8+
openssl version     # for HTTPS cert generation
```

---

## 🔧 Allowed Upload Types

Documents, images, video, audio, archives, and code files are all supported out of the box:

```
.pdf .doc .docx .xls .xlsx .ppt .pptx .txt .md .csv
.jpg .jpeg .png .gif .webp .svg .heic
.mp4 .mov .avi .mkv .webm .m4v
.mp3 .wav .flac .aac .ogg .m4a
.zip .tar .gz .7z .rar
.json .yaml .py .js .ts .html .css .sh
```

To add more, edit `ALLOWED_EXTENSIONS` in the script.

---

## 🤝 Contributing

Pull requests are welcome! Some ideas for contributions:

- [ ] Multi-user support with per-user permissions
- [ ] File rename / delete from browser
- [ ] Folder creation
- [ ] QR code for quick phone access
- [ ] Dark/light theme toggle
- [ ] Persistent sync state (beyond session storage)
- [ ] Docker container

---

## ⚠️ Security Notes

- Always use `fileserver_secure.py` when exposing to the internet
- Change the default password before running
- The self-signed certificate will trigger a browser warning — this is expected. Click *Advanced → Proceed* once
- For production use, consider replacing the self-signed cert with a free [Let's Encrypt](https://letsencrypt.org) certificate
- Sessions are in-memory — they reset when the server restarts

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

<div align="center">

**Built with ❤️ and zero dependencies**

*FileBeam — because your files should go where you go.*

⭐ Star this repo if it's useful!

</div>
