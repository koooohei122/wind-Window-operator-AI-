"""
Configuration for Wind Window Operator AI
"""
import os

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCREENSHOTS_DIR = os.path.join(DATA_DIR, "screenshots")
RECORDINGS_DIR = os.path.join(DATA_DIR, "recordings")
MEMORY_DIR = os.path.join(DATA_DIR, "memory")
SKILLS_DIR = os.path.join(DATA_DIR, "skills")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Screen capture settings
SCREENSHOT_INTERVAL_SECONDS = 10       # Take screenshot every N seconds
RECORDING_SEGMENT_MINUTES = 5         # Recording segment length in minutes
CAPTURE_MODE = "screenshot"            # "screenshot" or "recording"

# Multiple save folders (screenshots/recordings are saved to ALL of these)
SAVE_FOLDERS = [
    os.path.join(SCREENSHOTS_DIR, "primary"),
    os.path.join(SCREENSHOTS_DIR, "backup"),
    os.path.join(RECORDINGS_DIR, "primary"),
    os.path.join(RECORDINGS_DIR, "backup"),
]

# Cleanup settings
SCREENSHOT_RETENTION_HOURS = 3        # Delete screenshots after N hours
RECORDING_RETENTION_HOURS = 6         # Delete recordings after N hours
CLEANUP_CHECK_INTERVAL_MINUTES = 30   # How often to check for old files

# Memory settings
SHORT_TERM_MEMORY_FILE = os.path.join(MEMORY_DIR, "short_term.json")
LONG_TERM_MEMORY_FILE = os.path.join(MEMORY_DIR, "long_term.json")
MAX_MEMORY_ENTRIES = 100              # Max entries per memory type
MAX_MEMORY_CHARS = 500                # Max characters per memory entry
SHORT_TERM_PROMOTE_THRESHOLD = 5      # Promote to long-term after N appearances

# AI Analysis settings
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-opus-4-6"
ANALYSIS_INTERVAL_SECONDS = 30        # Analyze every N screenshots
MAX_SCREENSHOTS_PER_ANALYSIS = 3      # Send N most recent screenshots to AI

# Recommendation settings
VOICE_ENABLED = True
VOICE_RATE = 150                      # Speech rate (words per minute)
VOICE_LANGUAGE = "ja"                 # Japanese
RECOMMENDATION_INTERVAL_SECONDS = 60  # How often to generate recommendations

# Skills folder
SKILLS_INDEX_FILE = os.path.join(SKILLS_DIR, "index.json")

# Ensure all directories exist
for d in [
    SCREENSHOTS_DIR, RECORDINGS_DIR, MEMORY_DIR, SKILLS_DIR, LOGS_DIR,
    os.path.join(SCREENSHOTS_DIR, "primary"),
    os.path.join(SCREENSHOTS_DIR, "backup"),
    os.path.join(RECORDINGS_DIR, "primary"),
    os.path.join(RECORDINGS_DIR, "backup"),
]:
    os.makedirs(d, exist_ok=True)
