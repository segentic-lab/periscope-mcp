import os

# Browser settings
HEADLESS = True
TIMEOUT = 30000  # milliseconds
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080

# Crawler settings
MAX_PAGES = 20
MAX_DEPTH = 3

# Storage paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")

# Ensure directories exist
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
