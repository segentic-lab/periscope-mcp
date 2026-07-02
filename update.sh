#!/usr/bin/env bash
# Periscope MCP updater: pull the latest source from GitHub and refresh the
# install (Python deps, browser, self-test, mcp-config.json).
#
# Usage:
#   ./update.sh [--force] [--full]
#
# Options:
#   --force   Stash local modifications to tracked files before updating
#   --full    Also re-check apt prerequisites (Debian/Ubuntu, uses sudo)
#   -h, --help
#
# Your data/ directory (projects, screenshots, reports) is untouched — it is
# not part of the repository.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

FORCE=0
FULL=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --full) FULL=1 ;;
        -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg (see --help)" >&2; exit 1 ;;
    esac
done

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null || fail "git is required"
[ -d .git ] || fail "This is not a git checkout, so it can't be updated in place.
Re-install fresh (your data/ directory can be copied over afterwards):
  git clone https://github.com/segentic-lab/periscope-mcp.git && cd periscope-mcp && ./install.sh"

# Local modifications to tracked files would make the pull fail halfway.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    if [ "$FORCE" -eq 1 ]; then
        info "Stashing local modifications (recover later with 'git stash pop')"
        git stash push --quiet -m "update.sh auto-stash"
    else
        fail "You have local modifications to tracked files:
$(git status --porcelain --untracked-files=no | sed 's/^/  /')
Commit or stash them first, or re-run with --force to stash automatically."
    fi
fi

BEFORE="$(git rev-parse HEAD)"
info "Fetching latest from $(git remote get-url origin)"
git pull --ff-only || fail "Your branch has diverged from origin — resolve manually (git status, git pull --rebase)."
AFTER="$(git rev-parse HEAD)"

if [ "$BEFORE" = "$AFTER" ]; then
    info "Source already up to date ($(git rev-parse --short HEAD))"
else
    info "Updated $(git rev-parse --short "$BEFORE") -> $(git rev-parse --short "$AFTER"):"
    git --no-pager log --oneline "$BEFORE..$AFTER" | sed 's/^/      /'
fi

# Refresh the install through install.sh: venv deps, browser, self-test,
# and a regenerated mcp-config.json. --refresh is portable (no apt/sudo);
# --full re-runs the whole Debian/Ubuntu flow including apt prerequisites.
INSTALL_ARGS=(-y)
if [ "$FULL" -eq 1 ]; then
    :  # full platform flow, may use sudo for apt / playwright install-deps
else
    INSTALL_ARGS+=(--refresh)
fi
# Keep using the system Chromium if the previous install chose it.
if [ -f mcp-config.json ] && grep -q CHROMIUM_PATH mcp-config.json; then
    INSTALL_ARGS+=(--system-chromium)
fi

info "Refreshing install: ./install.sh ${INSTALL_ARGS[*]}"
exec ./install.sh "${INSTALL_ARGS[@]}"
