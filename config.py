import os

# Browser settings
HEADLESS = os.environ.get("HEADLESS", "true").lower() != "false"
STARTUP_PAUSE = int(os.environ.get("STARTUP_PAUSE", "10"))  # seconds to wait after browser opens
TIMEOUT = 30000  # milliseconds
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080
# Path to a system Chromium/Chrome binary. Unset = Playwright's bundled Chromium.
# Useful when Playwright has no build for your OS (set e.g. CHROMIUM_PATH=/usr/bin/chromium).
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH") or None
# Navigation wait strategy: "networkidle" is thorough but hangs 30s on pages with
# websockets/polling. Set NAV_WAIT_UNTIL=load or domcontentloaded for those.
WAIT_UNTIL = os.environ.get("NAV_WAIT_UNTIL", "networkidle")

# Crawler settings
MAX_PAGES = 20
MAX_DEPTH = 3

# Session settings
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "20"))  # max concurrent sessions
SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT", "300"))  # seconds idle before expiry
MAX_RESPONSE_BODY_SIZE = 512000  # 500KB max per response body capture
MAX_RESPONSE_BODIES = 100  # max captured response bodies kept per session
MAX_CONSOLE_LOG = 500    # max console entries kept per session
MAX_NETWORK_LOG = 1000   # max network log entries kept per session

# Storage paths. PERISCOPE_DATA_DIR overrides the data root (tests/CI use it
# to avoid touching the real projects/screenshots store).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("PERISCOPE_DATA_DIR") or os.path.join(BASE_DIR, "data")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")  # saved storage_state per project (login sessions)
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")

# Ensure directories exist
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
