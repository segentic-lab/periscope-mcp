import os

# Browser settings
HEADLESS = os.environ.get("HEADLESS", "true").lower() != "false"
STARTUP_PAUSE = int(os.environ.get("STARTUP_PAUSE", "10"))  # seconds to wait after browser opens
TIMEOUT = 30000  # milliseconds
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH", "/snap/chromium/current/usr/lib/chromium-browser/chrome")
# Navigation wait strategy: "networkidle" is thorough but hangs 30s on pages with
# websockets/polling. Set NAV_WAIT_UNTIL=load or domcontentloaded for those.
WAIT_UNTIL = os.environ.get("NAV_WAIT_UNTIL", "networkidle")

# Crawler settings
MAX_PAGES = 20
MAX_DEPTH = 3

# Session settings
MAX_SESSIONS = 20
SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT", "300"))  # seconds idle before expiry
MAX_RESPONSE_BODY_SIZE = 512000  # 500KB max per response body capture
MAX_CONSOLE_LOG = 500    # max console entries kept per session
MAX_NETWORK_LOG = 1000   # max network log entries kept per session

# Storage paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")

# Ensure directories exist
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
