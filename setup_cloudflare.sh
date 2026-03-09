#!/bin/bash
# FileBeam + Cloudflare Tunnel Setup (macOS / Linux)

set -e
BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo "  ============================================================"
echo -e "  ${BOLD}⚡  FileBeam + Cloudflare Tunnel  —  Auto Setup${NC}"
echo "  ============================================================"
echo ""

DIR="$HOME/filebeam"
mkdir -p "$DIR"

# ── Step 1: Python ────────────────────────────────────────────────────────
echo -e "  ${BOLD}[1/4]${NC} Checking Python..."
if ! command -v python3 &>/dev/null; then
    echo -e "  ${RED}❌  Python3 not found. Install it first:${NC}"
    echo "       macOS:  brew install python3"
    echo "       Ubuntu: sudo apt install python3"
    exit 1
fi
echo -e "  ${GREEN}✅  Python3 found.${NC}"

# ── Step 2: cloudflared ───────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}[2/4]${NC} Setting up cloudflared..."

if command -v cloudflared &>/dev/null; then
    echo -e "  ${GREEN}✅  cloudflared already installed.${NC}"
else
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)
    [ "$ARCH" = "x86_64" ] && ARCH="amd64"
    [ "$ARCH" = "aarch64" ] && ARCH="arm64"

    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-${OS}-${ARCH}"
    echo "  ⬇  Downloading cloudflared for ${OS}/${ARCH}..."
    curl -L "$CF_URL" -o "$DIR/cloudflared"
    chmod +x "$DIR/cloudflared"
    CF_BIN="$DIR/cloudflared"
    echo -e "  ${GREEN}✅  cloudflared downloaded to $DIR/cloudflared${NC}"
fi

CF_BIN=$(command -v cloudflared 2>/dev/null || echo "$DIR/cloudflared")

# ── Step 3: Copy scripts ──────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}[3/4]${NC} Preparing FileBeam scripts..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in fileserver.py filesync.py; do
    if [ -f "$SCRIPT_DIR/$f" ] && [ ! -f "$DIR/$f" ]; then
        cp "$SCRIPT_DIR/$f" "$DIR/$f"
        echo -e "  ${GREEN}✅  $f copied.${NC}"
    fi
done

# ── Step 4: Launcher ──────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}[4/4]${NC} Creating launcher..."

cat > "$DIR/start_filebeam.sh" << EOF
#!/bin/bash
echo ""
echo "  ============================================================"
echo "  ⚡  FileBeam is starting..."
echo "  ============================================================"
echo ""
echo "  Starting file server on port 8080..."
python3 "$DIR/fileserver.py" --port 8080 &
SERVER_PID=\$!
sleep 2
echo "  Starting Cloudflare Tunnel..."
echo "  (Your public URL will appear below)"
echo ""
$CF_BIN tunnel --url http://localhost:8080
kill \$SERVER_PID 2>/dev/null
EOF

chmod +x "$DIR/start_filebeam.sh"
echo -e "  ${GREEN}✅  Launcher: $DIR/start_filebeam.sh${NC}"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "  ============================================================"
echo -e "  ${GREEN}${BOLD}✅  Setup Complete!${NC}"
echo "  ============================================================"
echo ""
echo "  HOW TO USE:"
echo "  1. Run:  $DIR/start_filebeam.sh"
echo "  2. A URL like https://xxxx.trycloudflare.com will appear"
echo "  3. Open that URL on your phone from ANYWHERE"
echo ""
echo -e "  ${YELLOW}NOTE:${NC} URL changes each restart. For a permanent URL,"
echo "  set up a free Cloudflare account tunnel."
echo ""
echo "  ============================================================"
echo ""

read -p "  Launch FileBeam now? (y/n): " LAUNCH
if [ "$LAUNCH" = "y" ] || [ "$LAUNCH" = "Y" ]; then
    bash "$DIR/start_filebeam.sh"
fi
