#!/usr/bin/env bash
# Photobooth — NUC setup script
# Run once from the repo root after cloning.
# Usage: bash setup.sh

set -euo pipefail

# ── colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLUE}→${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
die()  { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

# ── repo root check ───────────────────────────────────────────────────────────
[[ -f requirements.txt && -d src ]] || die "Run this script from the repo root."

# ── Python 3.11+ ──────────────────────────────────────────────────────────────
PYTHON=""
for candidate in python3.12 python3.11 python3; do
    if cmd=$(command -v "$candidate" 2>/dev/null); then
        ver=$($cmd -c 'import sys; print(sys.version_info >= (3,11))')
        if [[ "$ver" == "True" ]]; then PYTHON=$cmd; break; fi
    fi
done
[[ -z "$PYTHON" ]] && die "Python 3.11+ not found. Install it: sudo apt install python3.11"
ok "Python: $($PYTHON --version)"

# ── system packages ───────────────────────────────────────────────────────────
info "Installing system packages (apt)…"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    v4l-utils \
    libusb-1.0-0 \
    python3-venv \
    python3-pip \
    curl \
    git
ok "System packages ready"

# ── Python virtual environment ────────────────────────────────────────────────
VENV=".venv"
if [[ ! -d "$VENV" ]]; then
    info "Creating virtual environment…"
    $PYTHON -m venv "$VENV"
fi
# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install --upgrade pip -q
ok "Virtual environment: $VENV"

# ── Python dependencies ────────────────────────────────────────────────────────
info "Installing Python dependencies…"
pip install -r requirements.txt -q
ok "Python dependencies installed"

# ── directories ───────────────────────────────────────────────────────────────
for d in config photos fonts; do
    mkdir -p "$d"
done
ok "Directories: config/ photos/ fonts/"

# ── .env ──────────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    cat > .env <<'ENV'
WEB_PORT=8080
CONFIG_PATH=config/settings.json
# SHOTGUN_API_TOKEN=your_token_here
ENV
    ok ".env created"
else
    ok ".env already present"
fi

# ── udev rules ────────────────────────────────────────────────────────────────
RULES=/etc/udev/rules.d/60-photobooth.rules
if [[ ! -f "$RULES" ]]; then
    info "Installing udev rules → $RULES (requires sudo)…"
    sudo tee "$RULES" > /dev/null <<'RULES'
# Epson TM-M30 thermal printer (0e02 = USB, 0e20 = Bluetooth/USB combo)
SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", ATTRS{idProduct}=="0e02", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", ATTRS{idProduct}=="0e20", MODE="0666", GROUP="plugdev"
# ESP8266 CH340G (most NodeMCU clones)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", GROUP="dialout", SYMLINK+="ttyESP8266"
# ESP8266 CP2102 (some Wemos D1 Mini)
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666", GROUP="dialout", SYMLINK+="ttyESP8266"
RULES
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    ok "udev rules installed"
else
    ok "udev rules already present"
fi

# ── dialout group ─────────────────────────────────────────────────────────────
if ! groups | grep -qw dialout; then
    sudo usermod -aG dialout "$USER"
    warn "Added $USER to 'dialout' group — log out and back in for this to take effect"
else
    ok "User already in dialout group"
fi

# ── plugdev group ─────────────────────────────────────────────────────────────
if ! groups | grep -qw plugdev; then
    sudo usermod -aG plugdev "$USER"
    warn "Added $USER to 'plugdev' group — log out and back in for this to take effect"
else
    ok "User already in plugdev group"
fi

# ── Arduino CLI ───────────────────────────────────────────────────────────────
ARDUINO_BIN="$HOME/.local/bin/arduino-cli"
if [[ ! -x "$ARDUINO_BIN" ]]; then
    info "Installing Arduino CLI…"
    mkdir -p "$HOME/.local/bin"
    # BINDIR env var sets the install destination (--bindir flag breaks the URL)
    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
        | BINDIR="$HOME/.local/bin" sh
    ok "Arduino CLI installed → $ARDUINO_BIN"
else
    ok "Arduino CLI already installed"
fi
export PATH="$HOME/.local/bin:$PATH"

# Board manager + ESP8266 core + FastLED
info "Configuring Arduino CLI (ESP8266 core + FastLED)…"
arduino-cli config init --overwrite
arduino-cli config set board_manager.additional_urls \
    "https://arduino.esp8266.com/stable/package_esp8266com_index.json"
arduino-cli core update-index

if ! arduino-cli core list | grep -q esp8266:esp8266; then
    info "Installing ESP8266 core (takes a moment)…"
    arduino-cli core install esp8266:esp8266
    ok "ESP8266 core installed"
else
    ok "ESP8266 core already installed"
fi

if ! arduino-cli lib list | grep -q FastLED; then
    arduino-cli lib install FastLED
    ok "FastLED library installed"
else
    ok "FastLED already installed"
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  1. Flash the ESP8266 firmware (plug in via USB first):"
echo ""
echo "       arduino-cli compile --fqbn esp8266:esp8266:nodemcu esp32/"
echo "       arduino-cli upload  --fqbn esp8266:esp8266:nodemcu \\"
echo "                           --port /dev/ttyUSB0 esp32/"
echo ""
echo "  2. Test the LED ring (no camera or printer needed):"
echo ""
echo "       source .venv/bin/activate"
echo "       python src/test_hardware.py --port /dev/ttyUSB0"
echo ""
echo "  3. Start the photobooth:"
echo ""
echo "       source .venv/bin/activate"
echo "       python src/main.py --no-printer    # skip printer"
echo "       python src/main.py --no-camera     # skip camera (placeholder)"
echo "       python src/main.py --no-esp        # skip ESP8266 entirely"
echo "       python src/main.py                 # full hardware"
echo ""
echo "  Web UI (layout + virtual trigger): http://localhost:8080"
echo ""
