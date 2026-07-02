#!/usr/bin/env bash
# Periscope MCP installer.
#
# Debian/Ubuntu (and derivatives): performs the full install.
# Any other platform: prints the exact commands for you to run yourself.
#
# Usage:
#   ./install.sh [options]
#
# Options:
#   -y, --yes              Don't ask before running sudo/apt steps
#   --skip-deps            Skip apt package installation (no sudo used)
#   --system-chromium      Use an existing system Chromium via CHROMIUM_PATH
#                          instead of downloading Playwright's browser build
#   --manual [PLATFORM]    Just print manual instructions and exit.
#                          PLATFORM: debian|fedora|arch|suse|macos|windows|generic
#   --refresh              Refresh an existing install on any platform:
#                          venv deps + browser + self-test + config (no apt/sudo).
#                          Used by update.sh.
#   -h, --help             Show this help

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_DIR/venv"
MIN_PY_MAJOR=3
MIN_PY_MINOR=11

ASSUME_YES=0
SKIP_DEPS=0
SYSTEM_CHROMIUM=0
FORCE_MANUAL=""
REFRESH=0

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mWARN:\033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        -y|--yes) ASSUME_YES=1 ;;
        --skip-deps) SKIP_DEPS=1 ;;
        --system-chromium) SYSTEM_CHROMIUM=1 ;;
        --manual) FORCE_MANUAL="${2:-generic}"; [ $# -gt 1 ] && shift ;;
        --refresh) REFRESH=1; SKIP_DEPS=1 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1 (see --help)" ;;
    esac
    shift
done

confirm() {
    [ "$ASSUME_YES" -eq 1 ] && return 0
    printf '%s [Y/n] ' "$1"
    read -r reply
    case "$reply" in n|N|no|NO) return 1 ;; *) return 0 ;; esac
}

# ---------------------------------------------------------------- detection

detect_platform() {
    if [ -n "$FORCE_MANUAL" ]; then
        echo "$FORCE_MANUAL"
        return
    fi
    case "$(uname -s)" in
        Darwin) echo "macos"; return ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows"; return ;;
        Linux) : ;;
        *) echo "generic"; return ;;
    esac
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        local ids="${ID:-} ${ID_LIKE:-}"
        case " $ids " in
            *debian*|*ubuntu*) echo "debian" ;;
            *fedora*|*rhel*|*centos*) echo "fedora" ;;
            *arch*|*manjaro*) echo "arch" ;;
            *suse*) echo "suse" ;;
            *) echo "generic" ;;
        esac
    else
        echo "generic"
    fi
}

find_system_chromium() {
    local candidates=(
        /snap/chromium/current/usr/lib/chromium-browser/chrome
        /usr/bin/chromium
        /usr/bin/chromium-browser
        /usr/bin/google-chrome
        /usr/bin/google-chrome-stable
        /Applications/Chromium.app/Contents/MacOS/Chromium
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    )
    for c in "${candidates[@]}"; do
        [ -x "$c" ] && { echo "$c"; return 0; }
    done
    command -v chromium 2>/dev/null || command -v chromium-browser 2>/dev/null || return 1
}

python_ok() {
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= ($MIN_PY_MAJOR, $MIN_PY_MINOR) else 1)" 2>/dev/null
}

# ------------------------------------------------------- manual instructions

MCP_CONFIG="$REPO_DIR/mcp-config.json"

write_mcp_config() {
    # Generated per-machine (absolute paths) — gitignored, safe to overwrite.
    if [ -n "${CHROMIUM_HINT:-}" ]; then
        cat > "$MCP_CONFIG" <<EOF
{
  "mcpServers": {
    "periscope": {
      "command": "$VENV/bin/python",
      "args": ["$REPO_DIR/server.py"],
      "env": { "CHROMIUM_PATH": "$CHROMIUM_HINT" }
    }
  }
}
EOF
    else
        cat > "$MCP_CONFIG" <<EOF
{
  "mcpServers": {
    "periscope": {
      "command": "$VENV/bin/python",
      "args": ["$REPO_DIR/server.py"]
    }
  }
}
EOF
    fi
    info "Wrote MCP config for this install path: $MCP_CONFIG"
}

print_registration() {
    local py="$VENV/bin/python"
    local env_lines=""
    [ -n "${CHROMIUM_HINT:-}" ] && env_lines="--env CHROMIUM_PATH=$CHROMIUM_HINT "
    cat <<EOF

-------------------------------------------------------------------
Register the server with your MCP client. The generated config below
(also written to mcp-config.json) works with most clients — Claude Code,
Cursor, Windsurf, and custom agents all accept this shape:

$(sed 's/^/  /' "$MCP_CONFIG")

Examples:
  Claude Code:  claude mcp add periscope $env_lines-- "$py" "$REPO_DIR/server.py"
                (or copy mcp-config.json into the project as .mcp.json)
  Cursor:       merge into ~/.cursor/mcp.json
  Codex CLI:    add [mcp_servers.periscope] with the same command/args
                to ~/.codex/config.toml
-------------------------------------------------------------------
EOF
}

manual_common() {
    cat <<EOF
  cd "$REPO_DIR"
  python3 -m venv venv
  venv/bin/python -m pip install --upgrade pip
  venv/bin/python -m pip install -r requirements.txt
EOF
}

print_manual() {
    local platform="$1"
    echo
    info "Automated install supports Debian/Ubuntu only."
    info "Run these commands yourself ($platform):"
    echo
    case "$platform" in
        debian)
            echo "  sudo apt-get update && sudo apt-get install -y git python3 python3-venv"
            manual_common
            echo "  venv/bin/python -m playwright install chromium"
            echo "  sudo venv/bin/python -m playwright install-deps chromium"
            ;;
        fedora)
            echo "  sudo dnf install -y git python3 python3-pip chromium"
            manual_common
            cat <<'EOF'
  # Playwright's install-deps only supports apt-based distros. Either use
  # Playwright's bundled browser (usually works on Fedora):
  venv/bin/python -m playwright install chromium
  # ...or point Periscope at the system Chromium instead:
  #   set CHROMIUM_PATH=/usr/bin/chromium in the MCP server env
EOF
            ;;
        arch)
            echo "  sudo pacman -S --needed git python chromium"
            manual_common
            cat <<'EOF'
  # Playwright's install-deps only supports apt-based distros. Either use
  # Playwright's bundled browser (usually works on Arch):
  venv/bin/python -m playwright install chromium
  # ...or point Periscope at the system Chromium instead:
  #   set CHROMIUM_PATH=/usr/bin/chromium in the MCP server env
EOF
            ;;
        suse)
            echo "  sudo zypper install -y git python311 python311-pip chromium"
            manual_common
            cat <<'EOF'
  venv/bin/python -m playwright install chromium
  # If the bundled browser is missing system libraries, use the system
  # Chromium instead: set CHROMIUM_PATH=/usr/bin/chromium in the server env.
EOF
            ;;
        macos)
            echo "  brew install python@3.12   # any Python >= 3.11"
            manual_common
            echo "  venv/bin/python -m playwright install chromium   # no install-deps needed on macOS"
            ;;
        windows)
            cat <<EOF
  # PowerShell, from the repo directory:
  py -3 -m venv venv
  venv\\Scripts\\pip install --upgrade pip
  venv\\Scripts\\pip install -r requirements.txt
  venv\\Scripts\\playwright install chromium
  # Register with your MCP client using venv\\Scripts\\python.exe + server.py
  # (Claude Code example: claude mcp add periscope -- venv\\Scripts\\python.exe server.py)
EOF
            return  # registration snippet below prints POSIX paths
            ;;
        *)
            echo "  # Install Python >= $MIN_PY_MAJOR.$MIN_PY_MINOR and a Chromium browser with your package manager, then:"
            manual_common
            cat <<'EOF'
  venv/bin/python -m playwright install chromium
  # If the bundled browser can't run (missing system libs), install a system
  # Chromium and set CHROMIUM_PATH=<path-to-chromium> in the MCP server env.
EOF
            ;;
    esac
    write_mcp_config
    print_registration
    echo "Verify afterwards with:"
    echo "  venv/bin/python -c 'from handlers import HANDLERS; from tool_schemas import TOOLS; print(len(TOOLS), \"tools ready\")'"
}

# ------------------------------------------------------------ debian install

install_debian() {
    if [ "$REFRESH" -eq 1 ]; then
        info "Refreshing existing install in $REPO_DIR"
    else
        info "Debian/Ubuntu detected — running automated install in $REPO_DIR"
    fi

    # --- system packages -------------------------------------------------
    local need_pkgs=()
    if ! command -v git >/dev/null; then
        need_pkgs+=(git)   # needed by update.sh and any git-based workflow
    fi
    if ! command -v python3 >/dev/null; then
        need_pkgs+=(python3)
    fi
    if ! python3 -c "import ensurepip" 2>/dev/null; then
        need_pkgs+=(python3-venv)
    fi
    if [ ${#need_pkgs[@]} -gt 0 ]; then
        if [ "$SKIP_DEPS" -eq 1 ]; then
            fail "Missing packages (${need_pkgs[*]}) but --skip-deps was given. Install them and re-run."
        fi
        info "Installing system packages: ${need_pkgs[*]}"
        confirm "Run 'sudo apt-get install ${need_pkgs[*]}'?" || fail "Aborted."
        sudo apt-get update
        sudo apt-get install -y "${need_pkgs[@]}"
    fi

    python_ok python3 || fail "Python >= $MIN_PY_MAJOR.$MIN_PY_MINOR required, found: $(python3 --version 2>&1). On older Ubuntu releases install a newer Python (e.g. via the deadsnakes PPA), then re-run."

    # --- venv + python deps ----------------------------------------------
    if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import sys" 2>/dev/null; then
        info "Reusing existing virtualenv at $VENV"
    else
        [ -d "$VENV" ] && { warn "Existing virtualenv is broken — recreating it"; rm -rf "$VENV"; }
        info "Creating virtualenv at $VENV"
        python3 -m venv "$VENV"
    fi
    # Always go through 'python -m ...': the venv's console-script shebangs
    # break if the repo directory is ever moved or renamed.
    info "Installing Python dependencies"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet -r "$REPO_DIR/requirements.txt"

    # --- browser ----------------------------------------------------------
    CHROMIUM_HINT=""
    if [ "$SYSTEM_CHROMIUM" -eq 1 ]; then
        CHROMIUM_HINT="$(find_system_chromium)" || fail "--system-chromium given but no Chromium/Chrome binary found."
        info "Using system Chromium: $CHROMIUM_HINT"
    else
        info "Installing Playwright's Chromium build"
        "$VENV/bin/python" -m playwright install chromium
        if [ "$SKIP_DEPS" -eq 1 ]; then
            warn "Skipping 'playwright install-deps' (--skip-deps); the browser may lack system libraries."
        else
            info "Installing Chromium system dependencies (needs sudo)"
            if confirm "Run 'sudo $VENV/bin/python -m playwright install-deps chromium'?"; then
                sudo "$VENV/bin/python" -m playwright install-deps chromium
            else
                warn "Skipped install-deps — if the browser fails to launch, re-run it manually."
            fi
        fi
    fi

    # --- self-test ----------------------------------------------------------
    info "Verifying installation"
    "$VENV/bin/python" -c "from handlers import HANDLERS; from tool_schemas import TOOLS; assert {t.name for t in TOOLS} == set(HANDLERS); print('  registry OK:', len(TOOLS), 'tools')" \
        || fail "Server modules failed to import."
    CHROMIUM_PATH="${CHROMIUM_HINT:-}" "$VENV/bin/python" - <<'PY' || fail "Headless Chromium failed to launch. Re-run with --system-chromium, or run 'sudo venv/bin/python -m playwright install-deps chromium'."
import asyncio, os
from playwright.async_api import async_playwright

async def main():
    kwargs = {"headless": True}
    if os.environ.get("CHROMIUM_PATH"):
        kwargs["executable_path"] = os.environ["CHROMIUM_PATH"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(**kwargs)
        page = await browser.new_page()
        await page.goto("data:text/html,<title>ok</title>")
        assert await page.title() == "ok"
        await browser.close()
    print("  browser OK: headless Chromium launches")

asyncio.run(main())
PY

    info "Install complete."
    write_mcp_config
    print_registration
}

# ----------------------------------------------------------------------- go

PLATFORM="$(detect_platform)"
if [ -n "$FORCE_MANUAL" ]; then
    print_manual "$PLATFORM"
elif [ "$REFRESH" -eq 1 ] || [ "$PLATFORM" = "debian" ]; then
    # --refresh works on any platform: apt is skipped and the flow is just
    # venv + pip + browser + self-test + config, all portable.
    install_debian
else
    print_manual "$PLATFORM"
fi
